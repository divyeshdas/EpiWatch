from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas import EmergencyCaseCreate
from app.infra.models import EmergencyCase


class EmergencyCaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, data: EmergencyCaseCreate) -> EmergencyCase:
        case = EmergencyCase(**data.model_dump())
        self._s.add(case)
        await self._s.commit()
        await self._s.refresh(case)
        return case

    async def get_by_id(self, case_id: int) -> EmergencyCase | None:
        result = await self._s.execute(
            select(EmergencyCase).where(EmergencyCase.id == case_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[EmergencyCase]:
        result = await self._s.execute(
            select(EmergencyCase).order_by(EmergencyCase.created_at.desc())
        )
        return list(result.scalars().all())

    async def assign(self, case_id: int, hospital_id: int) -> EmergencyCase | None:
        """Set assigned_hospital_id and transition status to ASSIGNED."""
        await self._s.execute(
            update(EmergencyCase)
            .where(EmergencyCase.id == case_id)
            .values(assigned_hospital_id=hospital_id, status="ASSIGNED")
        )
        await self._s.commit()
        return await self.get_by_id(case_id)
