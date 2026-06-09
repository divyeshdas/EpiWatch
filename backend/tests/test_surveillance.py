"""
Tests for Pillar B Phase 1 — Surveillance data layer.

Coverage:
  SurveillanceRepository:
    - create (returns persisted model)
    - get_by_id (found / not found)
    - list_reports (no filters, disease filter, region filter, date filters, limit)
    - aggregate_by_region (structure, disease filter)
    - time_series (structure, disease filter, day window)

  Surveillance API:
    POST /surveillance/reports   — 201 response, event emitted, validation errors
    GET  /surveillance/reports   — list with filters
    GET  /surveillance/reports/{id}  — found / 404
    GET  /surveillance/summary/by-region   — shape and field presence
    GET  /surveillance/summary/time-series — shape and field presence
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_bus, get_emergency_repo, get_hospital_repo, get_surveillance_repo
from app.domain.events import EventType
from app.infra.models import DiseaseReport
from app.main import app
from app.repositories.surveillance import SurveillanceRepository


# ── helpers ───────────────────────────────────────────────────────────────────

def _report(**overrides) -> DiseaseReport:
    r = DiseaseReport(
        id=1,
        disease_name="dengue",
        region="Dharavi",
        latitude=19.0415,
        longitude=72.8540,
        case_count=42,
        reported_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    for k, v in overrides.items():
        setattr(r, k, v)
    return r


# ── SurveillanceRepository unit tests ────────────────────────────────────────


class TestSurveillanceRepositoryCreate:
    @pytest.mark.asyncio
    async def test_create_returns_refreshed_row(self):
        """create() must add the row, commit, refresh, and return it."""
        from app.domain.schemas import DiseaseReportCreate

        session = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda r: None)
        session.add = MagicMock()

        repo = SurveillanceRepository(session)
        data = DiseaseReportCreate(
            disease_name="malaria",
            region="Kurla",
            case_count=10,
        )

        # After refresh the object should have all its fields set
        async def set_id(row):
            row.id = 99
            row.reported_at = datetime.now(timezone.utc)

        session.refresh = AsyncMock(side_effect=set_id)
        result = await repo.create(data)

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()
        assert result.disease_name == "malaria"
        assert result.region == "Kurla"
        assert result.case_count == 10

    @pytest.mark.asyncio
    async def test_create_sets_reported_at_if_not_provided(self):
        """Omitting reported_at should still produce a row with a datetime."""
        from app.domain.schemas import DiseaseReportCreate

        session = AsyncMock()
        session.add = MagicMock()
        session.refresh = AsyncMock()

        repo = SurveillanceRepository(session)
        data = DiseaseReportCreate(disease_name="cholera", region="Govandi", case_count=5)
        result = await repo.create(data)

        # The add() call should have received a model with a reported_at
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, DiseaseReport)
        assert added_obj.reported_at is not None

    @pytest.mark.asyncio
    async def test_create_uses_provided_reported_at(self):
        """Explicit reported_at should be preserved."""
        from app.domain.schemas import DiseaseReportCreate

        session = AsyncMock()
        session.add = MagicMock()
        session.refresh = AsyncMock()

        ts = datetime(2025, 6, 1, 8, 0, tzinfo=timezone.utc)
        data = DiseaseReportCreate(
            disease_name="typhoid",
            region="Dadar",
            case_count=3,
            reported_at=ts,
        )
        repo = SurveillanceRepository(session)
        await repo.create(data)

        added_obj = session.add.call_args[0][0]
        assert added_obj.reported_at == ts


class TestSurveillanceRepositoryGetById:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self):
        session = AsyncMock()
        report = _report(id=5)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = report
        session.execute = AsyncMock(return_value=result_mock)

        repo = SurveillanceRepository(session)
        found = await repo.get_by_id(5)
        assert found is report

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self):
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        repo = SurveillanceRepository(session)
        found = await repo.get_by_id(999)
        assert found is None


class TestSurveillanceRepositoryListReports:
    @pytest.mark.asyncio
    async def test_list_returns_rows(self):
        session = AsyncMock()
        reports = [_report(id=i) for i in range(3)]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = reports
        session.execute = AsyncMock(return_value=result_mock)

        repo = SurveillanceRepository(session)
        out = await repo.list_reports()
        assert len(out) == 3

    @pytest.mark.asyncio
    async def test_list_accepts_all_filters(self):
        """
        Calling list_reports with all filters should not raise.
        We just verify execute is called (query construction itself is tested
        by the ORM, not us).
        """
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = SurveillanceRepository(session)
        out = await repo.list_reports(
            disease="dengue",
            region="Dharavi",
            from_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            to_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
            limit=50,
        )
        assert isinstance(out, list)
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_returns_empty_when_no_rows(self):
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = SurveillanceRepository(session)
        out = await repo.list_reports()
        assert out == []


class TestSurveillanceRepositoryAggregate:
    @pytest.mark.asyncio
    async def test_aggregate_by_region_shape(self):
        """aggregate_by_region must return dicts with the expected keys."""
        session = AsyncMock()

        # First execute: the GROUP BY query
        agg_row = MagicMock()
        agg_row.region = "Dharavi"
        agg_row.latitude = 19.04
        agg_row.longitude = 72.85
        agg_row.total_cases = 200
        agg_row.report_count = 10

        # Second execute: distinct diseases query
        dis_row = ("Dharavi", "dengue")

        first_result = MagicMock()
        first_result.all.return_value = [agg_row]

        second_result = MagicMock()
        second_result.all.return_value = [dis_row]

        session.execute = AsyncMock(side_effect=[first_result, second_result])

        repo = SurveillanceRepository(session)
        rows = await repo.aggregate_by_region()

        assert len(rows) == 1
        row = rows[0]
        assert row["region"] == "Dharavi"
        assert row["total_cases"] == 200
        assert row["report_count"] == 10
        assert isinstance(row["latitude"], float)
        assert isinstance(row["longitude"], float)
        assert "diseases" in row
        assert "dengue" in row["diseases"]

    @pytest.mark.asyncio
    async def test_aggregate_handles_none_coordinates(self):
        """Regions with no coordinates should produce None, not a float error."""
        session = AsyncMock()

        agg_row = MagicMock()
        agg_row.region = "Unknown"
        agg_row.latitude = None
        agg_row.longitude = None
        agg_row.total_cases = 5
        agg_row.report_count = 1

        first_result = MagicMock()
        first_result.all.return_value = [agg_row]

        second_result = MagicMock()
        second_result.all.return_value = []

        session.execute = AsyncMock(side_effect=[first_result, second_result])

        repo = SurveillanceRepository(session)
        rows = await repo.aggregate_by_region()

        assert rows[0]["latitude"] is None
        assert rows[0]["longitude"] is None


class TestSurveillanceRepositoryTimeSeries:
    @pytest.mark.asyncio
    async def test_time_series_shape(self):
        """time_series must return dicts with date/total_cases/report_count."""
        session = AsyncMock()

        ts_row = MagicMock()
        ts_row.day = datetime(2026, 3, 1, tzinfo=timezone.utc)
        ts_row.total_cases = 55
        ts_row.report_count = 3

        result_mock = MagicMock()
        result_mock.all.return_value = [ts_row]
        session.execute = AsyncMock(return_value=result_mock)

        repo = SurveillanceRepository(session)
        points = await repo.time_series(region="Dharavi", days=90)

        assert len(points) == 1
        p = points[0]
        assert p["date"] == "2026-03-01"
        assert p["total_cases"] == 55
        assert p["report_count"] == 3

    @pytest.mark.asyncio
    async def test_time_series_empty(self):
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = SurveillanceRepository(session)
        points = await repo.time_series(region="Nowhere", days=30)
        assert points == []


# ── API endpoint tests ────────────────────────────────────────────────────────

@pytest.fixture
def mock_surv_repo():
    return AsyncMock()


@pytest.fixture
def surv_client(mock_surv_repo):
    mock_bus = AsyncMock()
    mock_hospital_repo = AsyncMock()
    mock_emergency_repo = AsyncMock()

    app.dependency_overrides[get_bus] = lambda: mock_bus
    app.dependency_overrides[get_hospital_repo] = lambda: mock_hospital_repo
    app.dependency_overrides[get_emergency_repo] = lambda: mock_emergency_repo
    app.dependency_overrides[get_surveillance_repo] = lambda: mock_surv_repo

    yield TestClient(app), mock_bus, mock_surv_repo
    app.dependency_overrides.clear()


class TestIngestReport:
    def test_creates_report_returns_201(self, surv_client):
        client, mock_bus, mock_surv_repo = surv_client

        report = _report()
        mock_surv_repo.create = AsyncMock(return_value=report)

        resp = client.post("/surveillance/reports", json={
            "disease_name": "dengue",
            "region": "Dharavi",
            "case_count": 42,
        })

        assert resp.status_code == 201
        body = resp.json()
        assert body["disease_name"] == "dengue"
        assert body["region"] == "Dharavi"
        assert body["case_count"] == 42
        assert body["id"] == 1

    def test_emits_disease_reported_event(self, surv_client):
        client, mock_bus, mock_surv_repo = surv_client

        report = _report()
        mock_surv_repo.create = AsyncMock(return_value=report)

        client.post("/surveillance/reports", json={
            "disease_name": "dengue",
            "region": "Dharavi",
            "case_count": 42,
        })

        mock_bus.publish.assert_awaited_once()
        event = mock_bus.publish.call_args[0][0]
        assert event.type == EventType.DISEASE_REPORTED
        assert event.payload["disease_name"] == "dengue"
        assert event.payload["region"] == "Dharavi"
        assert event.payload["report_id"] == 1

    def test_validation_rejects_zero_cases(self, surv_client):
        client, _, _ = surv_client
        resp = client.post("/surveillance/reports", json={
            "disease_name": "dengue",
            "region": "Dharavi",
            "case_count": 0,
        })
        assert resp.status_code == 422

    def test_validation_rejects_empty_disease_name(self, surv_client):
        client, _, _ = surv_client
        resp = client.post("/surveillance/reports", json={
            "disease_name": "",
            "region": "Dharavi",
            "case_count": 5,
        })
        assert resp.status_code == 422

    def test_validation_rejects_empty_region(self, surv_client):
        client, _, _ = surv_client
        resp = client.post("/surveillance/reports", json={
            "disease_name": "dengue",
            "region": "",
            "case_count": 5,
        })
        assert resp.status_code == 422

    def test_optional_coordinates_accepted(self, surv_client):
        client, mock_bus, mock_surv_repo = surv_client

        report = _report(latitude=19.04, longitude=72.85)
        mock_surv_repo.create = AsyncMock(return_value=report)

        resp = client.post("/surveillance/reports", json={
            "disease_name": "cholera",
            "region": "Govandi",
            "case_count": 12,
            "latitude": 19.04,
            "longitude": 72.85,
        })
        assert resp.status_code == 201
        assert resp.json()["latitude"] == 19.04


class TestListReports:
    def test_returns_200_with_list(self, surv_client):
        client, _, mock_surv_repo = surv_client

        reports = [_report(id=i) for i in range(3)]
        mock_surv_repo.list_reports = AsyncMock(return_value=reports)

        resp = client.get("/surveillance/reports")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_passes_disease_filter(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.list_reports = AsyncMock(return_value=[])

        client.get("/surveillance/reports?disease=malaria")
        _, kwargs = mock_surv_repo.list_reports.call_args
        assert kwargs.get("disease") == "malaria"

    def test_passes_region_filter(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.list_reports = AsyncMock(return_value=[])

        client.get("/surveillance/reports?region=Thane")
        _, kwargs = mock_surv_repo.list_reports.call_args
        assert kwargs.get("region") == "Thane"

    def test_returns_empty_list(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.list_reports = AsyncMock(return_value=[])

        resp = client.get("/surveillance/reports")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_limit_capped_at_1000(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.list_reports = AsyncMock(return_value=[])

        resp = client.get("/surveillance/reports?limit=9999")
        assert resp.status_code == 422


class TestGetReport:
    def test_returns_report_by_id(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.get_by_id = AsyncMock(return_value=_report(id=7))

        resp = client.get("/surveillance/reports/7")
        assert resp.status_code == 200
        assert resp.json()["id"] == 7

    def test_returns_404_when_not_found(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.get_by_id = AsyncMock(return_value=None)

        resp = client.get("/surveillance/reports/999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


class TestSummaryByRegion:
    def test_returns_region_list(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.aggregate_by_region = AsyncMock(return_value=[
            {
                "region": "Dharavi",
                "latitude": 19.04,
                "longitude": 72.85,
                "total_cases": 500,
                "report_count": 30,
                "diseases": ["dengue", "malaria"],
            },
            {
                "region": "Govandi",
                "latitude": 19.07,
                "longitude": 72.91,
                "total_cases": 200,
                "report_count": 15,
                "diseases": ["cholera"],
            },
        ])

        resp = client.get("/surveillance/summary/by-region")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["region"] == "Dharavi"
        assert body[0]["total_cases"] == 500
        assert "dengue" in body[0]["diseases"]

    def test_passes_disease_filter(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.aggregate_by_region = AsyncMock(return_value=[])

        client.get("/surveillance/summary/by-region?disease=dengue")
        _, kwargs = mock_surv_repo.aggregate_by_region.call_args
        assert kwargs.get("disease") == "dengue"

    def test_empty_result_is_valid(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.aggregate_by_region = AsyncMock(return_value=[])

        resp = client.get("/surveillance/summary/by-region")
        assert resp.status_code == 200
        assert resp.json() == []


class TestSummaryTimeSeries:
    def test_returns_time_series(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.time_series = AsyncMock(return_value=[
            {"date": "2026-01-01", "total_cases": 10, "report_count": 2},
            {"date": "2026-01-08", "total_cases": 25, "report_count": 4},
            {"date": "2026-01-15", "total_cases": 180, "report_count": 5},  # spike
        ])

        resp = client.get("/surveillance/summary/time-series?region=Dharavi")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3
        assert body[0]["date"] == "2026-01-01"
        assert body[2]["total_cases"] == 180   # spike week is visible

    def test_region_is_required(self, surv_client):
        client, _, _ = surv_client
        resp = client.get("/surveillance/summary/time-series")
        assert resp.status_code == 422

    def test_days_must_be_at_least_7(self, surv_client):
        client, _, _ = surv_client
        resp = client.get("/surveillance/summary/time-series?region=Dharavi&days=3")
        assert resp.status_code == 422

    def test_days_must_be_at_most_365(self, surv_client):
        client, _, _ = surv_client
        resp = client.get("/surveillance/summary/time-series?region=Dharavi&days=999")
        assert resp.status_code == 422

    def test_disease_filter_is_passed_to_repo(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.time_series = AsyncMock(return_value=[])

        client.get("/surveillance/summary/time-series?region=Dharavi&disease=dengue")
        _, kwargs = mock_surv_repo.time_series.call_args
        assert kwargs.get("disease") == "dengue"
        assert kwargs.get("region") == "Dharavi"

    def test_empty_series_returns_200(self, surv_client):
        client, _, mock_surv_repo = surv_client
        mock_surv_repo.time_series = AsyncMock(return_value=[])

        resp = client.get("/surveillance/summary/time-series?region=Nowhere&days=30")
        assert resp.status_code == 200
        assert resp.json() == []
