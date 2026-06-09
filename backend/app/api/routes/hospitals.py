from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_bus, get_hospital_repo
from app.domain.events import Event, EventType
from app.domain.schemas import HospitalCapacityUpdate, HospitalCreate, HospitalResponse
from app.events.bus import EventBus
from app.repositories.hospital import HospitalRepository

router = APIRouter(prefix="/hospitals", tags=["hospitals"])


@router.post("", response_model=HospitalResponse, status_code=201)
async def register_hospital(
    data: HospitalCreate,
    repo: HospitalRepository = Depends(get_hospital_repo),
    bus: EventBus = Depends(get_bus),
) -> HospitalResponse:
    hospital = await repo.create(data)
    await bus.publish(Event(
        type=EventType.HOSPITAL_UPDATED,
        payload={"hospital_id": hospital.id, "name": hospital.name, "action": "registered"},
    ))
    return HospitalResponse.model_validate(hospital)


@router.get("", response_model=list[HospitalResponse])
async def list_hospitals(
    specialization: str | None = None,
    repo: HospitalRepository = Depends(get_hospital_repo),
) -> list[HospitalResponse]:
    hospitals = await repo.list_all(specialization=specialization)
    return [HospitalResponse.model_validate(h) for h in hospitals]


@router.get("/{hospital_id}", response_model=HospitalResponse)
async def get_hospital(
    hospital_id: int,
    repo: HospitalRepository = Depends(get_hospital_repo),
) -> HospitalResponse:
    hospital = await repo.get_by_id(hospital_id)
    if hospital is None:
        raise HTTPException(status_code=404, detail="hospital not found")
    return HospitalResponse.model_validate(hospital)


@router.patch("/{hospital_id}", response_model=HospitalResponse)
async def update_hospital_capacity(
    hospital_id: int,
    data: HospitalCapacityUpdate,
    repo: HospitalRepository = Depends(get_hospital_repo),
    bus: EventBus = Depends(get_bus),
) -> HospitalResponse:
    hospital = await repo.update_capacity(hospital_id, data)
    if hospital is None:
        raise HTTPException(status_code=404, detail="hospital not found")
    await bus.publish(Event(
        type=EventType.HOSPITAL_UPDATED,
        payload={
            "hospital_id": hospital.id,
            "name": hospital.name,
            "available_beds": hospital.available_beds,
            "available_icu_beds": hospital.available_icu_beds,
            "current_load": hospital.current_load,
        },
    ))
    return HospitalResponse.model_validate(hospital)
