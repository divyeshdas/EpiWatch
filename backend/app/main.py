import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.events.redis_backend import RedisEventBus
from app.api.routes import ws, demo, hospitals, emergency, graph, route, surveillance
from app.graph.loader import load_graph
from app.infra.database import get_session_factory

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

bus: RedisEventBus | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bus

    # event bus
    bus = RedisEventBus(settings.redis_url)
    bus.subscribe(ws.manager.broadcast)
    asyncio.create_task(bus.listen())

    # road graph (no-op if ingest hasn't been run yet)
    async with get_session_factory()() as db:
        await load_graph(db)

    logger.info("EpiWatch backend ready")
    yield
    logger.info("EpiWatch backend shutting down")


app = FastAPI(title="EpiWatch API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws.router)
app.include_router(demo.router, prefix="/demo", tags=["demo"])
app.include_router(hospitals.router)
app.include_router(emergency.router)
app.include_router(graph.router)
app.include_router(route.router)
app.include_router(surveillance.router)
