"""
In-memory directed weighted road graph (adjacency list).

Space complexity:  O(V + E)
  - _nodes dict:  one entry per node  →  O(V)
  - _adj dict:    one Edge object per directed edge  →  O(E)
  For a Mumbai metro graph with V ≈ 15 000 nodes and E ≈ 40 000 edges this is
  roughly 4–8 MB of Python objects — well within a single-process memory budget.

The DB is the source of truth; this structure is rebuilt from the DB on every
startup (see loader.py).  Algorithms (Dijkstra, A*) operate entirely on this
in-memory representation — they never touch the DB during pathfinding.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.infra.models import GraphEdge, GraphNode


@dataclass(frozen=True, slots=True)
class Edge:
    """A single directed road segment."""
    target_id: int
    distance_m: float
    travel_time_s: float


class RoadGraph:
    """Directed adjacency-list graph over road-network nodes."""

    def __init__(self) -> None:
        self._nodes: dict[int, tuple[float, float]] = {}       # id → (lat, lon)
        self._adj: dict[int, list[Edge]] = defaultdict(list)   # id → [Edge, ...]

    # ── mutation ─────────────────────────────────────────────────────────────

    def add_node(self, node_id: int, lat: float, lon: float) -> None:
        self._nodes[node_id] = (lat, lon)

    def add_edge(
        self,
        source_id: int,
        target_id: int,
        distance_m: float,
        travel_time_s: float,
    ) -> None:
        self._adj[source_id].append(Edge(target_id, distance_m, travel_time_s))

    # ── queries ───────────────────────────────────────────────────────────────

    def neighbors(self, node_id: int) -> list[Edge]:
        return self._adj[node_id]

    def get_coords(self, node_id: int) -> tuple[float, float] | None:
        """Returns (lat, lon) or None if the node does not exist."""
        return self._nodes.get(node_id)

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return sum(len(edges) for edges in self._adj.values())

    def all_node_tuples(self) -> list[tuple[int, float, float]]:
        """Returns [(id, lat, lon), ...] — the input format for KDTree."""
        return [(nid, lat, lon) for nid, (lat, lon) in self._nodes.items()]

    def bounding_box(self) -> dict[str, float]:
        if not self._nodes:
            return {}
        lats = [c[0] for c in self._nodes.values()]
        lons = [c[1] for c in self._nodes.values()]
        return {
            "min_lat": min(lats),
            "max_lat": max(lats),
            "min_lon": min(lons),
            "max_lon": max(lons),
        }

    # ── factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_db(
        cls,
        nodes: "list[GraphNode]",
        edges: "list[GraphEdge]",
    ) -> "RoadGraph":
        graph = cls()
        for n in nodes:
            graph.add_node(n.id, n.latitude, n.longitude)
        for e in edges:
            graph.add_edge(e.source_node_id, e.target_node_id, e.distance_m, e.travel_time_s)
        return graph
