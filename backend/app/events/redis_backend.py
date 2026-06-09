"""
Redis Pub/Sub implementation of EventBus.

How fan-out works across processes:
  1. publish() serialises the Event to JSON and pushes it to a Redis channel
     ("epiwatch:events"). This is O(1) — Redis does the broadcast.
  2. listen() is a long-running coroutine (started as an asyncio Task in
     main.py lifespan). It subscribes to the same channel and, for every
     message, deserialises the event and calls each registered handler.
  3. The only registered handler in Phase 0 is ConnectionManager.broadcast,
     which sends the JSON payload to every active WebSocket client.

  Because publish() talks to Redis (not to handlers directly), this works
  correctly when the backend scales to multiple processes — each process runs
  its own listen() loop, so every process fans out to its own WS clients.
  The message travels: HTTP → Redis channel → all backend processes → all
  WebSocket clients attached to each process.

  To swap to Kafka: implement EventBus, publish to a Kafka topic, consume in
  listen(). Callers are unchanged.
"""
import json
import logging

import redis.asyncio as aioredis

from app.domain.events import Event, EventType
from app.events.bus import EventBus, Handler

logger = logging.getLogger(__name__)
_CHANNEL = "epiwatch:events"


class RedisEventBus(EventBus):
    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._handlers: list[Handler] = []

    async def publish(self, event: Event) -> None:
        data = json.dumps({
            "type": event.type,
            "payload": event.payload,
            "timestamp": event.timestamp,
        })
        await self._redis.publish(_CHANNEL, data)
        logger.debug("published %s", event.type)

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def listen(self) -> None:
        """Run as a background asyncio Task — never returns under normal operation."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(_CHANNEL)
        logger.info("Redis listener ready on channel %s", _CHANNEL)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                raw = json.loads(message["data"])
                event = Event(
                    type=EventType(raw["type"]),
                    payload=raw.get("payload", {}),
                    timestamp=raw.get("timestamp", 0.0),
                )
                for handler in self._handlers:
                    await handler(event)
            except Exception:
                logger.exception("error dispatching event from Redis")
