"""
Surge state — the event-driven bridge from Pillar B (surveillance) to
Pillar A (routing/scoring).

This module owns the only piece of mutable state that crosses the pillar
boundary, and it is deliberately small: a region -> active surge mapping,
written exclusively by an event-bus subscriber and read synchronously by the
hospital scorer.

How it gets populated
----------------------
This module never imports anything from app.surveillance.  When B3's spike
detector raises an OUTBREAK_SPIKE alert, app.surveillance.alerts.run_scan
publishes an AlertGenerated event on the shared bus (app.domain.events).
main.py subscribes handle_alert_generated (below) to that bus on startup,
alongside the websocket broadcaster.  The handler reads the event payload --
region, severity, disease_name, event_date -- and calls record_surge().

Nothing in app.scoring ever calls into app.surveillance, and nothing in
app.surveillance ever imports app.scoring.  The only thing both sides share
is Event/EventType, the spine both pillars already depend on.

Severity -> surge level
------------------------
B3 severities are the strings LOW / MEDIUM / HIGH / CRITICAL
(app.surveillance.spikes.Severity.value).  SEVERITY_TO_LEVEL maps each to a
surge level in [0, 1]: how strongly the scorer should penalise hospitals in
that region.  CRITICAL maps to 1.0 (the full surge weight applies); LOW is a
small nudge.  An unrecognised severity is ignored.

TTL / decay
-----------
A surge does not persist forever.  If no new alert refreshes a region within
settings.surge_ttl_seconds, get_surge() reports level 0 again -- the surge has
"faded".  This models an outbreak signal going stale: the router shouldn't
keep avoiding a region indefinitely because of one alert raised hours ago.

Complexity
----------
record_surge / get_surge are O(1) -- a single dict lookup keyed by region.
Space is O(R) for R distinct regions with an active surge.
"""
from __future__ import annotations

from dataclasses import dataclass
import time

from app.config import settings
from app.domain.events import Event, EventType

# B3 alert severities -> surge level in [0, 1].  Higher severity means the
# affected region is closer to (or already at) hospital saturation, so
# candidates there should be penalised more heavily.
SEVERITY_TO_LEVEL: dict[str, float] = {
    "LOW": 0.15,
    "MEDIUM": 0.4,
    "HIGH": 0.7,
    "CRITICAL": 1.0,
}


@dataclass
class SurgeInfo:
    """Current surge state for one region, as seen by the scorer."""
    region: str | None
    level: float = 0.0            # in [0, 1]; 0 = no active surge
    severity: str | None = None   # the alert severity that set this level
    disease_name: str | None = None
    event_date: str | None = None


@dataclass
class _SurgeRecord:
    severity: str
    disease_name: str | None
    event_date: str | None
    expires_at: float


# region -> active surge.  Mutated only by handle_alert_generated (the
# event-bus subscriber) -- never written to directly from request-handling
# code.  This is what makes the update "event-driven" rather than a direct
# function call from surveillance into scoring.
_surge_by_region: dict[str, _SurgeRecord] = {}


def record_surge(
    region: str,
    severity: str,
    disease_name: str | None = None,
    event_date: str | None = None,
    *,
    now: float | None = None,
) -> None:
    """
    Record (or refresh) an active surge for `region`.

    A later alert always replaces the previous record for that region, even
    if its severity is lower -- the surge state reflects the *most recent*
    signal, not the worst-ever-seen one. Unknown severities are ignored
    (defensive: the payload comes from Pillar B but the scorer doesn't trust
    it blindly).
    """
    if severity not in SEVERITY_TO_LEVEL:
        return
    now = now if now is not None else time.time()
    _surge_by_region[region] = _SurgeRecord(
        severity=severity,
        disease_name=disease_name,
        event_date=event_date,
        expires_at=now + settings.surge_ttl_seconds,
    )


def get_surge(region: str | None, *, now: float | None = None) -> SurgeInfo:
    """
    Return the current surge state for `region`.

    Level is 0 if the hospital has no region, no surge was ever recorded for
    it, or the recorded surge has expired (TTL passed without a refreshing
    alert).
    """
    if region is None:
        return SurgeInfo(region=None)

    record = _surge_by_region.get(region)
    now = now if now is not None else time.time()
    if record is None or record.expires_at <= now:
        return SurgeInfo(region=region)

    return SurgeInfo(
        region=region,
        level=SEVERITY_TO_LEVEL[record.severity],
        severity=record.severity,
        disease_name=record.disease_name,
        event_date=record.event_date,
    )


def clear() -> None:
    """Reset all surge state. Used between tests."""
    _surge_by_region.clear()


async def handle_alert_generated(event: Event) -> None:
    """
    Event-bus subscriber: AlertGenerated -> record_surge.

    This is the only way surge state changes in production. It is subscribed
    once, in main.py's lifespan, alongside the websocket broadcaster: B3's
    run_scan publishes AlertGenerated, this handler reacts to it, and the
    next score_hospitals() call for a hospital in that region picks up the
    new surge level. Surveillance and scoring never call each other directly
    -- this handler is the entire bridge.
    """
    if event.type != EventType.ALERT_GENERATED:
        return

    region = event.payload.get("region")
    severity = event.payload.get("severity")
    if not region or not severity:
        return

    record_surge(
        region=region,
        severity=severity,
        disease_name=event.payload.get("disease_name"),
        event_date=event.payload.get("event_date"),
    )
