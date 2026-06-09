"""
Tests for B2 DBSCAN hotspot clustering.

Coverage:
  _SpatialIndex.range_within
    - returns all points within radius
    - excludes points beyond radius
    - single-point index
    - empty index (edge case handled by dbscan wrapper)

  dbscan
    - two tight clusters separated by a gap → two distinct cluster ids
    - points beyond ε stay in separate clusters
    - isolated points below min_pts → noise (cluster_id == -1)
    - centroid is average lat/lon of members
    - total_cases is sum of member case_counts
    - single report, min_pts=1 → one cluster (not noise)
    - single report, min_pts=2 → noise
    - empty input → empty output

  K-D tree vs brute force
    - label array from dbscan (K-D tree) matches _dbscan_brute_labels on:
        * known tight pair
        * scattered points with one isolated noise
        * randomised 50-point set

  API endpoint
    - GET /surveillance/hotspots returns 200 with cluster + noise structure
    - cluster_count excludes noise
    - eps_km / min_pts are echoed in response
    - disease filter is forwarded to the repository
"""
from __future__ import annotations

import math
import random
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_bus,
    get_emergency_repo,
    get_hospital_repo,
    get_outbreak_repo,
    get_surveillance_repo,
)
from app.infra.models import DiseaseReport
from app.main import app
from app.surveillance.clustering import (
    NOISE,
    ClusterPoint,
    _SpatialIndex,
    _dbscan_brute_labels,
    dbscan,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _pt(idx: int, lat: float, lon: float, cases: int = 10) -> ClusterPoint:
    return ClusterPoint(idx=idx, report_id=idx + 1000, lat=lat, lon=lon, case_count=cases)


def _report(id: int, lat: float, lon: float, cases: int = 10) -> DiseaseReport:
    r = MagicMock(spec=DiseaseReport)
    r.id = id
    r.latitude = lat
    r.longitude = lon
    r.case_count = cases
    return r


# Mumbai centre — used as anchor for cluster geometry tests
_MUM_LAT = 19.076
_MUM_LON = 72.877

# 1 km in degrees (approximate) — used to space test points
_KM_DEG_LAT = 1.0 / 111.32


# ── _SpatialIndex tests ───────────────────────────────────────────────────────

class TestSpatialIndex:
    def test_returns_points_within_radius(self):
        pts = [
            _pt(0, _MUM_LAT,               _MUM_LON),           # origin
            _pt(1, _MUM_LAT + _KM_DEG_LAT, _MUM_LON),           # ~1 km north
            _pt(2, _MUM_LAT + 5 * _KM_DEG_LAT, _MUM_LON),       # ~5 km north
        ]
        idx = _SpatialIndex(pts)
        within_2km = idx.range_within(_MUM_LAT, _MUM_LON, 2_000)
        assert 0 in within_2km
        assert 1 in within_2km
        assert 2 not in within_2km

    def test_excludes_points_beyond_radius(self):
        pts = [_pt(0, _MUM_LAT, _MUM_LON), _pt(1, _MUM_LAT + 10 * _KM_DEG_LAT, _MUM_LON)]
        idx = _SpatialIndex(pts)
        result = idx.range_within(_MUM_LAT, _MUM_LON, 500)
        assert result == [0]

    def test_single_point_index(self):
        pts = [_pt(0, _MUM_LAT, _MUM_LON)]
        idx = _SpatialIndex(pts)
        assert idx.range_within(_MUM_LAT, _MUM_LON, 1_000) == [0]
        assert idx.range_within(_MUM_LAT + 1, _MUM_LON, 1_000) == []

    def test_includes_boundary_point(self):
        """A point exactly at eps distance must be included (≤, not <)."""
        pts = [_pt(0, _MUM_LAT, _MUM_LON), _pt(1, _MUM_LAT + _KM_DEG_LAT, _MUM_LON)]
        idx = _SpatialIndex(pts)
        from app.graph.haversine import haversine
        exact_dist = haversine(_MUM_LAT, _MUM_LON,
                               _MUM_LAT + _KM_DEG_LAT, _MUM_LON)
        result = idx.range_within(_MUM_LAT, _MUM_LON, exact_dist)
        assert 1 in result


# ── dbscan unit tests ─────────────────────────────────────────────────────────

class TestDBSCAN:
    def test_two_tight_clusters_separated(self):
        """Points ≤ 1 km apart cluster; two groups 20 km apart stay separate."""
        # Cluster A: 4 points near Mumbai origin
        cluster_a = [_pt(i, _MUM_LAT + i * 0.001, _MUM_LON, cases=5) for i in range(4)]
        # Cluster B: 4 points 20 km north
        cluster_b = [_pt(i + 4, _MUM_LAT + 20 * _KM_DEG_LAT + i * 0.001, _MUM_LON, cases=5) for i in range(4)]
        results = dbscan(cluster_a + cluster_b, eps_km=2.0, min_pts=3)
        cluster_ids = {r.cluster_id for r in results}
        assert len(cluster_ids) == 2
        assert NOISE not in cluster_ids

    def test_isolated_point_is_noise(self):
        """A single point with no neighbours within eps is noise."""
        pts = [
            _pt(0, _MUM_LAT,               _MUM_LON),          # isolated
            _pt(1, _MUM_LAT + 10 * _KM_DEG_LAT, _MUM_LON),    # cluster
            _pt(2, _MUM_LAT + 10 * _KM_DEG_LAT + 0.001, _MUM_LON),
            _pt(3, _MUM_LAT + 10 * _KM_DEG_LAT + 0.002, _MUM_LON),
        ]
        results = dbscan(pts, eps_km=2.0, min_pts=3)
        noise = [r for r in results if r.cluster_id == NOISE]
        assert len(noise) == 1
        assert 1000 in noise[0].member_ids   # report_id = idx + 1000, idx=0 → 1000

    def test_centroid_is_average_of_members(self):
        """Centroid = unweighted mean of member coordinates."""
        pts = [
            _pt(0, 19.00, 72.80, cases=10),
            _pt(1, 19.02, 72.82, cases=10),
            _pt(2, 19.04, 72.84, cases=10),
        ]
        results = dbscan(pts, eps_km=5.0, min_pts=2)
        assert len(results) == 1
        c = results[0]
        assert abs(c.centroid_lat - 19.02) < 1e-5
        assert abs(c.centroid_lon - 72.82) < 1e-5

    def test_total_cases_is_sum_of_members(self):
        pts = [
            _pt(0, _MUM_LAT,       _MUM_LON, cases=100),
            _pt(1, _MUM_LAT + 0.001, _MUM_LON, cases=200),
            _pt(2, _MUM_LAT + 0.002, _MUM_LON, cases=300),
        ]
        results = dbscan(pts, eps_km=2.0, min_pts=2)
        real = [r for r in results if r.cluster_id >= 0]
        assert len(real) == 1
        assert real[0].total_cases == 600

    def test_single_report_min_pts_1_is_cluster(self):
        pts = [_pt(0, _MUM_LAT, _MUM_LON, cases=5)]
        results = dbscan(pts, eps_km=2.0, min_pts=1)
        assert len(results) == 1
        assert results[0].cluster_id == 0

    def test_single_report_min_pts_2_is_noise(self):
        pts = [_pt(0, _MUM_LAT, _MUM_LON, cases=5)]
        results = dbscan(pts, eps_km=2.0, min_pts=2)
        assert len(results) == 1
        assert results[0].cluster_id == NOISE

    def test_empty_input_returns_empty(self):
        assert dbscan([], eps_km=2.0, min_pts=3) == []

    def test_clusters_sorted_by_total_cases_desc(self):
        """Clusters come back ordered largest → smallest; noise at end."""
        small_cluster = [_pt(i, _MUM_LAT + i * 0.001, _MUM_LON, cases=1) for i in range(3)]
        large_cluster = [_pt(i + 3, _MUM_LAT + 20 * _KM_DEG_LAT + i * 0.001, _MUM_LON, cases=100) for i in range(3)]
        results = dbscan(small_cluster + large_cluster, eps_km=2.0, min_pts=3)
        real = [r for r in results if r.cluster_id >= 0]
        assert real[0].total_cases > real[-1].total_cases

    def test_radius_km_is_max_distance_from_centroid(self):
        pts = [
            _pt(0, 19.00, 72.80, cases=1),
            _pt(1, 19.01, 72.80, cases=1),
            _pt(2, 19.02, 72.80, cases=1),
        ]
        results = dbscan(pts, eps_km=5.0, min_pts=2)
        c = results[0]
        from app.graph.haversine import haversine
        max_r = max(
            haversine(c.centroid_lat, c.centroid_lon, p.lat, p.lon) / 1000.0
            for p in pts
        )
        assert abs(c.radius_km - max_r) < 1e-3

    def test_border_point_pulled_into_cluster(self):
        """A noise-labeled point that falls in range of a core is reclassified."""
        # Three points form a core; a 4th is just within ε of the core's edge.
        core = [_pt(i, _MUM_LAT + i * 0.001, _MUM_LON) for i in range(3)]
        border = _pt(3, _MUM_LAT + 0.001, _MUM_LON + 0.01, cases=5)  # close to core[1]
        results = dbscan(core + [border], eps_km=2.0, min_pts=3)
        real = [r for r in results if r.cluster_id >= 0]
        assert len(real) == 1
        assert border.report_id in real[0].member_ids


# ── K-D tree vs brute force ───────────────────────────────────────────────────

class TestKDTreeVsBruteForce:
    def _same_partition(self, points: list[ClusterPoint], eps_km: float, min_pts: int) -> bool:
        """
        Check that the K-D tree and brute-force DBSCAN produce the same
        partitioning (same sets of points in the same cluster, even if
        cluster_ids differ because iteration order can vary).
        """
        kd_labels = [NOISE] * len(points)
        kd_results = dbscan(points, eps_km, min_pts)
        for r in kd_results:
            for rid in r.member_ids:
                idx = rid - 1000   # report_id = idx + 1000
                kd_labels[idx] = r.cluster_id

        bf_labels = _dbscan_brute_labels(points, eps_km, min_pts)

        # Build sets-of-members per label for both, then compare partitions.
        def partition(labels: list[int]) -> frozenset:
            groups: dict[int, frozenset] = {}
            for i, lbl in enumerate(labels):
                groups.setdefault(lbl, set()).add(i)
            return frozenset(frozenset(s) for s in groups.values())

        return partition(kd_labels) == partition(bf_labels)

    def test_known_two_cluster_geometry(self):
        a = [_pt(i, _MUM_LAT + i * 0.001, _MUM_LON) for i in range(4)]
        b = [_pt(i + 4, _MUM_LAT + 20 * _KM_DEG_LAT + i * 0.001, _MUM_LON) for i in range(4)]
        assert self._same_partition(a + b, eps_km=2.0, min_pts=3)

    def test_one_cluster_one_noise(self):
        pts = [
            _pt(0, _MUM_LAT, _MUM_LON),
            _pt(1, _MUM_LAT + 0.001, _MUM_LON),
            _pt(2, _MUM_LAT + 0.002, _MUM_LON),
            _pt(3, _MUM_LAT + 20 * _KM_DEG_LAT, _MUM_LON),  # isolated
        ]
        assert self._same_partition(pts, eps_km=2.0, min_pts=3)

    def test_randomised_50_points(self):
        rng = random.Random(7)
        pts = [
            _pt(i, _MUM_LAT + rng.uniform(-0.05, 0.05), _MUM_LON + rng.uniform(-0.05, 0.05))
            for i in range(50)
        ]
        assert self._same_partition(pts, eps_km=2.0, min_pts=3)

    def test_all_noise(self):
        """Points far apart all become noise — both implementations agree."""
        pts = [_pt(i, _MUM_LAT + i * 0.5, _MUM_LON) for i in range(5)]
        assert self._same_partition(pts, eps_km=0.1, min_pts=3)

    def test_single_cluster(self):
        pts = [_pt(i, _MUM_LAT + i * 0.0005, _MUM_LON) for i in range(10)]
        assert self._same_partition(pts, eps_km=2.0, min_pts=3)


# ── API endpoint tests ────────────────────────────────────────────────────────

@pytest.fixture
def mock_surv_repo():
    return AsyncMock()


@pytest.fixture
def hotspot_client(mock_surv_repo):
    mock_bus = AsyncMock()
    mock_hospital = AsyncMock()
    mock_emergency = AsyncMock()
    mock_outbreak = AsyncMock()

    app.dependency_overrides[get_bus] = lambda: mock_bus
    app.dependency_overrides[get_hospital_repo] = lambda: mock_hospital
    app.dependency_overrides[get_emergency_repo] = lambda: mock_emergency
    app.dependency_overrides[get_outbreak_repo] = lambda: mock_outbreak
    app.dependency_overrides[get_surveillance_repo] = lambda: mock_surv_repo

    yield TestClient(app), mock_surv_repo
    app.dependency_overrides.clear()


class TestHotspotsEndpoint:
    def _make_reports(self, n: int, base_lat: float, base_lon: float, id_start: int = 0) -> list:
        return [
            _report(id_start + i, base_lat + i * 0.001, base_lon, cases=50)
            for i in range(n)
        ]

    def test_returns_200_with_cluster_structure(self, hotspot_client):
        client, repo = hotspot_client
        repo.reports_for_clustering = AsyncMock(
            return_value=self._make_reports(5, _MUM_LAT, _MUM_LON)
        )
        resp = client.get("/surveillance/hotspots")
        assert resp.status_code == 200
        body = resp.json()
        assert "clusters" in body
        assert "noise_points" in body
        assert "eps_km" in body
        assert "min_pts" in body
        assert "report_count" in body
        assert "cluster_count" in body

    def test_cluster_count_excludes_noise(self, hotspot_client):
        client, repo = hotspot_client
        # 3 tight reports (cluster) + 1 isolated report (noise)
        tight = self._make_reports(3, _MUM_LAT, _MUM_LON)
        noise = [_report(99, _MUM_LAT + 20 * _KM_DEG_LAT, _MUM_LON, cases=1)]
        repo.reports_for_clustering = AsyncMock(return_value=tight + noise)
        resp = client.get("/surveillance/hotspots?eps_km=2.0&min_pts=3")
        body = resp.json()
        assert body["cluster_count"] == 1
        assert len(body["noise_points"]) == 1

    def test_eps_and_min_pts_echoed(self, hotspot_client):
        client, repo = hotspot_client
        repo.reports_for_clustering = AsyncMock(return_value=[])
        resp = client.get("/surveillance/hotspots?eps_km=1.5&min_pts=5")
        body = resp.json()
        assert body["eps_km"] == 1.5
        assert body["min_pts"] == 5

    def test_report_count_reflects_input(self, hotspot_client):
        client, repo = hotspot_client
        repo.reports_for_clustering = AsyncMock(
            return_value=self._make_reports(7, _MUM_LAT, _MUM_LON)
        )
        resp = client.get("/surveillance/hotspots")
        assert resp.json()["report_count"] == 7

    def test_empty_reports_returns_200(self, hotspot_client):
        client, repo = hotspot_client
        repo.reports_for_clustering = AsyncMock(return_value=[])
        resp = client.get("/surveillance/hotspots")
        assert resp.status_code == 200
        body = resp.json()
        assert body["clusters"] == []
        assert body["noise_points"] == []
        assert body["cluster_count"] == 0

    def test_disease_filter_forwarded(self, hotspot_client):
        client, repo = hotspot_client
        repo.reports_for_clustering = AsyncMock(return_value=[])
        client.get("/surveillance/hotspots?disease=dengue")
        _, kwargs = repo.reports_for_clustering.call_args
        assert kwargs.get("disease") == "dengue"

    def test_cluster_has_required_fields(self, hotspot_client):
        client, repo = hotspot_client
        repo.reports_for_clustering = AsyncMock(
            return_value=self._make_reports(4, _MUM_LAT, _MUM_LON)
        )
        resp = client.get("/surveillance/hotspots?min_pts=2")
        body = resp.json()
        assert len(body["clusters"]) > 0
        c = body["clusters"][0]
        for field in ("cluster_id", "centroid_lat", "centroid_lon",
                      "total_cases", "report_count", "radius_km", "member_ids"):
            assert field in c, f"missing field: {field}"

    def test_eps_zero_rejected(self, hotspot_client):
        client, _ = hotspot_client
        resp = client.get("/surveillance/hotspots?eps_km=0")
        assert resp.status_code == 422

    def test_min_pts_zero_rejected(self, hotspot_client):
        client, _ = hotspot_client
        resp = client.get("/surveillance/hotspots?min_pts=0")
        assert resp.status_code == 422
