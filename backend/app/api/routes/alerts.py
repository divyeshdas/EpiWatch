"""
Alerts API — read access to the alerts table.

Alerts are created by app.surveillance.alerts.run_scan (B3 spike detection,
triggered via POST /surveillance/scan).  This router only exposes the list
view; nothing here writes to the table.
"""
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_alert_repo
from app.domain.schemas import AlertResponse
from app.repositories.alerts import AlertRepository

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    severity: str | None = Query(default=None, description="Filter by severity (LOW/MEDIUM/HIGH/CRITICAL)"),
    type: str | None = Query(default=None, alias="type", description="Filter by alert type (e.g. OUTBREAK_SPIKE)"),
    limit: int = Query(default=100, ge=1, le=500),
    repo: AlertRepository = Depends(get_alert_repo),
) -> list[AlertResponse]:
    """List alerts newest-first, optionally filtered by severity and/or type."""
    alerts = await repo.list_alerts(severity=severity, type_=type, limit=limit)
    return [AlertResponse.model_validate(a) for a in alerts]
