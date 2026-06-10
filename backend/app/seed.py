"""
Seed script: populates the database with realistic Mumbai hospitals.
Run with:  python -m app.seed

Idempotent — skips all inserts if any hospital row already exists.
"""
import asyncio

from sqlalchemy import select

from app.infra.database import get_session_factory
from app.infra.models import Hospital

# Coordinates span the full Mumbai metro: south (Colaba) to north (Mulund/Andheri),
# west (Bandra/Versova) to east (Ghatkopar/Mulund).
_HOSPITALS = [
    {
        "name": "KEM Hospital",
        "latitude": 18.9990,
        "longitude": 72.8408,
        "total_beds": 1800,
        "available_beds": 340,
        "total_icu_beds": 120,
        "available_icu_beds": 28,
        "emergency_capacity": 180,
        "current_load": 1460,
        "specializations": ["general", "trauma", "pediatric"],
        "region": "Dadar",
    },
    {
        "name": "Hinduja Hospital",
        "latitude": 19.0390,
        "longitude": 72.8394,
        "total_beds": 350,
        "available_beds": 85,
        "total_icu_beds": 60,
        "available_icu_beds": 14,
        "emergency_capacity": 60,
        "current_load": 265,
        "specializations": ["cardiac", "general", "orthopedic"],
        "region": "Dharavi",
    },
    {
        "name": "Lilavati Hospital",
        "latitude": 19.0537,
        "longitude": 72.8267,
        "total_beds": 320,
        "available_beds": 72,
        "total_icu_beds": 50,
        "available_icu_beds": 11,
        "emergency_capacity": 55,
        "current_load": 248,
        "specializations": ["general", "oncology", "neurology"],
        "region": "Bandra",
    },
    {
        "name": "Breach Candy Hospital",
        "latitude": 18.9714,
        "longitude": 72.8082,
        "total_beds": 200,
        "available_beds": 45,
        "total_icu_beds": 40,
        "available_icu_beds": 9,
        "emergency_capacity": 40,
        "current_load": 155,
        "specializations": ["pediatric", "general", "cardiac"],
        "region": "Worli",
    },
    {
        "name": "Jaslok Hospital",
        "latitude": 18.9700,
        "longitude": 72.8121,
        "total_beds": 350,
        "available_beds": 88,
        "total_icu_beds": 55,
        "available_icu_beds": 13,
        "emergency_capacity": 65,
        "current_load": 262,
        "specializations": ["cardiac", "oncology", "general"],
        "region": "Worli",
    },
    {
        "name": "Nanavati Hospital",
        "latitude": 19.1019,
        "longitude": 72.8379,
        "total_beds": 350,
        "available_beds": 95,
        "total_icu_beds": 70,
        "available_icu_beds": 18,
        "emergency_capacity": 70,
        "current_load": 255,
        "specializations": ["general", "orthopedic", "trauma"],
        "region": "Andheri",
    },
    {
        "name": "Cooper Hospital",
        "latitude": 19.1063,
        "longitude": 72.8503,
        "total_beds": 1500,
        "available_beds": 280,
        "total_icu_beds": 100,
        "available_icu_beds": 22,
        "emergency_capacity": 150,
        "current_load": 1220,
        "specializations": ["general", "trauma", "pediatric"],
        "region": "Andheri",
    },
    {
        "name": "Bombay Hospital",
        "latitude": 18.9381,
        "longitude": 72.8230,
        "total_beds": 450,
        "available_beds": 110,
        "total_icu_beds": 80,
        "available_icu_beds": 20,
        "emergency_capacity": 80,
        "current_load": 340,
        "specializations": ["cardiac", "general", "neurology"],
        "region": "Worli",
    },
    {
        "name": "Seven Hills Hospital",
        "latitude": 19.1133,
        "longitude": 72.8695,
        "total_beds": 1500,
        "available_beds": 320,
        "total_icu_beds": 150,
        "available_icu_beds": 35,
        "emergency_capacity": 160,
        "current_load": 1180,
        "specializations": ["general", "trauma", "oncology"],
        "region": "Andheri",
    },
    {
        "name": "Wockhardt Hospital Mulund",
        "latitude": 19.1647,
        "longitude": 72.9545,
        "total_beds": 300,
        "available_beds": 78,
        "total_icu_beds": 60,
        "available_icu_beds": 15,
        "emergency_capacity": 55,
        "current_load": 222,
        "specializations": ["cardiac", "general", "orthopedic"],
        "region": "Mulund",
    },
]


async def seed() -> None:
    async with get_session_factory()() as db:
        existing = await db.execute(select(Hospital).limit(1))
        if existing.scalar_one_or_none() is not None:
            print("hospitals table already seeded — skipping")
            return

        for row in _HOSPITALS:
            db.add(Hospital(**row))

        await db.commit()
        print(f"seeded {len(_HOSPITALS)} hospitals")


if __name__ == "__main__":
    asyncio.run(seed())
