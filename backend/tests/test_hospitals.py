from app.domain.events import EventType
from tests.conftest import make_hospital

_CREATE_PAYLOAD = {
    "name": "Test Hospital",
    "latitude": 19.04,
    "longitude": 72.85,
    "total_beds": 200,
    "available_beds": 50,
    "total_icu_beds": 30,
    "available_icu_beds": 8,
    "emergency_capacity": 40,
    "current_load": 150,
    "specializations": ["general", "trauma"],
}


def test_create_hospital_returns_201(client, mock_hospital_repo):
    mock_hospital_repo.create.return_value = make_hospital()
    resp = client.post("/hospitals", json=_CREATE_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == 1
    assert body["name"] == "Test Hospital"


def test_create_hospital_emits_hospital_updated(client, mock_hospital_repo, mock_bus):
    mock_hospital_repo.create.return_value = make_hospital()
    client.post("/hospitals", json=_CREATE_PAYLOAD)
    mock_bus.publish.assert_called_once()
    event = mock_bus.publish.call_args[0][0]
    assert event.type == EventType.HOSPITAL_UPDATED
    assert event.payload["hospital_id"] == 1


def test_list_hospitals(client, mock_hospital_repo):
    mock_hospital_repo.list_all.return_value = [make_hospital(), make_hospital({"id": 2, "name": "Other"})]
    resp = client.get("/hospitals")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_hospitals_passes_specialization_filter(client, mock_hospital_repo):
    mock_hospital_repo.list_all.return_value = []
    client.get("/hospitals?specialization=cardiac")
    mock_hospital_repo.list_all.assert_called_once_with(specialization="cardiac")


def test_get_hospital_found(client, mock_hospital_repo):
    mock_hospital_repo.get_by_id.return_value = make_hospital()
    resp = client.get("/hospitals/1")
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


def test_get_hospital_not_found(client, mock_hospital_repo):
    mock_hospital_repo.get_by_id.return_value = None
    resp = client.get("/hospitals/99")
    assert resp.status_code == 404


def test_patch_hospital_returns_updated(client, mock_hospital_repo):
    updated = make_hospital({"available_beds": 30, "current_load": 170})
    mock_hospital_repo.update_capacity.return_value = updated
    resp = client.patch("/hospitals/1", json={"available_beds": 30, "current_load": 170})
    assert resp.status_code == 200
    assert resp.json()["available_beds"] == 30
    assert resp.json()["current_load"] == 170


def test_patch_hospital_emits_hospital_updated(client, mock_hospital_repo, mock_bus):
    mock_hospital_repo.update_capacity.return_value = make_hospital({"available_beds": 30})
    client.patch("/hospitals/1", json={"available_beds": 30})
    mock_bus.publish.assert_called_once()
    event = mock_bus.publish.call_args[0][0]
    assert event.type == EventType.HOSPITAL_UPDATED


def test_patch_hospital_not_found(client, mock_hospital_repo):
    mock_hospital_repo.update_capacity.return_value = None
    resp = client.patch("/hospitals/99", json={"available_beds": 10})
    assert resp.status_code == 404
