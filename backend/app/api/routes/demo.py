import time

from fastapi import APIRouter, HTTPException

from app.domain.events import Event, EventType

router = APIRouter()


@router.post("/ping")
async def demo_ping() -> dict:
    """Emit a DemoPing event — proves the HTTP → event bus → Redis → WS → client chain works."""
    from app.main import bus  # late import avoids circular reference at module load time

    if bus is None:
        raise HTTPException(status_code=503, detail="event bus not ready")

    event = Event(
        type=EventType.DEMO_PING,
        payload={"message": "pong", "ts": time.time()},
    )
    await bus.publish(event)
    return {"status": "published", "event": event.type}
