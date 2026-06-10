"""
Tests for B3 spike detection + alert engine.

Coverage:
  detect_spikes (app.surveillance.spikes)
    - cold start: series with <= window points -> no detections
    - flat series -> no detections, no divide-by-zero
    - causal window: a spike is not flagged before it happens
    - injected spike on a flat baseline -> CRITICAL (SENTINEL_Z path)
    - severity tiers: LOW / MEDIUM / HIGH / CRITICAL boundaries
    - below the lowest threshold -> no detection

  run_scan (app.surveillance.alerts)
    - new detection -> alert persisted + AlertGenerated event emitted
    - duplicate detection (repo returns None) -> no event, not in new_alerts

  API
    POST /surveillance/scan
      - detects the injected spike, persists alert, emits AlertGenerated
      - idempotent re-scan: no new alerts, no duplicate event
      - 404 when no time-series data
    GET /surveillance/spikes
      - read-only preview, same detections, no alert/event side effects
    GET /alerts
      - lists alerts, forwards severity/type filters
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_alert_repo,
    get_bus,
    get_emergency_repo,
    get_hospital_repo,
    get_outbreak_repo,
    get_surveillance_repo,
)
from app.domain.events import EventType
from app.infra.models import Alert, OutbreakTimeSeries
from app.main import app
from app.surveillance.alerts import run_scan
from app.surveillance.spikes import SENTINEL_Z, SeriesPoint, Severity, SpikeDetection, detect_spikes

_DEFAULT_THRESHOLDS = {
    Severity.LOW: 2.0,
    Severity.MEDIUM: 3.0,
    Severity.HIGH: 4.0,
    Severity.CRITICAL: 5.0,
}


def _series(values: list[int], start_year: int = 2020) -> list[SeriesPoint]:
    return [
        SeriesPoint(date=f"{start_year + i // 12}-{(i % 12) + 1:02d}-01", value=v)
        for i, v in enumerate(values)
    ]


# ── detect_spikes ─────────────────────────────────────────────────────────────

class TestDetectSpikes:
    def test_cold_start_no_full_window(self):
        """A series with <= window points has no trailing window -> nothing."""
        points = _series([100, 100, 100])
        out = detect_spikes(points, window=6, thresholds=_DEFAULT_THRESHOLDS)
        assert out == []

    def test_flat_series_no_detections_no_div_by_zero(self):
        """A perfectly flat series: rolling_std == 0 and value == mean everywhere."""
        points = _series([100] * 14)
        out = detect_spikes(points, window=6, thresholds=_DEFAULT_THRESHOLDS)
        assert out == []

    def test_injected_spike_on_flat_baseline_is_critical(self):
        """
        12 flat months then one huge spike.  The trailing window for the spike
        is still flat (std == 0) and the value differs -> SENTINEL_Z -> CRITICAL.
        """
        points = _series([100] * 12 + [10_000])
        out = detect_spikes(points, window=6, thresholds=_DEFAULT_THRESHOLDS)

        assert len(out) == 1
        spike = out[0]
        assert spike.date == points[-1].date
        assert spike.value == 10_000
        assert spike.z_score == SENTINEL_Z
        assert spike.severity == Severity.CRITICAL

    def test_causal_window_spike_not_flagged_early(self):
        """
        The point immediately before the spike must not itself be flagged --
        a causal detector can't "see" the spike before it happens.
        """
        points = _series([100] * 12 + [10_000])
        out = detect_spikes(points, window=6, thresholds=_DEFAULT_THRESHOLDS)

        flagged_dates = {d.date for d in out}
        assert points[-2].date not in flagged_dates  # last flat point, pre-spike
        assert points[-1].date in flagged_dates       # the spike itself

    def test_below_low_threshold_not_flagged(self):
        """window=[0, 10] -> mean=5, std=5.  z=1.6 for value=13 -> below LOW (2.0)."""
        points = _series([0, 10, 13])
        out = detect_spikes(points, window=2, thresholds=_DEFAULT_THRESHOLDS)
        assert out == []

    @pytest.mark.parametrize(
        "value, expected_z, expected_severity",
        [
            (15, 2.0, Severity.LOW),
            (20, 3.0, Severity.MEDIUM),
            (25, 4.0, Severity.HIGH),
            (30, 5.0, Severity.CRITICAL),
        ],
    )
    def test_severity_tiers(self, value, expected_z, expected_severity):
        """
        window=[0, 10] -> mean=5, std=5 (population stddev of {0,10}).
        z = (value - 5) / 5, chosen so z lands exactly on each tier boundary.
        """
        points = _series([0, 10, value])
        out = detect_spikes(points, window=2, thresholds=_DEFAULT_THRESHOLDS)

        assert len(out) == 1
        assert out[0].z_score == pytest.approx(expected_z)
        assert out[0].severity == expected_severity
        assert out[0].rolling_mean == pytest.approx(5.0)
        assert out[0].rolling_std == pytest.approx(5.0)


# ── run_scan (alert engine) ──────────────────────────────────────────────────

class TestRunScan:
    @pytest.mark.asyncio
    async def test_new_detection_creates_alert_and_emits_event(self):
        repo = AsyncMock()
        repo.create_spike_alert = AsyncMock(return_value={
            "id": 1,
            "type": "OUTBREAK_SPIKE",
            "severity": "CRITICAL",
            "message": "covid_19 in India: cases far above 6-month baseline on 2021-04-01",
            "region": "India",
            "disease_name": "covid_19",
            "event_date": "2021-04-01",
            "z_score": SENTINEL_Z,
            "created_at": datetime(2026, 6, 10, tzinfo=timezone.utc),
        })
        bus = AsyncMock()
        detection = SpikeDetection(
            date="2021-04-01", value=4_954_030,
            rolling_mean=1_514_487.0, rolling_std=0.0,
            z_score=SENTINEL_Z, severity=Severity.CRITICAL,
        )

        new_alerts = await run_scan(
            disease_name="covid_19", region="India",
            detections=[detection], window=6, repo=repo, bus=bus,
        )

        assert len(new_alerts) == 1
        repo.create_spike_alert.assert_awaited_once()
        bus.publish.assert_awaited_once()
        event = bus.publish.call_args[0][0]
        assert event.type == EventType.ALERT_GENERATED
        assert event.payload["disease_name"] == "covid_19"
        assert event.payload["region"] == "India"
        assert event.payload["event_date"] == "2021-04-01"
        assert event.payload["severity"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_duplicate_detection_skipped_no_event(self):
        """A repeat scan: create_spike_alert returns None (ON CONFLICT DO NOTHING)."""
        repo = AsyncMock()
        repo.create_spike_alert = AsyncMock(return_value=None)
        bus = AsyncMock()
        detection = SpikeDetection(
            date="2021-04-01", value=4_954_030,
            rolling_mean=1_514_487.0, rolling_std=0.0,
            z_score=SENTINEL_Z, severity=Severity.CRITICAL,
        )

        new_alerts = await run_scan(
            disease_name="covid_19", region="India",
            detections=[detection], window=6, repo=repo, bus=bus,
        )

        assert new_alerts == []
        bus.publish.assert_not_awaited()


# ── API ───────────────────────────────────────────────────────────────────────

def _ots_row(d: str, case_count: int) -> OutbreakTimeSeries:
    r = MagicMock(spec=OutbreakTimeSeries)
    r.date = date.fromisoformat(d)
    r.case_count = case_count
    return r


def _alert_row(**overrides) -> Alert:
    r = MagicMock(spec=Alert)
    r.id = 1
    r.type = "OUTBREAK_SPIKE"
    r.severity = "CRITICAL"
    r.message = "covid_19 in India: cases far above 6-month baseline on 2021-04-01"
    r.region = "India"
    r.disease_name = "covid_19"
    r.event_date = date(2021, 4, 1)
    r.z_score = SENTINEL_Z
    r.created_at = datetime(2026, 6, 10, tzinfo=timezone.utc)
    r.resolved_at = None
    for k, v in overrides.items():
        setattr(r, k, v)
    return r


# 12 flat months then one spike -> with the default window (6) and thresholds
# (2/3/4/5), only the final point is flagged, as CRITICAL via SENTINEL_Z.
_FLAT_THEN_SPIKE = [_ots_row(f"{2020 + i // 12}-{(i % 12) + 1:02d}-01", 100) for i in range(12)]
_FLAT_THEN_SPIKE.append(_ots_row("2021-01-01", 10_000))


@pytest.fixture
def mock_outbreak_repo():
    return AsyncMock()


@pytest.fixture
def mock_alert_repo():
    return AsyncMock()


@pytest.fixture
def b3_client(mock_outbreak_repo, mock_alert_repo):
    mock_bus = AsyncMock()
    mock_hospital = AsyncMock()
    mock_emergency = AsyncMock()
    mock_surv = AsyncMock()

    app.dependency_overrides[get_bus] = lambda: mock_bus
    app.dependency_overrides[get_hospital_repo] = lambda: mock_hospital
    app.dependency_overrides[get_emergency_repo] = lambda: mock_emergency
    app.dependency_overrides[get_surveillance_repo] = lambda: mock_surv
    app.dependency_overrides[get_outbreak_repo] = lambda: mock_outbreak_repo
    app.dependency_overrides[get_alert_repo] = lambda: mock_alert_repo

    yield TestClient(app), mock_outbreak_repo, mock_alert_repo, mock_bus
    app.dependency_overrides.clear()


class TestScanEndpoint:
    def test_detects_spike_and_creates_alert(self, b3_client):
        client, mock_outbreak_repo, mock_alert_repo, mock_bus = b3_client
        mock_outbreak_repo.timeseries = AsyncMock(return_value=_FLAT_THEN_SPIKE)
        mock_alert_repo.create_spike_alert = AsyncMock(return_value={
            "id": 1,
            "type": "OUTBREAK_SPIKE",
            "severity": "CRITICAL",
            "message": "covid_19 in India: cases far above 6-month baseline on 2021-01-01",
            "region": "India",
            "disease_name": "covid_19",
            "event_date": "2021-01-01",
            "z_score": SENTINEL_Z,
            "created_at": datetime(2026, 6, 10, tzinfo=timezone.utc),
            "resolved_at": None,
        })

        resp = client.post("/surveillance/scan?disease=covid_19&region=India")

        assert resp.status_code == 200
        body = resp.json()
        assert body["disease_name"] == "covid_19"
        assert body["region"] == "India"
        assert body["points_scanned"] == 13
        assert len(body["detections"]) == 1
        assert body["detections"][0]["severity"] == "CRITICAL"
        assert body["detections"][0]["date"] == "2021-01-01"
        assert len(body["new_alerts"]) == 1
        assert body["new_alerts"][0]["severity"] == "CRITICAL"

        mock_bus.publish.assert_awaited_once()
        event = mock_bus.publish.call_args[0][0]
        assert event.type == EventType.ALERT_GENERATED

    def test_rescan_is_idempotent(self, b3_client):
        """Same series, but the alert already exists -> no new alert, no event."""
        client, mock_outbreak_repo, mock_alert_repo, mock_bus = b3_client
        mock_outbreak_repo.timeseries = AsyncMock(return_value=_FLAT_THEN_SPIKE)
        mock_alert_repo.create_spike_alert = AsyncMock(return_value=None)

        resp = client.post("/surveillance/scan?disease=covid_19&region=India")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["detections"]) == 1   # detection still reported
        assert body["new_alerts"] == []        # but no new alert row
        mock_bus.publish.assert_not_awaited()

    def test_404_when_no_data(self, b3_client):
        client, mock_outbreak_repo, _, _ = b3_client
        mock_outbreak_repo.timeseries = AsyncMock(return_value=[])

        resp = client.post("/surveillance/scan?disease=covid_19&region=Nowhere")
        assert resp.status_code == 404

    def test_flat_series_scan_creates_no_alerts(self, b3_client):
        client, mock_outbreak_repo, mock_alert_repo, mock_bus = b3_client
        mock_outbreak_repo.timeseries = AsyncMock(
            return_value=[_ots_row(f"{2020 + i // 12}-{(i % 12) + 1:02d}-01", 100) for i in range(14)]
        )

        resp = client.post("/surveillance/scan?disease=covid_19&region=India")

        assert resp.status_code == 200
        body = resp.json()
        assert body["detections"] == []
        assert body["new_alerts"] == []
        mock_alert_repo.create_spike_alert.assert_not_awaited()
        mock_bus.publish.assert_not_awaited()


class TestSpikesEndpoint:
    def test_returns_detections_without_side_effects(self, b3_client):
        client, mock_outbreak_repo, mock_alert_repo, mock_bus = b3_client
        mock_outbreak_repo.timeseries = AsyncMock(return_value=_FLAT_THEN_SPIKE)

        resp = client.get("/surveillance/spikes?disease=covid_19&region=India")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["severity"] == "CRITICAL"
        mock_alert_repo.create_spike_alert.assert_not_awaited()
        mock_bus.publish.assert_not_awaited()

    def test_404_when_no_data(self, b3_client):
        client, mock_outbreak_repo, _, _ = b3_client
        mock_outbreak_repo.timeseries = AsyncMock(return_value=[])

        resp = client.get("/surveillance/spikes?disease=covid_19&region=Nowhere")
        assert resp.status_code == 404


class TestAlertsEndpoint:
    def test_lists_alerts_newest_first(self, b3_client):
        client, _, mock_alert_repo, _ = b3_client
        mock_alert_repo.list_alerts = AsyncMock(return_value=[_alert_row(id=2), _alert_row(id=1)])

        resp = client.get("/alerts")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["id"] == 2
        assert body[0]["type"] == "OUTBREAK_SPIKE"
        assert body[0]["event_date"] == "2021-04-01"

    def test_forwards_severity_and_type_filters(self, b3_client):
        client, _, mock_alert_repo, _ = b3_client
        mock_alert_repo.list_alerts = AsyncMock(return_value=[])

        client.get("/alerts?severity=CRITICAL&type=OUTBREAK_SPIKE")

        _, kwargs = mock_alert_repo.list_alerts.call_args
        assert kwargs.get("severity") == "CRITICAL"
        assert kwargs.get("type_") == "OUTBREAK_SPIKE"

    def test_empty_list_is_valid(self, b3_client):
        client, _, mock_alert_repo, _ = b3_client
        mock_alert_repo.list_alerts = AsyncMock(return_value=[])

        resp = client.get("/alerts")
        assert resp.status_code == 200
        assert resp.json() == []
