from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time


class EventType(str, Enum):
    HOSPITAL_UPDATED = "HospitalUpdated"
    EMERGENCY_REPORTED = "EmergencyReported"
    AMBULANCE_ASSIGNED = "AmbulanceAssigned"
    ROUTE_COMPUTED = "RouteComputed"
    OUTBREAK_DETECTED = "OutbreakDetected"
    HOTSPOT_RECOMPUTED = "HotspotRecomputed"
    ALERT_GENERATED = "AlertGenerated"
    DEMO_PING = "DemoPing"


@dataclass
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
