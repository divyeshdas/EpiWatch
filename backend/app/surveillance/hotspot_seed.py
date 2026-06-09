"""
B2 hotspot seed: adds geolocated disease_reports designed to produce
visually distinct DBSCAN clusters and genuine noise points.

The base surveillance_seed.py already populates ~3 000 reports across
15 Mumbai regions, which cluster naturally by neighbourhood.  This seed
adds five isolated reports placed 10–20 km from the nearest cluster so
that the hotspot map clearly shows the difference between a computed
cluster and an unclassified noise point.

Run with:  python -m app.surveillance.hotspot_seed

Idempotent — skips all inserts if the sentinel record already exists.
"""
import asyncio
import random
from datetime import datetime, timezone

from sqlalchemy import select

from app.infra.database import get_session_factory
from app.infra.models import DiseaseReport

_SENTINEL_REGION = "Alibag_Isolated"   # unique to this seed; used as idempotency check

_RNG_SEED = 99
_BASE_TIME = datetime(2025, 12, 1, 8, 0, 0, tzinfo=timezone.utc)

# Five genuinely isolated reports placed well outside the 15-region Mumbai
# metro cluster (each ≥ 10 km from the nearest base-seed region).
# At eps=2 km these will not connect to any cluster → labelled noise.
_NOISE_POINTS: list[dict] = [
    {
        "disease_name": "dengue",
        "region": _SENTINEL_REGION,   # Alibag coastal area, ~22 km south of Worli
        "latitude":  18.648,
        "longitude": 72.872,
        "case_count": 2,
    },
    {
        "disease_name": "malaria",
        "region": "Badlapur_Isolated",  # ~25 km north of Kalyan
        "latitude":  19.428,
        "longitude": 73.198,
        "case_count": 1,
    },
    {
        "disease_name": "typhoid",
        "region": "Panvel_Isolated",    # ~13 km south-east of Navi Mumbai
        "latitude":  18.988,
        "longitude": 73.117,
        "case_count": 3,
    },
    {
        "disease_name": "cholera",
        "region": "Vasai_Isolated",     # ~17 km north-west of Borivali
        "latitude":  19.388,
        "longitude": 72.804,
        "case_count": 1,
    },
    {
        "disease_name": "leptospirosis",
        "region": "Khopoli_Isolated",   # ~22 km east of Kalyan
        "latitude":  18.787,
        "longitude": 73.345,
        "case_count": 2,
    },
]


def _build_rows() -> list[dict]:
    rng = random.Random(_RNG_SEED)
    rows: list[dict] = []
    for pt in _NOISE_POINTS:
        jitter_lat = rng.uniform(-0.001, 0.001)
        jitter_lon = rng.uniform(-0.001, 0.001)
        rows.append({
            "disease_name": pt["disease_name"],
            "region":       pt["region"],
            "latitude":     pt["latitude"] + jitter_lat,
            "longitude":    pt["longitude"] + jitter_lon,
            "case_count":   pt["case_count"],
            "reported_at":  _BASE_TIME,
        })
    return rows


async def seed() -> None:
    async with get_session_factory()() as db:
        existing = await db.execute(
            select(DiseaseReport)
            .where(DiseaseReport.region == _SENTINEL_REGION)
            .limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            print("hotspot seed already present — skipping")
            return

        rows = _build_rows()
        for row in rows:
            db.add(DiseaseReport(**row))
        await db.commit()
        print(f"hotspot seed: inserted {len(rows)} isolated noise reports")


if __name__ == "__main__":
    asyncio.run(seed())
