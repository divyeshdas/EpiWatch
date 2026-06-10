"""
Alert repository — data access for the alerts table.

Idempotency strategy
---------------------
B3's POST /surveillance/scan can be called repeatedly over the same series
(e.g. every time new outbreak data lands).  Re-running detection must not
create duplicate alerts for a (type, disease_name, region, event_date)
combination that was already raised.

uq_alerts_spike_dedup (migration 006) is a unique constraint on exactly those
four columns.  create_spike_alert() does an INSERT ... ON CONFLICT DO NOTHING
against it: if the row already exists, the insert is a no-op and
.returning() yields nothing, so the method returns None.  The caller (the
alert engine) uses that None to skip emitting a duplicate AlertGenerated
event.  This pushes the uniqueness guarantee to the database, so it holds
even if two scans run concurrently — a plain "SELECT then INSERT if missing"
would have a race window between the two statements.

Time complexity: O(1) per alert (index lookup via the unique constraint);
O(R) for list_alerts where R = matching rows, ordered by the created_at
index (newest first).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.models import Alert

SPIKE_ALERT_TYPE = "OUTBREAK_SPIKE"


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_spike_alert(
        self,
        disease_name: str,
        region: str,
        event_date: str,
        severity: str,
        z_score: float,
        message: str,
    ) -> dict | None:
        """
        Insert one OUTBREAK_SPIKE alert.  Returns the inserted row as a dict,
        or None if a row with the same (type, disease_name, region,
        event_date) already existed (duplicate scan — no-op).
        """
        stmt = (
            insert(Alert)
            .values(
                type=SPIKE_ALERT_TYPE,
                severity=severity,
                message=message,
                region=region,
                disease_name=disease_name,
                event_date=date.fromisoformat(event_date),
                z_score=z_score,
            )
            .on_conflict_do_nothing(constraint="uq_alerts_spike_dedup")
            .returning(Alert.id, Alert.created_at)
        )
        result = await self._s.execute(stmt)
        row = result.first()
        await self._s.commit()
        if row is None:
            return None
        return {
            "id": row.id,
            "type": SPIKE_ALERT_TYPE,
            "severity": severity,
            "message": message,
            "region": region,
            "disease_name": disease_name,
            "event_date": event_date,
            "z_score": z_score,
            "created_at": row.created_at,
            "resolved_at": None,
        }

    async def list_alerts(
        self,
        severity: str | None = None,
        type_: str | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        """Return alerts newest-first, optionally filtered by severity/type."""
        stmt = select(Alert).order_by(Alert.created_at.desc())
        if severity:
            stmt = stmt.where(Alert.severity == severity)
        if type_:
            stmt = stmt.where(Alert.type == type_)
        stmt = stmt.limit(limit)
        result = await self._s.execute(stmt)
        return list(result.scalars().all())
