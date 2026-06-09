"""
Surveillance API — Pillar B (Outbreak Monitoring).

Endpoints:
  POST /surveillance/reports              Ingest a new disease report
  GET  /surveillance/reports              List/filter reports
  GET  /surveillance/reports/{id}         Single report by ID
  GET  /surveillance/summary/by-region    Aggregated totals per region (→ B2 input)
  GET  /surveillance/summary/time-series  Daily series for one region (→ B3 input)

Why this separation from the emergency router (Pillar A):
  Pillar A and Pillar B are independent data streams that only meet at the
  event bus — A emits RouteComputed/AmbulanceAssigned; B emits
  OutbreakDetected/AlertGenerated.  Separate routers enforce this boundary
  at the API layer.

Why a dedicated summary/by-region endpoint:
  Raw disease_reports rows are too fine-grained for clustering (B2 needs one
  centroid and one total-case count per region, not hundreds of individual
  rows).  Aggregation happens in the DB via GROUP BY, not in Python, so it
  scales as the table grows.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_bus, get_surveillance_repo
from app.domain.events import Event, EventType
from app.domain.schemas import (
    DiseaseReportCreate,
    DiseaseReportResponse,
    RegionSummary,
    TimeSeriesPoint,
)
from app.events.bus import EventBus
from app.repositories.surveillance import SurveillanceRepository

router = APIRouter(prefix="/surveillance", tags=["surveillance"])


@router.post("/reports", response_model=DiseaseReportResponse, status_code=201)
async def ingest_report(
    data: DiseaseReportCreate,
    repo: SurveillanceRepository = Depends(get_surveillance_repo),
    bus: EventBus = Depends(get_bus),
) -> DiseaseReportResponse:
    """
    Ingest one disease report.  reported_at defaults to UTC now if omitted.

    Emits a DiseaseReported event so the frontend live-feed reflects new data
    without polling.  B2 (clustering) and B3 (spike detection) also subscribe
    to this event to decide when to re-run their analyses.
    """
    report = await repo.create(data)
    await bus.publish(Event(
        type=EventType.DISEASE_REPORTED,
        payload={
            "report_id": report.id,
            "disease_name": report.disease_name,
            "region": report.region,
            "case_count": report.case_count,
            "reported_at": report.reported_at.isoformat(),
        },
    ))
    return DiseaseReportResponse.model_validate(report)


@router.get("/reports", response_model=list[DiseaseReportResponse])
async def list_reports(
    disease: str | None = Query(default=None, description="Filter by disease name"),
    region: str | None = Query(default=None, description="Filter by region"),
    from_date: datetime | None = Query(default=None, description="Earliest reported_at (inclusive)"),
    to_date: datetime | None = Query(default=None, description="Latest reported_at (inclusive)"),
    limit: int = Query(default=100, ge=1, le=1000),
    repo: SurveillanceRepository = Depends(get_surveillance_repo),
) -> list[DiseaseReportResponse]:
    reports = await repo.list_reports(
        disease=disease,
        region=region,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )
    return [DiseaseReportResponse.model_validate(r) for r in reports]


@router.get("/reports/{report_id}", response_model=DiseaseReportResponse)
async def get_report(
    report_id: int,
    repo: SurveillanceRepository = Depends(get_surveillance_repo),
) -> DiseaseReportResponse:
    report = await repo.get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return DiseaseReportResponse.model_validate(report)


@router.get("/summary/by-region", response_model=list[RegionSummary])
async def summary_by_region(
    disease: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    repo: SurveillanceRepository = Depends(get_surveillance_repo),
) -> list[RegionSummary]:
    """
    Aggregate total cases and report count per region, sorted by total_cases
    descending (highest-burden regions first).

    Used as the direct input for B2 clustering: each row becomes one point
    in the geographic feature space with weight = total_cases.
    """
    rows = await repo.aggregate_by_region(
        disease=disease,
        from_date=from_date,
        to_date=to_date,
    )
    return [RegionSummary(**row) for row in rows]


@router.get("/summary/time-series", response_model=list[TimeSeriesPoint])
async def time_series(
    region: str = Query(description="Region to analyse"),
    disease: str | None = Query(default=None, description="Restrict to one disease"),
    days: int = Query(default=90, ge=7, le=365, description="Lookback window in days"),
    repo: SurveillanceRepository = Depends(get_surveillance_repo),
) -> list[TimeSeriesPoint]:
    """
    Daily case-count time series for one region (optionally one disease).

    Returned in chronological order (oldest → newest) so B3's sliding-window
    z-score algorithm can iterate forward without reversing the array.
    """
    points = await repo.time_series(region=region, disease=disease, days=days)
    return [TimeSeriesPoint(**p) for p in points]
