"""
Tests for B1 outbreak time-series layer.

Coverage:
  OutbreakRepository:
    - timeseries (all rows, date-filtered)
    - available_diseases
    - available_regions
    - disease_metadata (structure, disease grouping)
    - summary (totals, peak)
    - count

  Ingestion:
    - ingest() populates DB from fixture CSV
    - idempotency: second call inserts 0 rows

  API endpoints:
    GET /surveillance/diseases    — shape, field presence
    GET /surveillance/timeseries  — ordered, filtered, 422 on missing params
    GET /surveillance/summary     — totals shape
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_bus, get_emergency_repo, get_hospital_repo, get_outbreak_repo, get_surveillance_repo
from app.infra.models import OutbreakTimeSeries
from app.main import app


# ── fixtures & helpers ────────────────────────────────────────────────────────

def _ots(**overrides) -> OutbreakTimeSeries:
    o = OutbreakTimeSeries(
        id=1,
        disease_name="covid_19",
        region="India",
        date=date(2021, 5, 1),
        case_count=11_920_000,
        deaths=120_000,
        source="OWID",
    )
    for k, v in overrides.items():
        setattr(o, k, v)
    return o


# ── OutbreakRepository unit tests ─────────────────────────────────────────────

class TestOutbreakRepositoryTimeSeries:
    @pytest.mark.asyncio
    async def test_timeseries_returns_rows(self):
        from app.surveillance.repository import OutbreakRepository

        session = AsyncMock()
        rows = [_ots(id=i, date=date(2021, i + 1, 1)) for i in range(1, 4)]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = rows
        session.execute = AsyncMock(return_value=result_mock)

        repo = OutbreakRepository(session)
        out = await repo.timeseries("covid_19", "India")
        assert len(out) == 3

    @pytest.mark.asyncio
    async def test_timeseries_accepts_date_filters(self):
        from app.surveillance.repository import OutbreakRepository

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = OutbreakRepository(session)
        out = await repo.timeseries(
            "covid_19", "India",
            from_date=date(2021, 1, 1),
            to_date=date(2021, 12, 31),
        )
        assert isinstance(out, list)
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_timeseries_empty(self):
        from app.surveillance.repository import OutbreakRepository

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = OutbreakRepository(session)
        out = await repo.timeseries("cholera", "Nowhere")
        assert out == []


class TestOutbreakRepositoryDiseases:
    @pytest.mark.asyncio
    async def test_available_diseases_returns_list(self):
        from app.surveillance.repository import OutbreakRepository

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = ["cholera", "covid_19", "measles"]
        session.execute = AsyncMock(return_value=result_mock)

        repo = OutbreakRepository(session)
        out = await repo.available_diseases()
        assert out == ["cholera", "covid_19", "measles"]

    @pytest.mark.asyncio
    async def test_available_regions_returns_list(self):
        from app.surveillance.repository import OutbreakRepository

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = ["India", "Nigeria"]
        session.execute = AsyncMock(return_value=result_mock)

        repo = OutbreakRepository(session)
        out = await repo.available_regions("measles")
        assert "India" in out

    @pytest.mark.asyncio
    async def test_disease_metadata_merges_regions(self):
        """disease_metadata must return one dict per disease with all regions merged."""
        from app.surveillance.repository import OutbreakRepository

        session = AsyncMock()

        # Simulate two rows for the same disease but different regions
        row_india = MagicMock()
        row_india.disease_name = "measles"
        row_india.region = "India"
        row_india.date_from = date(2000, 1, 1)
        row_india.date_to = date(2022, 1, 1)
        row_india.record_count = 23

        row_nigeria = MagicMock()
        row_nigeria.disease_name = "measles"
        row_nigeria.region = "Nigeria"
        row_nigeria.date_from = date(2000, 1, 1)
        row_nigeria.date_to = date(2022, 1, 1)
        row_nigeria.record_count = 23

        result_mock = MagicMock()
        result_mock.all.return_value = [row_india, row_nigeria]
        session.execute = AsyncMock(return_value=result_mock)

        repo = OutbreakRepository(session)
        meta = await repo.disease_metadata()

        assert len(meta) == 1                # one entry per disease
        assert meta[0]["disease_name"] == "measles"
        assert set(meta[0]["regions"]) == {"India", "Nigeria"}
        assert meta[0]["total_records"] == 46


class TestOutbreakRepositorySummary:
    @pytest.mark.asyncio
    async def test_summary_shape(self):
        """summary() must return total_cases, total_deaths, peak_cases, peak_date."""
        from app.surveillance.repository import OutbreakRepository

        session = AsyncMock()

        agg_row = MagicMock()
        agg_row.disease_name = "covid_19"
        agg_row.total_cases = 100_000_000
        agg_row.total_deaths = 1_000_000
        agg_row.peak_cases = 11_920_000
        agg_row.record_count = 160

        first_result = MagicMock()
        first_result.all.return_value = [agg_row]

        peak_result = MagicMock()
        peak_result.scalar_one_or_none.return_value = date(2021, 6, 1)

        session.execute = AsyncMock(side_effect=[first_result, peak_result])

        repo = OutbreakRepository(session)
        rows = await repo.summary()

        assert len(rows) == 1
        s = rows[0]
        assert s["disease_name"] == "covid_19"
        assert s["total_cases"] == 100_000_000
        assert s["peak_cases"] == 11_920_000
        assert s["peak_date"] == "2021-06-01"


# ── Ingestion tests ───────────────────────────────────────────────────────────

class TestIngestion:
    @pytest.mark.asyncio
    async def test_ingest_populates_from_fixture(self, tmp_path):
        """ingest() should read a CSV and bulk-insert all rows."""
        import csv
        from app.surveillance.ingest import ingest

        # Write a tiny 3-row fixture
        fixture = tmp_path / "test.csv"
        with open(fixture, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["disease_name", "region", "date", "case_count", "deaths", "source"])
            w.writerow(["measles", "India", "2021-01-01", "1000", "10", "OWID"])
            w.writerow(["measles", "India", "2022-01-01", "1200", "12", "OWID"])
            w.writerow(["cholera", "DRC",   "2020-01-01", "5000", "60", "OWID"])

        # Mock the session factory so we never hit a real DB
        mock_obj = MagicMock()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # scalar_one_or_none() returns None → table is empty → proceed with insert
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.surveillance.ingest.get_session_factory", return_value=mock_factory):
            n = await ingest(fixture)

        assert n == 3
        assert mock_session.add.call_count == 3
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ingest_is_idempotent(self, tmp_path):
        """If any row already exists, ingest() skips all inserts and returns 0."""
        import csv
        from app.surveillance.ingest import ingest

        fixture = tmp_path / "test.csv"
        with open(fixture, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["disease_name", "region", "date", "case_count", "deaths", "source"])
            w.writerow(["measles", "India", "2021-01-01", "1000", "10", "OWID"])

        mock_session = AsyncMock()
        # Return an existing row → skip
        existing = MagicMock()
        existing.scalar_one_or_none.return_value = MagicMock()
        mock_session.execute = AsyncMock(return_value=existing)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.surveillance.ingest.get_session_factory", return_value=mock_factory):
            n = await ingest(fixture)

        assert n == 0
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_raises_on_missing_fixture(self, tmp_path):
        """ingest() must raise FileNotFoundError if the fixture path doesn't exist."""
        from app.surveillance.ingest import ingest

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.surveillance.ingest.get_session_factory", return_value=mock_factory):
            with pytest.raises(FileNotFoundError):
                await ingest(tmp_path / "does_not_exist.csv")


