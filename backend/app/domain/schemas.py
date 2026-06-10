from datetime import date, datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class PatientCondition(str, Enum):
    STABLE = "STABLE"
    SERIOUS = "SERIOUS"
    CRITICAL = "CRITICAL"
    CARDIAC = "CARDIAC"


# ── Hospital ─────────────────────────────────────────────────────────────────

class HospitalCreate(BaseModel):
    name: str
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    total_beds: Annotated[int, Field(ge=0)]
    available_beds: Annotated[int, Field(ge=0)]
    total_icu_beds: Annotated[int, Field(ge=0)]
    available_icu_beds: Annotated[int, Field(ge=0)]
    emergency_capacity: Annotated[int, Field(ge=0)]
    current_load: Annotated[int, Field(ge=0)] = 0
    specializations: list[str] = []


class HospitalCapacityUpdate(BaseModel):
    """Fields a hospital (data provider) may update. All optional for PATCH semantics."""
    available_beds: Annotated[int, Field(ge=0)] | None = None
    available_icu_beds: Annotated[int, Field(ge=0)] | None = None
    current_load: Annotated[int, Field(ge=0)] | None = None
    emergency_capacity: Annotated[int, Field(ge=0)] | None = None


class HospitalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    latitude: float
    longitude: float
    total_beds: int
    available_beds: int
    total_icu_beds: int
    available_icu_beds: int
    emergency_capacity: int
    current_load: int
    specializations: list[str]
    updated_at: datetime


# ── Emergency case ────────────────────────────────────────────────────────────

class EmergencyCaseCreate(BaseModel):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    patient_condition: PatientCondition


class EmergencyCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    latitude: float
    longitude: float
    patient_condition: str
    status: str
    created_at: datetime
    assigned_hospital_id: int | None


# ── Graph ─────────────────────────────────────────────────────────────────────

class NearestNodeRequest(BaseModel):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class NearestNodeResponse(BaseModel):
    node_id: int
    latitude: float
    longitude: float
    distance_m: float


class GraphStatsResponse(BaseModel):
    node_count: int
    edge_count: int
    bounding_box: dict[str, float]


# ── Routing ───────────────────────────────────────────────────────────────────

class RouteRequest(BaseModel):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    hospital_id: int


class RouteNode(BaseModel):
    node_id: int
    latitude: float
    longitude: float


class RouteDetail(BaseModel):
    path: list[RouteNode]
    total_distance_m: float
    total_travel_time_s: float
    node_count: int


class RouteResponse(BaseModel):
    route: RouteDetail | None
    reason: str | None = None


# ── Hospital scoring / assignment ─────────────────────────────────────────────

class FactorScoreResponse(BaseModel):
    """One factor's contribution to a hospital's total score."""
    raw: float           # Actual measurement before normalization
    penalty: float       # Mapped to [0, 1]: 0 = ideal, 1 = worst
    weight: float        # Condition-keyed weight applied
    contribution: float  # penalty × weight — this factor's slice of total_score


class ScoredHospitalResponse(BaseModel):
    """A hospital that passed filtering, with its route and explainable breakdown."""
    hospital_id: int
    hospital_name: str
    rank: int            # 1 = best (lowest score) — rank 1 is the assignment winner
    total_score: float   # Weighted sum of penalty factors; lower is better; ∈ [0, 1]
    travel_time_s: float
    distance_m: float
    path: list[RouteNode]
    # Per-factor breakdown keyed by name: travel_time, bed_availability,
    # icu_availability, load_factor, specialization
    factors: dict[str, FactorScoreResponse]


class FilteredHospitalResponse(BaseModel):
    """A hospital that was excluded before scoring, with its disqualification reason."""
    hospital_id: int
    hospital_name: str
    reason: str


# ── Surveillance / disease reports ───────────────────────────────────────────

