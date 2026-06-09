"""
Tests for the K-D tree, in-memory road graph, and hospital snap logic.

All tests use the synthetic grid — no OSM download, no database connection.
"""
import math

import pytest

from app.graph.haversine import haversine
from app.graph.kdtree import KDTree
from app.graph.road_graph import RoadGraph
from tests.graph_fixtures import _LAT0, _LON0, _STEP, make_grid, node_id


# ── helpers ────────────────────────────────────────────────────────────────────

def brute_nearest(
    nodes: list[tuple[int, float, float]],
    qlat: float,
    qlon: float,
) -> tuple[int, float, float, float]:
    """O(n) linear scan — ground truth for K-D tree correctness tests."""
    best_id, best_lat, best_lon, best_dist = -1, 0.0, 0.0, float("inf")
    for nid, lat, lon in nodes:
        d = haversine(qlat, qlon, lat, lon)
        if d < best_dist:
            best_id, best_lat, best_lon, best_dist = nid, lat, lon, d
    return best_id, best_lat, best_lon, best_dist


# ── K-D tree: correctness ──────────────────────────────────────────────────────

class TestKDTreeNearestNeighbour:
    """K-D tree result must match the brute-force O(n) scan for every query."""

    GRID_N = 7  # 7×7 = 49 nodes — small but non-trivial

    @pytest.fixture(scope="class")
    def grid(self):
        nodes, _ = make_grid(self.GRID_N)
        return nodes

    @pytest.fixture(scope="class")
    def tree(self, grid):
        return KDTree(grid)

    @pytest.mark.parametrize("qlat, qlon", [
        # interior point — nearest is grid node
        (_LAT0 + 0.005, _LON0 + 0.005),
        # near top-left corner
        (_LAT0 - 0.003, _LON0 - 0.003),
        # near bottom-right corner
        (_LAT0 + (7 - 1) * _STEP + 0.004, _LON0 + (7 - 1) * _STEP + 0.004),
        # centre of the grid (exact node)
        (_LAT0 + 3 * _STEP, _LON0 + 3 * _STEP),
        # 40 % of the way between two horizontal neighbours → clearly the left one
        (_LAT0 + 2 * _STEP, _LON0 + 1.4 * _STEP),
        # 40 % of the way between two vertical neighbours → clearly the lower one
        (_LAT0 + 1.4 * _STEP, _LON0 + 4 * _STEP),
        # far outside the grid to the north-east
        (_LAT0 + 0.2, _LON0 + 0.2),
    ])
    def test_matches_brute_force(self, tree, grid, qlat, qlon):
        kd_id, *_ = tree.nearest(qlat, qlon)
        bf_id, *_ = brute_nearest(grid, qlat, qlon)
        assert kd_id == bf_id, (
            f"K-D tree returned node {kd_id} but brute-force says {bf_id} "
            f"for query ({qlat:.4f}, {qlon:.4f})"
        )

    def test_exact_node_query_returns_zero_distance(self, tree):
        """Querying exactly at a node coordinate should return that node with d ≈ 0."""
        lat = _LAT0 + 2 * _STEP
        lon = _LON0 + 3 * _STEP
        expected_id = node_id(2, 3, self.GRID_N)
        nid, _, _, dist = tree.nearest(lat, lon)
        assert nid == expected_id
        assert dist < 1.0  # less than 1 metre

    def test_size(self, tree):
        assert len(tree) == self.GRID_N ** 2


# ── K-D tree: distance metric ─────────────────────────────────────────────────

class TestHaversine:
    def test_zero_distance(self):
        assert haversine(19.0, 72.8, 19.0, 72.8) == pytest.approx(0.0, abs=1e-6)

    def test_one_degree_latitude(self):
        # 1° of latitude ≈ 110 574 m at the equator
        d = haversine(0.0, 0.0, 1.0, 0.0)
        assert 110_000 < d < 111_500

    def test_symmetric(self):
        d1 = haversine(19.0, 72.8, 18.9, 72.9)
        d2 = haversine(18.9, 72.9, 19.0, 72.8)
        assert d1 == pytest.approx(d2, rel=1e-9)


# ── RoadGraph: adjacency list ──────────────────────────────────────────────────

class TestRoadGraph:
    @pytest.fixture
    def graph_3x3(self):
        nodes, edges = make_grid(3)
        g = RoadGraph()
        for nid, lat, lon in nodes:
            g.add_node(nid, lat, lon)
        for src, tgt, dist, time in edges:
            g.add_edge(src, tgt, dist, time)
        return g

    def test_node_count(self, graph_3x3):
        assert graph_3x3.node_count() == 9

    def test_edge_count(self, graph_3x3):
        # 3×3 grid: 12 horizontal/vertical pairs × 2 directions = 24 directed edges
        assert graph_3x3.edge_count() == 24

    def test_corner_node_has_two_neighbours(self, graph_3x3):
        # node_id(0,0,3) = 1 — connects right and down only
        neighbours = graph_3x3.neighbors(node_id(0, 0, 3))
        assert len(neighbours) == 2

    def test_interior_node_has_four_neighbours(self, graph_3x3):
        # node_id(1,1,3) = 5 — connects up/down/left/right
        neighbours = graph_3x3.neighbors(node_id(1, 1, 3))
        assert len(neighbours) == 4

    def test_edge_weights_are_positive(self, graph_3x3):
        for edges in (graph_3x3.neighbors(nid) for nid in range(1, 10)):
            for e in edges:
                assert e.distance_m > 0
                assert e.travel_time_s > 0

    def test_get_coords(self, graph_3x3):
        lat, lon = graph_3x3.get_coords(node_id(0, 0, 3))
        assert lat == pytest.approx(_LAT0, abs=1e-9)
        assert lon == pytest.approx(_LON0, abs=1e-9)

    def test_bounding_box(self, graph_3x3):
        bbox = graph_3x3.bounding_box()
        assert bbox["min_lat"] == pytest.approx(_LAT0, abs=1e-9)
        assert bbox["max_lat"] == pytest.approx(_LAT0 + 2 * _STEP, rel=1e-6)
        assert bbox["min_lon"] == pytest.approx(_LON0, abs=1e-9)
        assert bbox["max_lon"] == pytest.approx(_LON0 + 2 * _STEP, rel=1e-6)

    def test_all_node_tuples_length(self, graph_3x3):
        tuples = graph_3x3.all_node_tuples()
        assert len(tuples) == 9


# ── Hospital snap sanity ──────────────────────────────────────────────────────

class TestHospitalSnap:
    """Verify that snapping a coordinate finds the expected node."""

    def test_snap_at_exact_node(self):
        nodes, _ = make_grid(5)
        tree = KDTree(nodes)
        # The node at (2, 3) in a 5×5 grid
        expected = node_id(2, 3, 5)
        lat = _LAT0 + 2 * _STEP
        lon = _LON0 + 3 * _STEP
        found_id, _, _, dist_m = tree.nearest(lat, lon)
        assert found_id == expected
        assert dist_m < 1.0

    def test_snap_hospital_outside_grid_goes_to_boundary(self):
        """A coordinate well outside the grid should snap to the boundary node."""
        nodes, _ = make_grid(5)
        tree = KDTree(nodes)
        # Far north-east of the grid
        query_lat = _LAT0 + 10 * _STEP
        query_lon = _LON0 + 10 * _STEP
        expected = node_id(4, 4, 5)  # bottom-right corner of 5×5 grid (max i, max j)
        found_id, _, _, _ = tree.nearest(query_lat, query_lon)
        assert found_id == expected