# ── API endpoint tests ────────────────────────────────────────────────────────

@pytest.fixture
def mock_outbreak_repo():
    return AsyncMock()


@pytest.fixture
def outbreak_client(mock_outbreak_repo):
    mock_bus = AsyncMock()
    mock_hospital_repo = AsyncMock()
    mock_emergency_repo = AsyncMock()
    mock_surv_repo = AsyncMock()

    app.dependency_overrides[get_bus] = lambda: mock_bus
    app.dependency_overrides[get_hospital_repo] = lambda: mock_hospital_repo
    app.dependency_overrides[get_emergency_repo] = lambda: mock_emergency_repo
    app.dependency_overrides[get_surveillance_repo] = lambda: mock_surv_repo
    app.dependency_overrides[get_outbreak_repo] = lambda: mock_outbreak_repo

    yield TestClient(app), mock_outbreak_repo
    app.dependency_overrides.clear()


class TestDiseaseListEndpoint:
    def test_returns_disease_list(self, outbreak_client):
        client, mock_repo = outbreak_client
        mock_repo.disease_metadata = AsyncMock(return_value=[
            {
                "disease_name": "covid_19",
                "regions": ["India", "United States"],
                "date_from": "2020-03-01",
                "date_to": "2023-06-01",
                "total_records": 80,
            },
            {
                "disease_name": "measles",
                "regions": ["India", "Nigeria"],
                "date_from": "2000-01-01",
                "date_to": "2022-01-01",
                "total_records": 46,
            },
        ])

        resp = client.get("/surveillance/diseases")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["disease_name"] == "covid_19"
        assert "India" in body[0]["regions"]
        assert body[0]["total_records"] == 80

    def test_empty_returns_200(self, outbreak_client):
        client, mock_repo = outbreak_client
        mock_repo.disease_metadata = AsyncMock(return_value=[])
        resp = client.get("/surveillance/diseases")
        assert resp.status_code == 200
        assert resp.json() == []