class DiseaseReportCreate(BaseModel):
    disease_name: str = Field(min_length=1)
    region: str = Field(min_length=1)
    latitude: Annotated[float, Field(ge=-90, le=90)] | None = None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None = None
    case_count: Annotated[int, Field(ge=1)]
    reported_at: datetime | None = None


class DiseaseReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    disease_name: str
    region: str
    latitude: float | None
    longitude: float | None
    case_count: int
    reported_at: datetime


class RegionSummary(BaseModel):
    """Aggregated totals per region — used by B2 clustering."""
    region: str
    latitude: float | None
    longitude: float | None
    total_cases: int
    report_count: int
    diseases: list[str]


class TimeSeriesPoint(BaseModel):
    """Daily case count — used by B3 spike detection."""
    date: str          # ISO 8601 date string (YYYY-MM-DD)
    total_cases: int
    report_count: int


# ── Outbreak time-series (analytical, OWID-derived) ──────────────────────────

class DiseaseInfo(BaseModel):
    """Available disease metadata — used to populate frontend selectors."""
    disease_name: str
    regions: list[str]
    date_from: str   # YYYY-MM-DD of earliest record
    date_to: str     # YYYY-MM-DD of latest record
    total_records: int


class OutbreakPoint(BaseModel):
    """One observation in a disease × region time series."""
    date: str        # YYYY-MM-DD
    case_count: int
    deaths: int
    source: str


class OutbreakSummary(BaseModel):
    """Aggregate stats per disease — used for headline stat cards."""
    disease_name: str
    total_cases: int
    total_deaths: int
    peak_cases: int
    peak_date: str | None
    record_count: int


class HotspotCluster(BaseModel):
    """One DBSCAN cluster (or one noise point when cluster_id == -1)."""
    cluster_id: int
    centroid_lat: float
    centroid_lon: float
    total_cases: int
    report_count: int
    radius_km: float
    member_ids: list[int]


class HotspotResponse(BaseModel):
    """Full response for GET /surveillance/hotspots."""
    clusters: list[HotspotCluster]       # cluster_id >= 0, sorted total_cases desc
    noise_points: list[HotspotCluster]   # cluster_id == -1, one per isolated report
    eps_km: float
    min_pts: int
    report_count: int                    # total reports fed into the algorithm
    cluster_count: int                   # number of real clusters (excludes noise)


# ── Spike detection / alerts (B3) ────────────────────────────────────────────

class SpikeDetectionResponse(BaseModel):
    """One anomalous point flagged by the z-score detector."""
    date: str          # YYYY-MM-DD
    value: int
    rolling_mean: float
    rolling_std: float
    z_score: float
    severity: str       # LOW | MEDIUM | HIGH | CRITICAL


class AlertResponse(BaseModel):
    """One row from the alerts table."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    severity: str
    message: str
    region: str | None
    disease_name: str | None
    event_date: date | None
    z_score: float | None
    created_at: datetime
    resolved_at: datetime | None


class ScanResponse(BaseModel):
    """Full result of POST /surveillance/scan."""
    disease_name: str
    region: str
    window: int
    points_scanned: int
    detections: list[SpikeDetectionResponse]
    new_alerts: list[AlertResponse]   # only newly-created alerts (idempotent re-scans -> [])


class AssignmentResponse(BaseModel):
    """
    Full result of POST /emergency/{id}/assign.

    candidates is a ranked list (rank 1 = chosen hospital, rank 2 = next-best, etc.)
    filtered_out shows which hospitals were excluded and why.
    This breakdown lets a dispatcher see at a glance *why* a specific hospital
    was chosen and what alternatives were available.
    """
    emergency_id: int
    assigned_hospital_id: int | None
    status: str                               # "ASSIGNED" or "NO_CANDIDATES"
    reason: str | None = None                 # set when no candidates passed filtering
    condition: str                            # patient condition that drove the weights
    candidates: list[ScoredHospitalResponse]  # ranked best → worst
    filtered_out: list[FilteredHospitalResponse]
