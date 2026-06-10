"""
Surveillance API — Pillar B (Outbreak Monitoring).

Operational endpoints (disease_reports table — real-time incident reports):
  POST /surveillance/reports              Ingest a new disease report
  GET  /surveillance/reports              List/filter reports
  GET  /surveillance/reports/{id}         Single report by ID
  GET  /surveillance/summary/by-region    Aggregated totals per region (→ B2 input)
  GET  /surveillance/summary/time-series  Daily series for one region (→ B3 input)

Analytical endpoints (outbreak_timeseries table — OWID historical data):
  GET  /surveillance/diseases             Available diseases + regions + date range
  GET  /surveillance/timeseries           Ordered time-series for one disease+region
  GET  /surveillance/summary              Totals/peaks per disease (headline cards)

Spike detection / alerts (B3, outbreak_timeseries-driven):
  GET  /surveillance/spikes               Read-only z-score detections (chart markers)
  POST /surveillance/scan                 Detect + persist alerts + emit AlertGenerated

Why two separate tables served from the same router:
  disease_reports is operational: individual field reports, timestamptz precision,
  used for real-time alerting and B2/B3 input.
  outbreak_timeseries is analytical: calendar-day aggregates from OWID, used for
  the ECharts historical visualization.  Both live under /surveillance because they
  represent the same concern (disease surveillance) at different granularities.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_alert_repo, get_bus, get_outbreak_repo, get_surveillance_repo
from app.config import settings
from app.domain.events import Event, EventType
from app.domain.schemas import (
    AlertResponse,
    DiseaseInfo,
    DiseaseReportCreate,
    DiseaseReportResponse,
    HotspotCluster,
    HotspotResponse,
    OutbreakPoint,
    OutbreakSummary,
    RegionSummary,
    ScanResponse,
    SpikeDetectionResponse,
    TimeSeriesPoint,
)
from app.events.bus import EventBus
from app.repositories.alerts import AlertRepository
from app.repositories.surveillance import SurveillanceRepository
from app.surveillance.alerts import run_scan
from app.surveillance.clustering import ClusterPoint, dbscan
from app.surveillance.repository import OutbreakRepository
from app.surveillance.spikes import SeriesPoint, Severity, detect_spikes

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


# ── Clustering endpoint (B2) ──────────────────────────────────────────────────

@router.get("/hotspots", response_model=HotspotResponse)
async def get_hotspots(
    disease: str | None = Query(
        default=None,
        description="Restrict to one disease slug (e.g. dengue).  Omit for all diseases.",
    ),
    eps_km: float = Query(
        default=settings.hotspot_eps_km,
        gt=0,
        le=50,
        description="Neighbourhood radius in km.  Two reports within this distance are co-located.",
    ),
    min_pts: int = Query(
        default=settings.hotspot_min_pts,
        ge=1,
        le=500,
        description="Min reports in the ε-neighbourhood for a core point.  Fewer → noise.",
    ),
    from_date: datetime | None = Query(default=None, description="Earliest reported_at (inclusive)"),
    to_date: datetime | None = Query(default=None, description="Latest reported_at (inclusive)"),
    repo: SurveillanceRepository = Depends(get_surveillance_repo),
) -> HotspotResponse:
    """
    Run DBSCAN on geolocated disease reports and return outbreak hotspot clusters.

    Each cluster in the response represents a geographic concentration of field
    reports.  The centroid, total case count, member report ids, and bounding
    radius are derived from the raw report coordinates — not from pre-aggregated
    region boundaries.  Noise points (isolated reports below the density
    threshold) are returned separately so the frontend can render them
    distinctly from confirmed hotspots.

    Algorithm: DBSCAN with a K-D tree spatial index.
    Complexity: O(n log n) average over n matching reports.
    """
    reports = await repo.reports_for_clustering(
        disease=disease,
        from_date=from_date,
        to_date=to_date,
    )

    points = [
        ClusterPoint(
            idx=i,
            report_id=r.id,
            lat=float(r.latitude),
            lon=float(r.longitude),
            case_count=r.case_count,
        )
        for i, r in enumerate(reports)
    ]

    results = dbscan(points, eps_km=eps_km, min_pts=min_pts)

    clusters = [
        HotspotCluster(
            cluster_id=c.cluster_id,
            centroid_lat=c.centroid_lat,
            centroid_lon=c.centroid_lon,
            total_cases=c.total_cases,
            report_count=c.report_count,
            radius_km=c.radius_km,
            member_ids=c.member_ids,
        )
        for c in results
        if c.cluster_id >= 0
    ]
    noise_points = [
        HotspotCluster(
            cluster_id=c.cluster_id,
            centroid_lat=c.centroid_lat,
            centroid_lon=c.centroid_lon,
            total_cases=c.total_cases,
            report_count=c.report_count,
            radius_km=c.radius_km,
            member_ids=c.member_ids,
        )
        for c in results
        if c.cluster_id == -1
    ]

    return HotspotResponse(
        clusters=clusters,
        noise_points=noise_points,
        eps_km=eps_km,
        min_pts=min_pts,
        report_count=len(reports),
        cluster_count=len(clusters),
    )


# ── Analytical endpoints (outbreak_timeseries / OWID historical data) ─────────

@router.get("/diseases", response_model=list[DiseaseInfo])
async def list_diseases(
    repo: OutbreakRepository = Depends(get_outbreak_repo),
) -> list[DiseaseInfo]:
    """
    Return one entry per disease with its available regions and date range.
    The frontend uses this to populate the disease selector and region dropdown
    before fetching any time-series data.
    """
    rows = await repo.disease_metadata()
    return [DiseaseInfo(**row) for row in rows]


@router.get("/timeseries", response_model=list[OutbreakPoint])
async def get_timeseries(
    disease: str = Query(description="Disease slug (e.g. covid_19, measles)"),
    region: str = Query(description="Region name (e.g. India, Nigeria)"),
    from_date: str | None = Query(
        default=None,
        description="Start date inclusive (YYYY-MM-DD)",
    ),
    to_date: str | None = Query(
        default=None,
        description="End date inclusive (YYYY-MM-DD)",
    ),
    repo: OutbreakRepository = Depends(get_outbreak_repo),
) -> list[OutbreakPoint]:
    """
    Return ordered time-series (oldest → newest) for one disease × region pair.

    Used by the ECharts frontend to render the case-count area chart.  The
    date parameters accept ISO 8601 date strings (YYYY-MM-DD); omit them to
    get the full available history.
    """
    from datetime import date as _date

    try:
        fd = _date.fromisoformat(from_date) if from_date else None
        td = _date.fromisoformat(to_date) if to_date else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {exc}") from exc

    rows = await repo.timeseries(disease, region, from_date=fd, to_date=td)
    return [
        OutbreakPoint(
            date=r.date.isoformat(),
            case_count=r.case_count,
            deaths=r.deaths,
            source=r.source,
        )
        for r in rows
    ]


@router.get("/summary", response_model=list[OutbreakSummary])
async def outbreak_summary(
    repo: OutbreakRepository = Depends(get_outbreak_repo),
) -> list[OutbreakSummary]:
    """
    Headline stats per disease: total cases, deaths, peak period.
    Used for the stat cards at the top of the surveillance page.
    """
    rows = await repo.summary()
    return [OutbreakSummary(**row) for row in rows]


# ── Spike detection + alerts (B3) ─────────────────────────────────────────────

def _severity_thresholds() -> dict[Severity, float]:
    return {
        Severity.LOW: settings.spike_z_low,
        Severity.MEDIUM: settings.spike_z_medium,
        Severity.HIGH: settings.spike_z_high,
        Severity.CRITICAL: settings.spike_z_critical,
    }


async def _run_detection(
    disease: str,
    region: str,
    repo: OutbreakRepository,
):
    """Shared by /spikes and /scan: load the series and run the detector."""
    rows = await repo.timeseries(disease, region)
    if not rows:
        raise HTTPException(status_code=404, detail="no time-series data for this disease/region")

    points = [SeriesPoint(date=r.date.isoformat(), value=r.case_count) for r in rows]
    detections = detect_spikes(points, window=settings.spike_window_size, thresholds=_severity_thresholds())
    return points, detections


@router.get("/spikes", response_model=list[SpikeDetectionResponse])
async def get_spikes(
    disease: str = Query(description="Disease slug (e.g. covid_19)"),
    region: str = Query(description="Region name (e.g. India)"),
    repo: OutbreakRepository = Depends(get_outbreak_repo),
) -> list[SpikeDetectionResponse]:
    """
    Read-only preview of the z-score detector over one disease+region series.

    Unlike /scan, this does not persist alerts or emit events — it exists so
    the frontend can mark detected spikes on the B1 time-series chart without
    side effects every time the chart re-renders.
    """
    _, detections = await _run_detection(disease, region, repo)
    return [
        SpikeDetectionResponse(
            date=d.date,
            value=d.value,
            rolling_mean=d.rolling_mean,
            rolling_std=d.rolling_std,
            z_score=d.z_score,
            severity=d.severity.value,
        )
        for d in detections
    ]


@router.post("/scan", response_model=ScanResponse)
async def scan_for_spikes(
    disease: str = Query(description="Disease slug (e.g. covid_19)"),
    region: str = Query(description="Region name (e.g. India)"),
    outbreak_repo: OutbreakRepository = Depends(get_outbreak_repo),
    alert_repo: AlertRepository = Depends(get_alert_repo),
    bus: EventBus = Depends(get_bus),
) -> ScanResponse:
    """
    Run the sliding-window z-score detector over one disease+region series,
    persist a severity-tiered alert for each detection, and emit an
    AlertGenerated event for each newly-created one.

    Idempotent: detections that were already turned into alerts by a
    previous scan are skipped (see AlertRepository.create_spike_alert) — they
    still appear in `detections`, but not in `new_alerts`, and produce no
    duplicate event.
    """
    points, detections = await _run_detection(disease, region, outbreak_repo)

    new_alerts = await run_scan(
        disease_name=disease,
        region=region,
        detections=detections,
        window=settings.spike_window_size,
        repo=alert_repo,
        bus=bus,
    )

    return ScanResponse(
        disease_name=disease,
        region=region,
        window=settings.spike_window_size,
        points_scanned=len(points),
        detections=[
            SpikeDetectionResponse(
                date=d.date,
                value=d.value,
                rolling_mean=d.rolling_mean,
                rolling_std=d.rolling_std,
                z_score=d.z_score,
                severity=d.severity.value,
            )
            for d in detections
        ],
        new_alerts=[AlertResponse.model_validate(a) for a in new_alerts],
    )