class TestTimeSeriesEndpoint:
    def test_returns_ordered_points(self, outbreak_client):
        client, mock_repo = outbreak_client

        rows = [
            _ots(id=i, date=date(2021, i + 1, 1), case_count=i * 100_000)
            for i in range(1, 4)
        ]
        mock_repo.timeseries = AsyncMock(return_value=rows)

        resp = client.get("/surveillance/timeseries?disease=covid_19&region=India")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 3
        # oldest first
        assert body[0]["date"] == "2021-02-01"
        assert body[1]["date"] == "2021-03-01"

    def test_requires_disease_param(self, outbreak_client):
        client, _ = outbreak_client
        resp = client.get("/surveillance/timeseries?region=India")
        assert resp.status_code == 422

    def test_requires_region_param(self, outbreak_client):
        client, _ = outbreak_client
        resp = client.get("/surveillance/timeseries?disease=covid_19")
        assert resp.status_code == 422

    def test_accepts_date_filters(self, outbreak_client):
        client, mock_repo = outbreak_client
        mock_repo.timeseries = AsyncMock(return_value=[])

        resp = client.get(
            "/surveillance/timeseries"
            "?disease=covid_19&region=India"
            "&from_date=2021-01-01&to_date=2021-12-31"
        )
        assert resp.status_code == 200
        _, kwargs = mock_repo.timeseries.call_args
        assert kwargs["from_date"].isoformat() == "2021-01-01"
        assert kwargs["to_date"].isoformat() == "2021-12-31"

    def test_invalid_date_format_returns_500_or_422(self, outbreak_client):
        """Malformed date string should not return 200."""
        client, _ = outbreak_client
        resp = client.get(
            "/surveillance/timeseries"
            "?disease=covid_19&region=India&from_date=not-a-date"
        )
        assert resp.status_code in (422, 500)

    def test_empty_series_returns_200(self, outbreak_client):
        client, mock_repo = outbreak_client
        mock_repo.timeseries = AsyncMock(return_value=[])
        resp = client.get("/surveillance/timeseries?disease=cholera&region=Nowhere")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_response_has_required_fields(self, outbreak_client):
        client, mock_repo = outbreak_client
        mock_repo.timeseries = AsyncMock(return_value=[_ots()])

        resp = client.get("/surveillance/timeseries?disease=covid_19&region=India")
        point = resp.json()[0]
        assert "date" in point
        assert "case_count" in point
        assert "deaths" in point
        assert "source" in point


class TestSummaryEndpoint:
    def test_returns_summary_list(self, outbreak_client):
        client, mock_repo = outbreak_client
        mock_repo.summary = AsyncMock(return_value=[
            {
                "disease_name": "covid_19",
                "total_cases": 100_000_000,
                "total_deaths": 1_000_000,
                "peak_cases": 11_920_000,
                "peak_date": "2021-06-01",
                "record_count": 160,
            },
        ])

        resp = client.get("/surveillance/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["disease_name"] == "covid_19"
        assert body[0]["total_cases"] == 100_000_000
        assert body[0]["peak_date"] == "2021-06-01"

    def test_empty_returns_200(self, outbreak_client):
        client, mock_repo = outbreak_client
        mock_repo.summary = AsyncMock(return_value=[])
        resp = client.get("/surveillance/summary")
        assert resp.status_code == 200
        assert resp.json() == []
