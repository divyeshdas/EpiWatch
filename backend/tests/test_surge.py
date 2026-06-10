"""
Tests for B4 — surveillance-aware routing.

Coverage:
  app.scoring.surge
    - AlertGenerated -> handle_alert_generated -> surge store (event-driven,
      never a direct call from surveillance code)
    - other event types / unknown severities are ignored
    - surge decays/expires once its TTL passes without a refreshing alert
    - a hospital with no region (or an unrecognised region) has no surge

  app.scoring.scorer
    - a hospital in a surging region gets the surge penalty in its breakdown
      and ranks lower than an otherwise-identical hospital outside it
    - with no active surge, the surge factor contributes 0 and total_score
      matches the pre-B4 (five-factor) total exactly

  module boundary
    - app.scoring never imports app.surveillance, and vice versa
"""
from __future__ import annotations

import ast
import os
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.domain.events import Event, EventType
from app.graph.road_graph import RoadGraph
from app.infra.models import Hospital
from app.scoring import surge
from app.scoring.scorer import score_hospitals
from tests.graph_fixtures import make_grid, node_id


def _make_road_graph(n: int) -> RoadGraph:
    nodes, edges = make_grid(n)
    g = RoadGraph()
    for nid, lat, lon in nodes:
        g.add_node(nid, lat, lon)
    for src, tgt, dist_m, tt_s in edges:
        g.add_edge(src, tgt, dist_m, tt_s)
    return g


def _hospital(id: int, name: str, nearest_node_id: int | None, region: str | None = None) -> Hospital:
    return Hospital(
        id=id,
        name=name,
        latitude=19.0,
        longitude=72.85,
        total_beds=200,
        available_beds=80,
        total_icu_beds=40,
        available_icu_beds=16,
        emergency_capacity=50,
        current_load=120,
        specializations=["general"],
        region=region,
        updated_at=datetime.now(timezone.utc),
        nearest_node_id=nearest_node_id,
    )


# ── event-driven update ──────────────────────────────────────────────────────

class TestSurgeEventHandler:
    @pytest.mark.asyncio
    async def test_alert_generated_updates_surge_store_via_handler(self):
        assert surge.get_surge("Bandra").level == 0.0

        event = Event(
            type=EventType.ALERT_GENERATED,
            payload={
                "alert_id": 1,
                "type": "OUTBREAK_SPIKE",
                "severity": "HIGH",
                "message": "dengue in Bandra: cases 4.2σ above baseline",
                "region": "Bandra",
                "disease_name": "dengue",
                "event_date": "2026-06-10",
                "z_score": 4.2,
                "created_at": "2026-06-10T00:00:00+00:00",
            },
        )
        await surge.handle_alert_generated(event)

        info = surge.get_surge("Bandra")
        assert info.level == surge.SEVERITY_TO_LEVEL["HIGH"]
        assert info.severity == "HIGH"
        assert info.disease_name == "dengue"

    @pytest.mark.asyncio
    async def test_other_event_types_are_ignored(self):
        event = Event(
            type=EventType.HOSPITAL_UPDATED,
            payload={"region": "Bandra", "severity": "CRITICAL"},
        )
        await surge.handle_alert_generated(event)
        assert surge.get_surge("Bandra").level == 0.0

    @pytest.mark.asyncio
    async def test_unknown_severity_is_ignored(self):
        event = Event(
            type=EventType.ALERT_GENERATED,
            payload={"region": "Bandra", "severity": "WEIRD"},
        )
        await surge.handle_alert_generated(event)
        assert surge.get_surge("Bandra").level == 0.0


# ── ranking effect ────────────────────────────────────────────────────────────

class TestSurgePenaltyAffectsRanking:
    @pytest.mark.asyncio
    async def test_hospital_in_surging_region_ranks_lower(self):
        """
        Two otherwise-identical hospitals, one in Bandra and one in Andheri.
        A CRITICAL spike alert for Bandra (delivered through the event-bus
        handler, not a direct call) should give the Bandra hospital the full
        surge penalty and push it to rank 2.
        """
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        same_node = node_id(0, 2, 5)

        hospitals = [
            _hospital(1, "Bandra General", same_node, region="Bandra"),
            _hospital(2, "Andheri General", same_node, region="Andheri"),
        ]

        await surge.handle_alert_generated(Event(
            type=EventType.ALERT_GENERATED,
            payload={
                "region": "Bandra",
                "severity": "CRITICAL",
                "disease_name": "covid_19",
                "event_date": "2026-06-10",
            },
        ))

        result = score_hospitals(hospitals, src, "STABLE", g)
        by_name = {c.hospital.name: c for c in result.scored}
        bandra, andheri = by_name["Bandra General"], by_name["Andheri General"]

        # identical hospitals on the same node -> only the surge factor differs
        assert bandra.factors["surge"].contribution == pytest.approx(settings.surge_weight)
        assert andheri.factors["surge"].contribution == 0.0
        assert "CRITICAL" in bandra.factors["surge"].note

        assert bandra.total_score > andheri.total_score
        assert andheri.rank < bandra.rank

    def test_no_surge_scores_match_pre_b4(self):
        """With nothing in the surge store, the surge factor contributes 0
        and total_score equals the sum of the original five factors."""
        g = _make_road_graph(5)
        src = node_id(0, 0, 5)
        hospitals = [_hospital(1, "H", node_id(0, 2, 5), region="Bandra")]

        result = score_hospitals(hospitals, src, "STABLE", g)
        c = result.scored[0]

        assert c.factors["surge"].contribution == 0.0
        assert c.factors["surge"].penalty == 0.0

        pre_b4_total = sum(
            f.contribution for name, f in c.factors.items() if name != "surge"
        )
        assert c.total_score == pytest.approx(pre_b4_total)


# ── decay / TTL ────────────────────────────────────────────────────────────────

class TestSurgeDecay:
    def test_surge_expires_after_ttl(self):
        now = 1_000_000.0
        surge.record_surge("Bandra", "CRITICAL", disease_name="covid_19", now=now)

        # just before expiry: still active
        info = surge.get_surge("Bandra", now=now + settings.surge_ttl_seconds - 1)
        assert info.level == surge.SEVERITY_TO_LEVEL["CRITICAL"]

        # after expiry: faded back to 0
        info = surge.get_surge("Bandra", now=now + settings.surge_ttl_seconds + 1)
        assert info.level == 0.0
        assert info.severity is None

    def test_no_region_or_unrecognised_region_has_no_surge(self):
        assert surge.get_surge(None).level == 0.0
        assert surge.get_surge("NowhereLand").level == 0.0


# ── module boundary ─────────────────────────────────────────────────────────────

_APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")


def _imported_modules(*relative_dirs: str) -> dict[str, set[str]]:
    """Map each .py file to the set of top-level module names it imports
    (via `import x.y` or `from x.y import ...`), ignoring docstrings/comments."""
    imports: dict[str, set[str]] = {}
    for rel in relative_dirs:
        d = os.path.join(_APP_DIR, rel)
        for fname in os.listdir(d):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(d, fname)
            with open(path) as f:
                tree = ast.parse(f.read(), filename=path)
            names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names.add(node.module)
            imports[os.path.join(rel, fname)] = names
    return imports


class TestModuleBoundary:
    def test_scoring_does_not_import_surveillance(self):
        for path, names in _imported_modules("scoring").items():
            for n in names:
                assert not n.startswith("app.surveillance"), f"{path} imports {n}"

    def test_surveillance_does_not_import_scoring(self):
        for path, names in _imported_modules("surveillance").items():
            for n in names:
                assert not n.startswith("app.scoring"), f"{path} imports {n}"
