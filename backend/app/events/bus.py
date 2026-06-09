"""
EventBus — the swappable pub/sub interface.

Design intent:
  Callers depend only on this abstract class. The concrete implementation
  (RedisEventBus today, Kafka tomorrow) is wired up once in main.py lifespan
  and injected wherever needed. Swapping the backend requires changing exactly
  one line in main.py — no caller changes.

  publish(event)    → send an event into the bus
  subscribe(handler) → register a coroutine that receives every event
"""
from abc import ABC, abstractmethod
from collections.abc import Callable, Awaitable

from app.domain.events import Event

Handler = Callable[[Event], Awaitable[None]]


class EventBus(ABC):
    @abstractmethod
    async def publish(self, event: Event) -> None: ...

    @abstractmethod
    def subscribe(self, handler: Handler) -> None: ...
