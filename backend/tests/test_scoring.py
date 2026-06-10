"""
Tests for the hospital scoring engine and POST /emergency/{id}/assign endpoint.

─── Test strategy ────────────────────────────────────────────────────────────
The scorer is a pure function (no I/O), so the bulk of the tests call
score_hospitals() directly with synthetic hospitals and a small RoadGraph.
This is fast (no DB, no HTTP) and focuses on the business logic.

The endpoint tests use the same mock-override pattern as the routing tests:
repos and event bus are replaced with AsyncMocks; graph is patched in-memory.

─── Grid layout ──────────────────────────────────────────────────────────────
All scoring tests use a 5×5 grid.  Emergency source is at node (0,0) = node 1.

Hospitals are placed at:
  NEAR    node (0,2) = node 3  — 2 horizontal hops  (~265 s travel)
  MEDIUM  node (0,4) = node 5  — 4 horizontal hops  (~530 s travel)
  FAR     node (4,4) = node 25 — 8 Manhattan hops   (~1061 s travel)

These positions allow straightforward hand-verification of expected rankings.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.graph.kdtree import KDTree
from app.graph.road_graph import RoadGraph
from app.infra.models import EmergencyCase, Hospital
from app.scoring.scorer import score_hospitals
from tests.graph_fixtures import _DIST_M, _LAT0, _LON0, _STEP, _TIME_S, make_grid, node_id
from tests.conftest import make_hospital, make_case


# ── graph + hospital fixtures ─────────────────────────────────────────────────

def _make_road_graph(n: int) -> RoadGraph:
    nodes, edges = make_grid(n)
    g = RoadGraph()
    for nid, lat, lon in nodes:
        g.add_node(nid, lat, lon)
    for src, tgt, dist_m, tt_s in edges:
        g.add_edge(src, tgt, dist_m, tt_s)
    return g


def _hospital(
    id: int,
    name: str,
    nearest_node_id: int | None,
    *,
    total_beds: int = 200,
    available_beds: int = 80,
    total_icu_beds: int = 40,
    available_icu_beds: int = 16,
    current_load: int = 120,
    specializations: list[str] | None = None,
) -> Hospital:
    h = Hospital(
        id=id,
        name=name,
        latitude=_LAT0,
        longitude=_LON0,
        total_beds=total_beds,
        available_beds=available_beds,
        total_icu_beds=total_icu_beds,
        available_icu_beds=available_icu_beds,
        emergency_capacity=50,
        current_load=current_load,
        specializations=specializations or ["general"],
        updated_at=datetime.now(timezone.utc),
        nearest_node_id=nearest_node_id,
    )
    return h


# ── Pure scorer tests ─────────────────────────────────────────────────────────

class TestScoringFilter:
    """Filtering rejects hospitals that physically cannot serve the patient."""

    def test_not_snapped_is_filtered(self):
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "Unsnapped", nearest_node_id=None),
            _hospital(2, "Snapped", nearest_node_id=node_id(0, 2, 5)),
        ]
        result = score_hospitals(hospitals, src, "STABLE", g)

        filtered_names = {f.hospital.name for f in result.filtered_out}
        scored_names = {c.hospital.name for c in result.scored}
        assert "Unsnapped" in filtered_names
        assert "Snapped" in scored_names
        assert any("snap" in f.reason.lower() for f in result.filtered_out
                   if f.hospital.name == "Unsnapped")

    def test_zero_beds_is_filtered(self):
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "Full", nearest_node_id=node_id(0, 2, 5), available_beds=0),
            _hospital(2, "Open", nearest_node_id=node_id(0, 4, 5)),
        ]
        result = score_hospitals(hospitals, src, "STABLE", g)

        assert len(result.scored) == 1
        assert result.scored[0].hospital.name == "Open"
        assert any("beds" in f.reason.lower() for f in result.filtered_out)

    def test_critical_requires_icu(self):
        """CRITICAL patient: hospital with 0 ICU beds is excluded."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "No ICU",
                      nearest_node_id=node_id(0, 2, 5),
                      total_icu_beds=20, available_icu_beds=0),
            _hospital(2, "Has ICU",
                      nearest_node_id=node_id(0, 4, 5),
                      total_icu_beds=30, available_icu_beds=10),
        ]
        result = score_hospitals(hospitals, src, "CRITICAL", g)

        assert len(result.scored) == 1
        assert result.scored[0].hospital.name == "Has ICU"
        filtered_reasons = {f.hospital.name: f.reason for f in result.filtered_out}
        assert "No ICU" in filtered_reasons
        assert "ICU" in filtered_reasons["No ICU"]

    def test_cardiac_requires_icu(self):
        """CARDIAC patient also requires ICU (as per spec: CRITICAL/CARDIAC need ICU)."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "No ICU",
                      nearest_node_id=node_id(0, 2, 5),
                      total_icu_beds=20, available_icu_beds=0,
                      specializations=["cardiac"]),
            _hospital(2, "Cardiac + ICU",
                      nearest_node_id=node_id(0, 4, 5),
                      total_icu_beds=30, available_icu_beds=10,
                      specializations=["cardiac"]),
        ]
        result = score_hospitals(hospitals, src, "CARDIAC", g)

        assert len(result.scored) == 1
        assert result.scored[0].hospital.name == "Cardiac + ICU"

    def test_stable_does_not_require_icu(self):
        """STABLE patient: hospital with 0 ICU beds still passes the filter."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "No ICU",
                      nearest_node_id=node_id(0, 2, 5),
                      total_icu_beds=0, available_icu_beds=0),
        ]
        result = score_hospitals(hospitals, src, "STABLE", g)
        assert len(result.scored) == 1

    def test_unreachable_node_is_filtered(self):
        """A node that exists in the graph but is unreachable from src is filtered."""
        g = RoadGraph()
        # Two disconnected islands
        g.add_node(1, _LAT0, _LON0)                  # src
        g.add_node(2, _LAT0 + _STEP, _LON0)          # reachable
        g.add_node(3, _LAT0 + 2 * _STEP, _LON0)      # isolated — no path from 1
        g.add_edge(1, 2, _DIST_M, _TIME_S)
        g.add_edge(2, 1, _DIST_M, _TIME_S)

        hospitals = [
            _hospital(1, "Reachable",   nearest_node_id=2),
            _hospital(2, "Unreachable", nearest_node_id=3),
        ]
        result = score_hospitals(hospitals, 1, "STABLE", g)

        assert len(result.scored) == 1
        assert result.scored[0].hospital.name == "Reachable"
        assert any("unreachable" in f.reason.lower() for f in result.filtered_out
                   if f.hospital.name == "Unreachable")

    def test_max_travel_time_cap(self):
        """Hospitals beyond the travel time cap are excluded."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "Near",   nearest_node_id=node_id(0, 2, 5)),  # ~265 s
            _hospital(2, "Far",    nearest_node_id=node_id(4, 4, 5)),  # ~1061 s
        ]
        # Cap at 400 s — only the near hospital should survive
        result = score_hospitals(hospitals, src, "STABLE", g, max_travel_time_s=400.0)

        assert len(result.scored) == 1
        assert result.scored[0].hospital.name == "Near"
        assert any("exceeds" in f.reason.lower() for f in result.filtered_out)


class TestScoringLogic:
    """
    Core ranking tests demonstrating condition-dependent weight behaviour.

    Design intent:
      NEAR    — 2 hops, no ICU, saturated, no specialty
      MEDIUM  — 4 hops, has ICU, medium load, has cardiac spec
      FAR     — 8 hops, has ICU, good load, has trauma spec

    This setup lets us verify that condition weights deterministically change
    which hospital wins, even with the same three candidates.
    """

    @pytest.fixture
    def graph(self):
        return _make_road_graph(5)

    @pytest.fixture
    def hospitals(self):
        return [
            _hospital(1, "NEAR",
                      nearest_node_id=node_id(0, 2, 5),
                      total_beds=100, available_beds=5,
                      total_icu_beds=20, available_icu_beds=0,
                      current_load=95,
                      specializations=["general"]),
            _hospital(2, "MEDIUM",
                      nearest_node_id=node_id(0, 4, 5),
                      total_beds=200, available_beds=80,
                      total_icu_beds=40, available_icu_beds=20,
                      current_load=120,
                      specializations=["cardiac", "general"]),
            _hospital(3, "FAR",
                      nearest_node_id=node_id(4, 4, 5),
                      total_beds=300, available_beds=150,
                      total_icu_beds=50, available_icu_beds=30,
                      current_load=150,
                      specializations=["trauma", "general"]),
        ]

    def test_critical_filters_no_icu_and_picks_faster_icu_hospital(
        self, graph, hospitals
    ):
        """
        CRITICAL: NEAR (no ICU) is filtered out.
        MEDIUM wins over FAR because speed (weight=0.45) favours the closer hospital —
        even though FAR has more absolute ICU beds, MEDIUM's 4-hop advantage
        dominates at CRITICAL's travel_time weight of 0.45.
        """
        src = node_id(0, 0, 5)
        result = score_hospitals(hospitals, src, "CRITICAL", graph)

        filtered_names = {f.hospital.name for f in result.filtered_out}
        assert "NEAR" in filtered_names, "NEAR should be filtered (no ICU)"

        assert len(result.scored) == 2
        assert result.scored[0].hospital.name == "MEDIUM", (
            "MEDIUM should win for CRITICAL: faster + has ICU"
        )
        assert result.scored[0].rank == 1
        assert result.scored[1].rank == 2

    def test_cardiac_prefers_specialization_over_proximity(
        self, graph, hospitals
    ):
        """
        CARDIAC: NEAR (no ICU) is filtered out.
        MEDIUM wins over FAR: MEDIUM has 'cardiac' spec (penalty=0) while
        FAR has 'trauma' spec (penalty=1 for cardiac).  The specialization
        weight (0.40) dominates, so MEDIUM beats FAR despite being equidistant
        on other factors.
        """
        src = node_id(0, 0, 5)
        result = score_hospitals(hospitals, src, "CARDIAC", graph)

        scored_names = [c.hospital.name for c in result.scored]
        assert "NEAR" not in scored_names, "NEAR should be filtered (no ICU for CARDIAC)"
        assert result.scored[0].hospital.name == "MEDIUM", (
            "MEDIUM should win for CARDIAC: has 'cardiac' specialization"
        )
        # Verify specialization drove the decision
        medium_spec = result.scored[0].factors["specialization"]
        assert medium_spec.penalty == pytest.approx(0.0), "cardiac spec match → 0 penalty"

    def test_stable_deprioritises_saturated_nearest(self, graph, hospitals):
        """
        STABLE: all three hospitals pass filter (no ICU requirement).
        NEAR (95% load, 5% bed availability) should NOT be rank 1.
        MEDIUM and FAR both have better load and bed profiles — the system
        demonstrates load-balancing, not nearest-wins.
        """
        src = node_id(0, 0, 5)
        result = score_hospitals(hospitals, src, "STABLE", graph)

        assert len(result.scored) == 3, "all pass filter for STABLE"
        best = result.scored[0]
        assert best.hospital.name != "NEAR", (
            "NEAR (95% load) should not win for STABLE — load-balancing should prefer"
            " a less-burdened hospital even if it is farther"
        )

    def test_different_conditions_produce_different_rankings(self, graph):
        """
        Verify that changing patient condition changes which hospital ranks first.
        This is the core proof that the system is condition-aware triage, not
        nearest-hospital dispatch.

        Purpose-built fixture:
          FAST-NO-ICU    — 1 hop, good load, no ICU, no specialty tag
          CARDIAC-ICU    — 3 hops, has ICU, 'cardiac' specialization
          TRAUMA-ICU     — 4 hops, has ICU, 'trauma' specialization

        Expected outcomes (hand-verified):
          STABLE   → FAST-NO-ICU wins  (nearest, good load; ICU not required)
          CRITICAL → CARDIAC-ICU wins  (nearest ICU hospital; speed weight 0.45)
          CARDIAC  → CARDIAC-ICU wins  (cardiac spec; spec weight 0.40 dominates)

        Key demonstration: FAST-NO-ICU wins for STABLE but is filtered out for
        CRITICAL and CARDIAC (no ICU beds).  The same hospital scores very
        differently depending solely on the patient's condition.
        """
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "FAST-NO-ICU",
                      nearest_node_id=node_id(0, 1, 5),
                      total_beds=200, available_beds=100, current_load=100,
                      total_icu_beds=0, available_icu_beds=0,
                      specializations=["general"]),
            _hospital(2, "CARDIAC-ICU",
                      nearest_node_id=node_id(0, 3, 5),
                      total_beds=200, available_beds=100, current_load=100,
                      total_icu_beds=40, available_icu_beds=20,
                      specializations=["cardiac"]),
            _hospital(3, "TRAUMA-ICU",
                      nearest_node_id=node_id(0, 4, 5),
                      total_beds=200, available_beds=100, current_load=100,
                      total_icu_beds=40, available_icu_beds=20,
                      specializations=["trauma"]),
        ]

        stable_result   = score_hospitals(hospitals, src, "STABLE",   graph)
        critical_result = score_hospitals(hospitals, src, "CRITICAL",  graph)
        cardiac_result  = score_hospitals(hospitals, src, "CARDIAC",   graph)

        # STABLE: all three pass filter, FAST-NO-ICU wins (nearest, good load)
        assert stable_result.scored
        assert stable_result.scored[0].hospital.name == "FAST-NO-ICU", (
            "STABLE: nearest non-saturated hospital should win when ICU not required"
        )

        # CRITICAL/CARDIAC: FAST-NO-ICU is filtered (no ICU); CARDIAC-ICU wins
        fast_in_critical_filtered = any(
            f.hospital.name == "FAST-NO-ICU" for f in critical_result.filtered_out
        )
        assert fast_in_critical_filtered, "FAST-NO-ICU must be filtered for CRITICAL (no ICU)"
        assert critical_result.scored[0].hospital.name == "CARDIAC-ICU", (
            "CRITICAL: nearest ICU hospital wins (travel weight 0.45 dominates)"
        )

        fast_in_cardiac_filtered = any(
            f.hospital.name == "FAST-NO-ICU" for f in cardiac_result.filtered_out
        )
        assert fast_in_cardiac_filtered, "FAST-NO-ICU must be filtered for CARDIAC (no ICU)"

        # The rank-1 winner changes between STABLE and CRITICAL
        assert stable_result.scored[0].hospital.name != critical_result.scored[0].hospital.name, (
            "STABLE and CRITICAL should produce different rank-1 winners, "
            "demonstrating that condition-dependent weights drive triage decisions"
        )


class TestScoringMath:
    """Verify the arithmetic invariants of the scoring model."""

    def test_score_breakdown_sums_to_total(self):
        """sum(contribution for each factor) == total_score (within float tolerance)."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "H1", nearest_node_id=node_id(0, 2, 5),
                      total_beds=200, available_beds=80,
                      total_icu_beds=40, available_icu_beds=20,
                      current_load=120, specializations=["general", "trauma"]),
            _hospital(2, "H2", nearest_node_id=node_id(0, 4, 5),
                      total_beds=300, available_beds=100,
                      total_icu_beds=60, available_icu_beds=15,
                      current_load=200, specializations=["cardiac"]),
        ]
        result = score_hospitals(hospitals, src, "CRITICAL", g)

        for candidate in result.scored:
            contrib_sum = sum(f.contribution for f in candidate.factors.values())
            assert contrib_sum == pytest.approx(candidate.total_score, abs=1e-9), (
                f"{candidate.hospital.name}: factor contributions {contrib_sum:.6f} "
                f"≠ total_score {candidate.total_score:.6f}"
            )

    def test_score_in_unit_interval(self):
        """total_score ∈ [0, 1] because weights sum to 1 and penalties ∈ [0, 1]."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "H", nearest_node_id=node_id(0, 2, 5)),
        ]
        result = score_hospitals(hospitals, src, "STABLE", g)
        for c in result.scored:
            assert 0.0 <= c.total_score <= 1.0 + 1e-9

    def test_rank_one_has_lowest_score(self):
        """candidates are sorted ascending — rank 1 must have the minimum score."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(i, f"H{i}", nearest_node_id=node_id(0, i, 5))
            for i in range(1, 5)
        ]
        result = score_hospitals(hospitals, src, "STABLE", g)
        assert result.scored, "expected at least one candidate"
        scores = [c.total_score for c in result.scored]
        assert scores == sorted(scores), "candidates must be sorted ascending by score"
        assert result.scored[0].rank == 1

    def test_single_candidate_travel_penalty_is_zero(self):
        """
        With only one candidate there is nothing to compare travel time against.
        The min-max normalization should yield 0 (no relative penalty).
        """
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [_hospital(1, "Only", nearest_node_id=node_id(0, 4, 5))]
        result = score_hospitals(hospitals, src, "STABLE", g)
        assert result.scored[0].factors["travel_time"].penalty == pytest.approx(0.0)

    def test_fastest_candidate_travel_penalty_is_zero(self):
        """The fastest hospital among multiple candidates gets travel penalty = 0."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "Near", nearest_node_id=node_id(0, 1, 5)),
            _hospital(2, "Far",  nearest_node_id=node_id(0, 4, 5)),
        ]
        result = score_hospitals(hospitals, src, "STABLE", g)
        near = next(c for c in result.scored if c.hospital.name == "Near")
        far = next(c for c in result.scored if c.hospital.name == "Far")
        assert near.factors["travel_time"].penalty == pytest.approx(0.0)
        assert far.factors["travel_time"].penalty == pytest.approx(1.0)

    def test_perfect_icu_penalty_is_zero(self):
        """A hospital with all ICU beds free gets icu penalty = 0."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "FullICU", nearest_node_id=node_id(0, 2, 5),
                      total_icu_beds=20, available_icu_beds=20),
        ]
        result = score_hospitals(hospitals, src, "STABLE", g)
        assert result.scored[0].factors["icu_availability"].penalty == pytest.approx(0.0)

    def test_specialization_match_gives_zero_penalty(self):
        """A hospital whose specialty matches the condition gets penalty = 0."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "Cardiac", nearest_node_id=node_id(0, 2, 5),
                      total_icu_beds=10, available_icu_beds=5,
                      specializations=["cardiac"]),
        ]
        result = score_hospitals(hospitals, src, "CARDIAC", g)
        assert result.scored[0].factors["specialization"].penalty == pytest.approx(0.0)

    def test_specialization_mismatch_gives_penalty_one(self):
        """A hospital whose specialty doesn't match the condition gets penalty = 1."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [
            _hospital(1, "General", nearest_node_id=node_id(0, 2, 5),
                      total_icu_beds=10, available_icu_beds=5,
                      specializations=["general"]),
        ]
        result = score_hospitals(hospitals, src, "CARDIAC", g)
        assert result.scored[0].factors["specialization"].penalty == pytest.approx(1.0)

    def test_no_candidates_returns_empty_scored(self):
        """When all hospitals fail filtering, scored list is empty."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        # All hospitals have 0 beds → filtered
        hospitals = [
            _hospital(i, f"H{i}", nearest_node_id=node_id(0, i, 5), available_beds=0)
            for i in range(1, 4)
        ]
        result = score_hospitals(hospitals, src, "STABLE", g)
        assert result.scored == []
        assert len(result.filtered_out) == 3


# ── Endpoint tests ────────────────────────────────────────────────────────────

class TestAssignEndpoint:
    """HTTP tests for POST /emergency/{id}/assign — algorithm is real, DB is mocked."""

    def _make_graph_and_tree(self, n: int) -> tuple[RoadGraph, KDTree]:
        nodes, edges = make_grid(n)
        g = RoadGraph()
        for nid, lat, lon in nodes:
            g.add_node(nid, lat, lon)
        for src, tgt, dist_m, tt_s in edges:
            g.add_edge(src, tgt, dist_m, tt_s)
        return g, KDTree(nodes)

    def _make_hospitals(self) -> list[Hospital]:
        """Two seeded hospitals: one has ICU, one doesn't."""
        return [
            _hospital(1, "Near No-ICU",
                      nearest_node_id=node_id(0, 1, 5),
                      total_icu_beds=20, available_icu_beds=0,
                      specializations=["general"]),
            _hospital(2, "Far With-ICU",
                      nearest_node_id=node_id(0, 4, 5),
                      total_icu_beds=40, available_icu_beds=20,
                      specializations=["trauma", "general"]),
        ]

    def test_assign_critical_returns_200_with_ranked_candidates(
        self, client, mock_hospital_repo, mock_emergency_repo
    ):
        g, tree = self._make_graph_and_tree(5)
        hospitals = self._make_hospitals()
        case = make_case({"id": 7, "patient_condition": "CRITICAL"})

        mock_emergency_repo.get_by_id.return_value = case
        mock_emergency_repo.assign.return_value = make_case({
            "id": 7,
            "patient_condition": "CRITICAL",
            "assigned_hospital_id": 2,
            "status": "ASSIGNED",
        })
        mock_hospital_repo.list_all.return_value = hospitals

        with patch("app.graph.loader.road_graph", g), \
             patch("app.graph.loader.kd_tree", tree):
            resp = client.post("/emergency/7/assign")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ASSIGNED"
        assert data["assigned_hospital_id"] == 2, (
            "Should assign Far With-ICU — Near No-ICU filtered (no ICU for CRITICAL)"
        )
        assert data["condition"] == "CRITICAL"
        assert len(data["candidates"]) == 1     # only the ICU hospital passes filter
        assert len(data["filtered_out"]) == 1   # Near No-ICU filtered out
        assert data["candidates"][0]["rank"] == 1

    def test_assign_response_contains_factor_breakdown(
        self, client, mock_hospital_repo, mock_emergency_repo
    ):
        g, tree = self._make_graph_and_tree(5)
        hospitals = [
            _hospital(1, "Hospital A",
                      nearest_node_id=node_id(0, 4, 5),
                      total_icu_beds=40, available_icu_beds=20),
        ]
        case = make_case({"id": 3, "patient_condition": "CRITICAL"})
        mock_emergency_repo.get_by_id.return_value = case
        mock_emergency_repo.assign.return_value = case
        mock_hospital_repo.list_all.return_value = hospitals

        with patch("app.graph.loader.road_graph", g), \
             patch("app.graph.loader.kd_tree", tree):
            resp = client.post("/emergency/3/assign")

        assert resp.status_code == 200
        candidate = resp.json()["candidates"][0]
        factors = candidate["factors"]

        # All six factors must be present (B4 adds "surge")
        expected_factors = {"travel_time", "bed_availability", "icu_availability",
                            "load_factor", "specialization", "surge"}
        assert set(factors.keys()) == expected_factors

        # Each factor has the required fields
        for name, f in factors.items():
            assert "penalty" in f, f"factor {name} missing 'penalty'"
            assert "weight" in f, f"factor {name} missing 'weight'"
            assert "contribution" in f, f"factor {name} missing 'contribution'"
            assert 0.0 <= f["penalty"] <= 1.0 + 1e-9, f"{name} penalty out of range"

        # Contributions sum to total_score
        contrib_sum = sum(f["contribution"] for f in factors.values())
        assert contrib_sum == pytest.approx(candidate["total_score"], abs=1e-6)

    def test_assign_emits_ambulance_assigned_event(
        self, client, mock_bus, mock_hospital_repo, mock_emergency_repo
    ):
        g, tree = self._make_graph_and_tree(5)
        hospitals = [
            _hospital(1, "H", nearest_node_id=node_id(0, 2, 5),
                      total_icu_beds=20, available_icu_beds=5),
        ]
        case = make_case({"id": 1, "patient_condition": "STABLE"})
        mock_emergency_repo.get_by_id.return_value = case
        mock_emergency_repo.assign.return_value = case
        mock_hospital_repo.list_all.return_value = hospitals

        with patch("app.graph.loader.road_graph", g), \
             patch("app.graph.loader.kd_tree", tree):
            resp = client.post("/emergency/1/assign")

        assert resp.status_code == 200
        mock_bus.publish.assert_called_once()
        event = mock_bus.publish.call_args[0][0]
        assert event.type.value == "AmbulanceAssigned"
        assert event.payload["hospital_id"] == 1
        assert "travel_time_s" in event.payload

    def test_assign_no_candidates_returns_200_with_null(
        self, client, mock_hospital_repo, mock_emergency_repo
    ):
        """When all hospitals fail filtering, return 200 with assigned=null — not 500."""
        g, tree = self._make_graph_and_tree(5)
        # No ICU beds in any hospital → filtered for CRITICAL
        hospitals = [
            _hospital(1, "No ICU", nearest_node_id=node_id(0, 2, 5),
                      total_icu_beds=20, available_icu_beds=0),
        ]
        case = make_case({"id": 2, "patient_condition": "CRITICAL"})
        mock_emergency_repo.get_by_id.return_value = case
        mock_hospital_repo.list_all.return_value = hospitals

        with patch("app.graph.loader.road_graph", g), \
             patch("app.graph.loader.kd_tree", tree):
            resp = client.post("/emergency/2/assign")

        assert resp.status_code == 200
        data = resp.json()
        assert data["assigned_hospital_id"] is None
        assert data["status"] == "NO_CANDIDATES"
        assert data["reason"] is not None
        assert len(data["filtered_out"]) == 1

    def test_assign_emergency_not_found_returns_404(
        self, client, mock_emergency_repo
    ):
        mock_emergency_repo.get_by_id.return_value = None
        resp = client.post("/emergency/999/assign")
        assert resp.status_code == 404

    def test_assign_graph_not_ready_returns_503(self, client, mock_emergency_repo):
        case = make_case({"id": 1})
        mock_emergency_repo.get_by_id.return_value = case
        with patch("app.graph.loader.kd_tree", None):
            resp = client.post("/emergency/1/assign")
        assert resp.status_code == 503

    def test_stable_assign_picks_least_loaded_not_nearest(
        self, client, mock_hospital_repo, mock_emergency_repo
    ):
        """
        STABLE: a saturated nearby hospital should lose to a less-loaded farther one.
        Demonstrates load-balancing — the system does not simply pick the nearest.
        """
        g, tree = self._make_graph_and_tree(5)
        hospitals = [
            _hospital(1, "Near Saturated",
                      nearest_node_id=node_id(0, 1, 5),
                      total_beds=100, available_beds=2,
                      total_icu_beds=10, available_icu_beds=1,
                      current_load=98,
                      specializations=["general"]),
            _hospital(2, "Far Available",
                      nearest_node_id=node_id(0, 4, 5),
                      total_beds=200, available_beds=120,
                      total_icu_beds=40, available_icu_beds=30,
                      current_load=80,
                      specializations=["general"]),
        ]
        case = make_case({"id": 5, "patient_condition": "STABLE"})
        mock_emergency_repo.get_by_id.return_value = case
        mock_emergency_repo.assign.return_value = case
        mock_hospital_repo.list_all.return_value = hospitals

        with patch("app.graph.loader.road_graph", g), \
             patch("app.graph.loader.kd_tree", tree):
            resp = client.post("/emergency/5/assign")

        assert resp.status_code == 200
        data = resp.json()
        assert data["assigned_hospital_id"] == 2, (
            "Far Available should win for STABLE: much lower load "
            "and better bed availability outweigh the travel penalty"
        )
