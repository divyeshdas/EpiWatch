"""
Tests for the binary min-heap, Dijkstra algorithm, and POST /route endpoint.

All graph tests use the synthetic grid fixture — no database, no OSM data.
The grid has uniform edge weights (_DIST_M, _TIME_S) so shortest-path costs
are hand-verifiable: a Manhattan path of k steps costs k * weight_per_step.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.graph.dijkstra import PathResult, dijkstra
from app.graph.heap import MinHeap
from app.graph.kdtree import KDTree
from app.graph.road_graph import RoadGraph
from tests.graph_fixtures import _DIST_M, _LAT0, _LON0, _TIME_S, make_grid, node_id


# ── shared helper ─────────────────────────────────────────────────────────────

def _make_road_graph(n: int) -> RoadGraph:
    """Build an n×n RoadGraph from the synthetic grid fixture."""
    nodes, edges = make_grid(n)
    g = RoadGraph()
    for nid, lat, lon in nodes:
        g.add_node(nid, lat, lon)
    for src, tgt, dist_m, tt_s in edges:
        g.add_edge(src, tgt, dist_m, tt_s)
    return g


# ── MinHeap ───────────────────────────────────────────────────────────────────

class TestMinHeap:

    def test_empty_heap_has_length_zero(self):
        assert len(MinHeap()) == 0

    def test_empty_heap_is_falsy(self):
        assert not MinHeap()

    def test_nonempty_heap_is_truthy(self):
        h = MinHeap()
        h.push(1.0, 1)
        assert h

    def test_single_push_then_pop(self):
        h = MinHeap()
        h.push(5.0, 42)
        assert len(h) == 1
        pri, item = h.pop_min()
        assert pri == 5.0
        assert item == 42
        assert len(h) == 0

    def test_pop_returns_minimum_priority_first(self):
        h = MinHeap()
        for pri in (3.0, 1.0, 4.0, 1.5, 9.0, 2.0):
            h.push(pri, 0)
        pops = [h.pop_min()[0] for _ in range(6)]
        assert pops == sorted(pops)

    def test_heap_sorts_many_pushes_correctly(self):
        h = MinHeap()
        priorities = [7, 2, 9, 1, 5, 3, 8, 4, 6]
        for i, p in enumerate(priorities):
            h.push(float(p), i)
        pops = [h.pop_min()[0] for _ in range(len(priorities))]
        assert pops == sorted(float(p) for p in priorities)

    def test_equal_priorities_all_elements_returned(self):
        h = MinHeap()
        for item in (10, 20, 30):
            h.push(1.0, item)
        items = {h.pop_min()[1] for _ in range(3)}
        assert items == {10, 20, 30}
        assert len(h) == 0

    def test_peek_does_not_remove_element(self):
        h = MinHeap()
        h.push(2.0, 1)
        h.push(1.0, 2)
        pri, _ = h.peek()
        assert pri == 1.0
        assert len(h) == 2  # still two elements

    def test_peek_returns_minimum(self):
        h = MinHeap()
        h.push(99.0, 1)
        h.push(0.5, 2)
        assert h.peek()[0] == 0.5

    def test_interleaved_push_and_pop(self):
        h = MinHeap()
        h.push(3.0, 1)
        h.push(1.0, 2)
        assert h.pop_min() == (1.0, 2)
        h.push(0.5, 3)
        assert h.pop_min() == (0.5, 3)
        assert h.pop_min() == (3.0, 1)


# ── Dijkstra ──────────────────────────────────────────────────────────────────

class TestDijkstra:

    def test_source_equals_target_returns_trivial_path(self):
        g = _make_road_graph(5)
        nid = node_id(2, 2, 5)
        result = dijkstra(g, nid, nid)
        assert result is not None
        assert result.node_ids == [nid]
        assert result.total_distance_m == 0.0
        assert result.total_travel_time_s == 0.0

    def test_single_hop_path(self):
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        tgt = node_id(0, 1, 5)  # immediately right
        result = dijkstra(g, src, tgt)
        assert result is not None
        assert result.node_ids == [src, tgt]
        assert result.total_distance_m == pytest.approx(_DIST_M)
        assert result.total_travel_time_s == pytest.approx(_TIME_S)

    def test_corner_to_corner_cost_on_5x5_grid(self):
        """
        From (0,0) to (4,4): Manhattan distance = 8 steps on a uniform grid.
        All shortest paths share the same cost; Dijkstra finds one of them.
        """
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        tgt = node_id(4, 4, 5)
        result = dijkstra(g, src, tgt)
        assert result is not None
        assert result.total_distance_m == pytest.approx(8 * _DIST_M)
        assert result.total_travel_time_s == pytest.approx(8 * _TIME_S)

    def test_corner_to_corner_path_has_9_nodes(self):
        """8 steps on a Manhattan path = 9 nodes in the ordered list."""
        g = _make_road_graph(5)
        result = dijkstra(g, node_id(0, 0, 5), node_id(4, 4, 5))
        assert result is not None
        assert len(result.node_ids) == 9

    def test_path_is_valid_sequence_of_edges(self):
        """Every consecutive pair in the returned path must be connected by an edge."""
        nodes, edges = make_grid(5)
        edge_set = {(src, tgt) for src, tgt, _, _ in edges}
        g = _make_road_graph(5)
        result = dijkstra(g, node_id(1, 0, 5), node_id(3, 4, 5))
        assert result is not None
        for a, b in zip(result.node_ids, result.node_ids[1:]):
            assert (a, b) in edge_set, f"no directed edge {a}→{b} found in graph"

    def test_both_metrics_populated_regardless_of_weight(self):
        """
        Even when weight=distance_m, travel_time_s is still summed from
        the actual edges and returned in the PathResult.
        """
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        tgt = node_id(0, 3, 5)  # 3 hops right
        result = dijkstra(g, src, tgt, weight=lambda e: e.distance_m)
        assert result is not None
        assert result.total_distance_m == pytest.approx(3 * _DIST_M)
        assert result.total_travel_time_s == pytest.approx(3 * _TIME_S)

    def test_unreachable_node_returns_none(self):
        """
        A node with no incoming edges cannot be reached from any other node.
        Dijkstra must return None cleanly — no exception.
        """
        g = RoadGraph()
        g.add_node(1, 19.0, 72.85)
        g.add_node(2, 19.1, 72.85)
        # Intentionally no edges — two completely isolated nodes
        result = dijkstra(g, 1, 2)
        assert result is None

    def test_disconnected_components_return_none(self):
        """Two connected sub-graphs with no bridge: source in A, target in B."""
        g = RoadGraph()
        # Component A: nodes 1–2, connected
        g.add_node(1, 19.00, 72.85)
        g.add_node(2, 19.01, 72.85)
        g.add_edge(1, 2, 1000.0, 120.0)
        g.add_edge(2, 1, 1000.0, 120.0)
        # Component B: nodes 3–4, connected internally but not to A
        g.add_node(3, 19.10, 72.90)
        g.add_node(4, 19.11, 72.90)
        g.add_edge(3, 4, 1000.0, 120.0)
        g.add_edge(4, 3, 1000.0, 120.0)
        assert dijkstra(g, 1, 4) is None

    def test_path_start_and_end_match_request(self):
        g = _make_road_graph(5)
        src = node_id(1, 2, 5)
        tgt = node_id(3, 0, 5)
        result = dijkstra(g, src, tgt)
        assert result is not None
        assert result.node_ids[0] == src
        assert result.node_ids[-1] == tgt


# ── POST /route endpoint ──────────────────────────────────────────────────────

class TestRouteEndpoint:
    """HTTP tests — algorithm is real; DB and event bus are mocked."""

    def _make_graph_and_tree(self, n: int) -> tuple[RoadGraph, KDTree]:
        nodes, edges = make_grid(n)
        g = RoadGraph()
        for nid, lat, lon in nodes:
            g.add_node(nid, lat, lon)
        for src, tgt, dist_m, tt_s in edges:
            g.add_edge(src, tgt, dist_m, tt_s)
        return g, KDTree(nodes)

    def test_route_found_returns_path(self, client, mock_hospital_repo):
        g, tree = self._make_graph_and_tree(5)
        hospital = MagicMock()
        hospital.nearest_node_id = node_id(4, 4, 5)  # far corner
        mock_hospital_repo.get_by_id.return_value = hospital

        with patch("app.graph.loader.road_graph", g), \
             patch("app.graph.loader.kd_tree", tree):
            resp = client.post("/route", json={
                "latitude": _LAT0,      # snaps to node(0,0) = 1
                "longitude": _LON0,
                "hospital_id": 1,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["route"] is not None
        r = data["route"]
        assert r["node_count"] == 9          # 8-step Manhattan path → 9 nodes
        assert r["total_travel_time_s"] == pytest.approx(8 * _TIME_S, rel=1e-3)
        assert r["total_distance_m"] == pytest.approx(8 * _DIST_M, rel=1e-3)
        assert len(r["path"]) == 9
        # First node should be at the emergency coordinate (node 0,0)
        assert r["path"][0]["node_id"] == node_id(0, 0, 5)

    def test_no_path_returns_200_with_null_route(self, client, mock_hospital_repo):
        """An unreachable hospital must never raise a 500."""
        g = RoadGraph()
        g.add_node(1, _LAT0, _LON0)
        g.add_node(2, _LAT0 + 0.5, _LON0 + 0.5)
        tree = KDTree([(1, _LAT0, _LON0), (2, _LAT0 + 0.5, _LON0 + 0.5)])

        hospital = MagicMock()
        hospital.nearest_node_id = 2   # isolated — no path from node 1
        mock_hospital_repo.get_by_id.return_value = hospital

        with patch("app.graph.loader.road_graph", g), \
             patch("app.graph.loader.kd_tree", tree):
            resp = client.post("/route", json={
                "latitude": _LAT0,
                "longitude": _LON0,
                "hospital_id": 1,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["route"] is None
        assert "no path" in data["reason"].lower()

    def test_hospital_not_found_returns_404(self, client, mock_hospital_repo):
        g, tree = self._make_graph_and_tree(3)
        mock_hospital_repo.get_by_id.return_value = None

        with patch("app.graph.loader.road_graph", g), \
             patch("app.graph.loader.kd_tree", tree):
            resp = client.post("/route", json={
                "latitude": _LAT0,
                "longitude": _LON0,
                "hospital_id": 999,
            })

        assert resp.status_code == 404

    def test_graph_not_ready_returns_503(self, client):
        with patch("app.graph.loader.kd_tree", None):
            resp = client.post("/route", json={
                "latitude": _LAT0,
                "longitude": _LON0,
                "hospital_id": 1,
            })

        assert resp.status_code == 503

    def test_hospital_not_snapped_returns_clean_response(self, client, mock_hospital_repo):
        g, tree = self._make_graph_and_tree(3)
        hospital = MagicMock()
        hospital.nearest_node_id = None  # snap script not yet run
        mock_hospital_repo.get_by_id.return_value = hospital

        with patch("app.graph.loader.road_graph", g), \
             patch("app.graph.loader.kd_tree", tree):
            resp = client.post("/route", json={
                "latitude": _LAT0,
                "longitude": _LON0,
                "hospital_id": 1,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["route"] is None
        assert "snap" in data["reason"].lower()

    def test_route_emits_event(self, client, mock_bus, mock_hospital_repo):
        g, tree = self._make_graph_and_tree(3)
        hospital = MagicMock()
        hospital.nearest_node_id = node_id(2, 2, 3)
        mock_hospital_repo.get_by_id.return_value = hospital

        with patch("app.graph.loader.road_graph", g), \
             patch("app.graph.loader.kd_tree", tree):
            resp = client.post("/route", json={
                "latitude": _LAT0,
                "longitude": _LON0,
                "hospital_id": 1,
            })

        assert resp.status_code == 200
        mock_bus.publish.assert_called_once()
        event = mock_bus.publish.call_args[0][0]
        assert event.payload["hospital_id"] == 1
        assert event.payload["total_travel_time_s"] > 0
