from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.bus import EventBus
from app.infra.database import get_db
from app.repositories.hospital import HospitalRepository
from app.repositories.emergency import EmergencyCaseRepository


def get_bus() -> EventBus:
    from app.main import bus
    if bus is None:
        raise HTTPException(status_code=503, detail="service unavailable")
    return bus


def get_hospital_repo(db: AsyncSession = Depends(get_db)) -> HospitalRepository:
    return HospitalRepository(db)


def get_emergency_repo(db: AsyncSession = Depends(get_db)) -> EmergencyCaseRepository:
    return EmergencyCaseRepository(db)
