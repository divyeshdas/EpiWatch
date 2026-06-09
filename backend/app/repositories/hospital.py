from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas import HospitalCapacityUpdate, HospitalCreate
from app.infra.models import Hospital


class HospitalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, data: HospitalCreate) -> Hospital:
        hospital = Hospital(**data.model_dump())
        self._s.add(hospital)
        await self._s.commit()
        await self._s.refresh(hospital)
        return hospital

    async def get_by_id(self, hospital_id: int) -> Hospital | None:
        result = await self._s.execute(
            select(Hospital).where(Hospital.id == hospital_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, specialization: str | None = None) -> list[Hospital]:
        stmt = select(Hospital).order_by(Hospital.name)
        if specialization:
            # JSONB @> operator: checks if specializations array contains the value
            stmt = stmt.where(Hospital.specializations.contains([specialization]))
        result = await self._s.execute(stmt)
        return list(result.scalars().all())

    async def update_capacity(
        self, hospital_id: int, data: HospitalCapacityUpdate
    ) -> Hospital | None:
        changes = {k: v for k, v in data.model_dump().items() if v is not None}
        if not changes:
            return await self.get_by_id(hospital_id)

        changes["updated_at"] = func.now()
        await self._s.execute(
            update(Hospital).where(Hospital.id == hospital_id).values(**changes)
        )
        await self._s.commit()
        return await self.get_by_id(hospital_id)
