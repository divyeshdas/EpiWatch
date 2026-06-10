from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_bus, get_emergency_repo, get_hospital_repo
from app.infra.models import EmergencyCase, Hospital
from app.main import app
from app.scoring import surge


def _hospital(overrides: dict | None = None) -> Hospital:
    h = Hospital(
        id=1,
        name="Test Hospital",
        latitude=19.04,
        longitude=72.85,
        total_beds=200,
        available_beds=50,
        total_icu_beds=30,
        available_icu_beds=8,
        emergency_capacity=40,
        current_load=150,
        specializations=["general", "trauma"],
        region=None,
        updated_at=datetime.now(timezone.utc),
    )
    for k, v in (overrides or {}).items():
        setattr(h, k, v)
    return h


def _case(overrides: dict | None = None) -> EmergencyCase:
    c = EmergencyCase(
        id=1,
        latitude=19.07,
        longitude=72.88,
        patient_condition="CRITICAL",
        status="PENDING",
        created_at=datetime.now(timezone.utc),
        assigned_hospital_id=None,
    )
    for k, v in (overrides or {}).items():
        setattr(c, k, v)
    return c


@pytest.fixture(autouse=True)
def _reset_surge_state():
    """Surge state is a module-level store (app.scoring.surge) so it doesn't
    leak between tests."""
    surge.clear()
    yield
    surge.clear()


@pytest.fixture
def mock_bus():
    return AsyncMock()


@pytest.fixture
def mock_hospital_repo():
    return AsyncMock()


@pytest.fixture
def mock_emergency_repo():
    return AsyncMock()


@pytest.fixture
def client(mock_bus, mock_hospital_repo, mock_emergency_repo):
    app.dependency_overrides[get_bus] = lambda: mock_bus
    app.dependency_overrides[get_hospital_repo] = lambda: mock_hospital_repo
    app.dependency_overrides[get_emergency_repo] = lambda: mock_emergency_repo
    yield TestClient(app)
    app.dependency_overrides.clear()


# expose helpers so test modules can import them
make_hospital = _hospital
make_case = _case
