"""
Alert engine — turns spike detections into persisted alerts and emits
AlertGenerated events for the ones that are new.

This module is the bridge between the pure detector (app.surveillance.spikes,
no I/O, no side effects) and the outside world: it writes rows via
AlertRepository and publishes onto the EventBus so the live frontend feed
sees new alerts as they're created.

Idempotency is enforced one layer down (AlertRepository.create_spike_alert,
backed by a unique constraint) — this module just respects the None it gets
back for a duplicate and does not publish an event for it.  That is also why
re-scanning is safe to call as often as you like: every detection is
re-evaluated, but only genuinely new ones produce a row + event.
"""
from __future__ import annotations

from app.domain.events import Event, EventType
from app.events.bus import EventBus
from app.repositories.alerts import AlertRepository
from app.surveillance.spikes import SENTINEL_Z, SpikeDetection


def _format_message(disease_name: str, region: str, detection: SpikeDetection, window: int) -> str:
    if detection.z_score >= SENTINEL_Z:
        magnitude = "far"
    else:
        magnitude = f"{detection.z_score:.1f}σ"
    return (
        f"{disease_name} in {region}: cases {magnitude} above "
        f"{window}-month baseline on {detection.date}"
    )


async def run_scan(
    disease_name: str,
    region: str,
    detections: list[SpikeDetection],
    window: int,
    repo: AlertRepository,
    bus: EventBus,
) -> list[dict]:
    """
    Persist one alert per detection (deduped) and emit AlertGenerated for
    each newly-created one.  Returns the list of newly-created alert dicts
    (empty on a fully-idempotent re-scan).
    """
    new_alerts: list[dict] = []

    for detection in detections:
        alert = await repo.create_spike_alert(
            disease_name=disease_name,
            region=region,
            event_date=detection.date,
            severity=detection.severity.value,
            z_score=detection.z_score,
            message=_format_message(disease_name, region, detection, window),
        )
        if alert is None:
            continue  # duplicate from a prior scan — no new row, no event

        new_alerts.append(alert)
        await bus.publish(Event(
            type=EventType.ALERT_GENERATED,
            payload={
                "alert_id": alert["id"],
                "type": alert["type"],
                "severity": alert["severity"],
                "message": alert["message"],
                "region": alert["region"],
                "disease_name": alert["disease_name"],
                "event_date": alert["event_date"],
                "z_score": alert["z_score"],
                "created_at": alert["created_at"].isoformat(),
            },
        ))

    return new_alerts
