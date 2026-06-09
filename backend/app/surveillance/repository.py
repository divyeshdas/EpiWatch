"""
OutbreakRepository — data access for the outbreak_timeseries table.

Query patterns and why they are indexed the way they are:

  timeseries():
    WHERE disease_name = ? AND region = ?  (equality)
    AND   date BETWEEN ? AND ?             (range)
    ORDER BY date                          (forward time order for B3)

    The (disease_name, region, date) composite index supports this pattern
    in one B-tree scan: the first two columns select the right time series,
    then date narrows the window.

  available_diseases():
    SELECT DISTINCT disease_name — full table scan; expected to be tiny
    (few hundred rows) so no special index needed.

  available_regions():
    SELECT DISTINCT region WHERE disease_name = ? — index prefix scan.

  summary():
    GROUP BY disease_name, SUM/MAX — index helps avoid seq-scan on large tables.

Time complexity:
  timeseries()          O(R) where R = rows in the date window
  available_diseases()  O(D × R / D) ≈ O(R) first time, cached after
  summary()             O(D × R / D) per disease — GROUP BY uses the index
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import OutbreakTimeSeries


class OutbreakRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def timeseries(
        self,
        disease_name: str,
        region: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[OutbreakTimeSeries]:
        """
        Return ordered (oldest-first) time-series rows for one disease+region.
        B3 spike detection requires a forward-ordered series.
        """
        stmt = (
            select(OutbreakTimeSeries)
            .where(OutbreakTimeSeries.disease_name == disease_name)
            .where(OutbreakTimeSeries.region == region)
            .order_by(OutbreakTimeSeries.date)
        )
        if from_date:
            stmt = stmt.where(OutbreakTimeSeries.date >= from_date)
        if to_date:
            stmt = stmt.where(OutbreakTimeSeries.date <= to_date)
        result = await self._s.execute(stmt)
        return list(result.scalars().all())

    async def available_diseases(self) -> list[str]:
        """List all distinct disease names, alphabetically sorted."""
        result = await self._s.execute(
            select(distinct(OutbreakTimeSeries.disease_name))
            .order_by(OutbreakTimeSeries.disease_name)
        )
        return list(result.scalars().all())

    async def available_regions(self, disease_name: str) -> list[str]:
        """List all distinct regions available for a given disease."""
        result = await self._s.execute(
            select(distinct(OutbreakTimeSeries.region))
            .where(OutbreakTimeSeries.disease_name == disease_name)
            .order_by(OutbreakTimeSeries.region)
        )
        return list(result.scalars().all())

    async def disease_metadata(self) -> list[dict]:
        """
        Return one dict per disease with regions, date range, and record count.
        Used by GET /surveillance/diseases to populate the frontend selectors.
        """
        stmt = (
            select(
                OutbreakTimeSeries.disease_name,
                OutbreakTimeSeries.region,
                func.min(OutbreakTimeSeries.date).label("date_from"),
                func.max(OutbreakTimeSeries.date).label("date_to"),
                func.count(OutbreakTimeSeries.id).label("record_count"),
            )
            .group_by(OutbreakTimeSeries.disease_name, OutbreakTimeSeries.region)
            .order_by(OutbreakTimeSeries.disease_name, OutbreakTimeSeries.region)
        )
        result = await self._s.execute(stmt)
        rows = result.all()

        # Merge per-region rows into one entry per disease.
        diseases: dict[str, dict] = {}
        for row in rows:
            d = row.disease_name
            if d not in diseases:
                diseases[d] = {
                    "disease_name": d,
                    "regions": [],
                    "date_from": row.date_from.isoformat(),
                    "date_to": row.date_to.isoformat(),
                    "total_records": 0,
                }
            diseases[d]["regions"].append(row.region)
            # Extend the global date range for the disease
            df = row.date_from.isoformat()
            dt = row.date_to.isoformat()
            if df < diseases[d]["date_from"]:
                diseases[d]["date_from"] = df
            if dt > diseases[d]["date_to"]:
                diseases[d]["date_to"] = dt
            diseases[d]["total_records"] += row.record_count

        return list(diseases.values())

    async def summary(self) -> list[dict]:
        """
        Return total cases, deaths, peak case count, and peak date per disease.
        Used by GET /surveillance/summary for headline stat cards.
        """
        stmt = (
            select(
                OutbreakTimeSeries.disease_name,
                func.sum(OutbreakTimeSeries.case_count).label("total_cases"),
                func.sum(OutbreakTimeSeries.deaths).label("total_deaths"),
                func.max(OutbreakTimeSeries.case_count).label("peak_cases"),
                func.count(OutbreakTimeSeries.id).label("record_count"),
            )
            .group_by(OutbreakTimeSeries.disease_name)
            .order_by(func.sum(OutbreakTimeSeries.case_count).desc())
        )
        result = await self._s.execute(stmt)
        agg_rows = result.all()

        # Second pass: find the date of the peak for each disease
        peak_dates: dict[str, str] = {}
        for row in agg_rows:
            peak_stmt = (
                select(OutbreakTimeSeries.date)
                .where(OutbreakTimeSeries.disease_name == row.disease_name)
                .where(OutbreakTimeSeries.case_count == row.peak_cases)
                .limit(1)
            )
            pd_result = await self._s.execute(peak_stmt)
            pd_row = pd_result.scalar_one_or_none()
            peak_dates[row.disease_name] = pd_row.isoformat() if pd_row else None

        return [
            {
                "disease_name": row.disease_name,
                "total_cases": int(row.total_cases),
                "total_deaths": int(row.total_deaths),
                "peak_cases": int(row.peak_cases),
                "peak_date": peak_dates.get(row.disease_name),
                "record_count": int(row.record_count),
            }
            for row in agg_rows
        ]

    async def count(self) -> int:
        result = await self._s.execute(select(func.count(OutbreakTimeSeries.id)))
        return result.scalar_one()
