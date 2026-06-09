from datetime import datetime
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
