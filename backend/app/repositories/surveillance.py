"""
Disease report repository — data access layer for Pillar B (Surveillance).

All heavy queries are written to remain efficient as the disease_reports table
grows.  The two aggregate methods (aggregate_by_region, time_series) are
designed with B2 (clustering) and B3 (spike detection) in mind:

  aggregate_by_region  →  one row per region with total cases and centroid
                           coordinates.  B2 feeds this directly into DBSCAN.

  time_series          →  daily case counts for one (region, disease) pair.
                           B3 runs the sliding-window z-score over this series.

Time complexity:
  create          O(1)
  get_by_id       O(1) with PK index
  list_reports    O(rows_scanned) — bounded by `limit` and date range filter
  aggregate_*     O(R) for R matching rows — GROUP BY pushes work to Postgres
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas import DiseaseReportCreate
from app.infra.models import DiseaseReport


class SurveillanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── writes ────────────────────────────────────────────────────────────────

    async def create(self, data: DiseaseReportCreate) -> DiseaseReport:
        """Insert one disease report.  reported_at defaults to UTC now."""
        row = DiseaseReport(
            disease_name=data.disease_name,
            region=data.region,
            latitude=data.latitude,
            longitude=data.longitude,
            case_count=data.case_count,
            reported_at=data.reported_at or datetime.now(timezone.utc),
        )
        self._s.add(row)
        await self._s.commit()
        await self._s.refresh(row)
        return row

    # ── reads ─────────────────────────────────────────────────────────────────

    async def get_by_id(self, report_id: int) -> DiseaseReport | None:
        result = await self._s.execute(
            select(DiseaseReport).where(DiseaseReport.id == report_id)
        )
        return result.scalar_one_or_none()

    async def list_reports(
        self,
        disease: str | None = None,
        region: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 200,
    ) -> list[DiseaseReport]:
        """
        Return reports filtered by any combination of disease name, region,
        and date window, newest-first.  All filters are optional.
        """
        stmt = select(DiseaseReport).order_by(DiseaseReport.reported_at.desc())
        if disease:
            stmt = stmt.where(DiseaseReport.disease_name == disease)
        if region:
            stmt = stmt.where(DiseaseReport.region == region)
        if from_date:
            stmt = stmt.where(DiseaseReport.reported_at >= from_date)
        if to_date:
            stmt = stmt.where(DiseaseReport.reported_at <= to_date)
        stmt = stmt.limit(limit)
        result = await self._s.execute(stmt)
        return list(result.scalars().all())

    async def aggregate_by_region(
        self,
        disease: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict]:
        """
        Aggregate total cases and report count per region.

        Returns a list of dicts:
          {region, latitude, longitude, total_cases, report_count, diseases}

        The coordinates returned are the centroid average of all reports for
        that region (or None if no coordinates were stored).  B2 clustering
        uses these centroids to place each region on the map.

        Used by B2 (DBSCAN hotspot clustering).
        """
        stmt = (
            select(
                DiseaseReport.region,
                func.avg(DiseaseReport.latitude).label("latitude"),
                func.avg(DiseaseReport.longitude).label("longitude"),
                func.sum(DiseaseReport.case_count).label("total_cases"),
                func.count(DiseaseReport.id).label("report_count"),
            )
            .group_by(DiseaseReport.region)
            .order_by(func.sum(DiseaseReport.case_count).desc())
        )
        if disease:
            stmt = stmt.where(DiseaseReport.disease_name == disease)
        if from_date:
            stmt = stmt.where(DiseaseReport.reported_at >= from_date)
        if to_date:
            stmt = stmt.where(DiseaseReport.reported_at <= to_date)

        result = await self._s.execute(stmt)
        rows = result.all()

        # Fetch the distinct disease names per region in a second pass
        disease_stmt = select(
            DiseaseReport.region,
            DiseaseReport.disease_name,
        ).distinct()
        if from_date:
            disease_stmt = disease_stmt.where(DiseaseReport.reported_at >= from_date)
        if to_date:
            disease_stmt = disease_stmt.where(DiseaseReport.reported_at <= to_date)
        dr = await self._s.execute(disease_stmt)
        region_diseases: dict[str, list[str]] = {}
        for reg, dis in dr.all():
            region_diseases.setdefault(reg, []).append(dis)

        return [
            {
                "region": row.region,
                "latitude": float(row.latitude) if row.latitude is not None else None,
                "longitude": float(row.longitude) if row.longitude is not None else None,
                "total_cases": int(row.total_cases),
                "report_count": int(row.report_count),
                "diseases": sorted(region_diseases.get(row.region, [])),
            }
            for row in rows
        ]

    async def time_series(
        self,
        region: str,
        disease: str | None = None,
        days: int = 90,
    ) -> list[dict]:
        """
        Return daily aggregated case counts for one region (optionally one disease).

        Output: [{date: "YYYY-MM-DD", total_cases: int, report_count: int}, ...]
        sorted chronologically (oldest first — B3 expects a forward time series).

        Used by B3 (sliding-window z-score spike detection).
        """
        stmt = (
            select(
                func.date_trunc("day", DiseaseReport.reported_at).label("day"),
                func.sum(DiseaseReport.case_count).label("total_cases"),
                func.count(DiseaseReport.id).label("report_count"),
            )
            .where(DiseaseReport.region == region)
            .group_by(func.date_trunc("day", DiseaseReport.reported_at))
            .order_by(func.date_trunc("day", DiseaseReport.reported_at))
        )
        if disease:
            stmt = stmt.where(DiseaseReport.disease_name == disease)
        if days:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            stmt = stmt.where(DiseaseReport.reported_at >= cutoff)

        result = await self._s.execute(stmt)
        return [
            {
                "date": row.day.strftime("%Y-%m-%d"),
                "total_cases": int(row.total_cases),
                "report_count": int(row.report_count),
            }
            for row in result.all()
        ]
