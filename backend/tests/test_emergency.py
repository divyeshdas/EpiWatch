from app.domain.events import EventType
from tests.conftest import make_case

_CREATE_PAYLOAD = {
    "latitude": 19.07,
    "longitude": 72.88,
    "patient_condition": "CRITICAL",
}


def test_report_emergency_returns_201(client, mock_emergency_repo):
    mock_emergency_repo.create.return_value = make_case()
    resp = client.post("/emergency", json=_CREATE_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == 1
    assert body["patient_condition"] == "CRITICAL"
    assert body["status"] == "PENDING"
    assert body["assigned_hospital_id"] is None


def test_report_emergency_emits_emergency_reported(client, mock_emergency_repo, mock_bus):
    mock_emergency_repo.create.return_value = make_case()
    client.post("/emergency", json=_CREATE_PAYLOAD)
    mock_bus.publish.assert_called_once()
    event = mock_bus.publish.call_args[0][0]
    assert event.type == EventType.EMERGENCY_REPORTED
    assert event.payload["case_id"] == 1
    assert event.payload["patient_condition"] == "CRITICAL"


def test_list_emergencies(client, mock_emergency_repo):
    mock_emergency_repo.list_all.return_value = [make_case(), make_case({"id": 2})]
    resp = client.get("/emergency")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_emergency_found(client, mock_emergency_repo):
    mock_emergency_repo.get_by_id.return_value = make_case()
    resp = client.get("/emergency/1")
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


def test_get_emergency_not_found(client, mock_emergency_repo):
    mock_emergency_repo.get_by_id.return_value = None
    resp = client.get("/emergency/99")
    assert resp.status_code == 404


def test_invalid_patient_condition_rejected(client, mock_emergency_repo):
    resp = client.post("/emergency", json={**_CREATE_PAYLOAD, "patient_condition": "UNKNOWN"})
    assert resp.status_code == 422
