"""
Dijkstra shortest-path over the in-memory RoadGraph.

─── Why travel_time_s is the default weight ─────────────────────────────────
An ambulance ETA (how long until it reaches the hospital) is the primary
optimisation target for emergency dispatch.  Travel time and road distance
diverge on real networks: a 2 km highway segment at 80 km/h beats a 1.5 km
side-street at 20 km/h.  The weight function is a parameter so callers can
switch to distance_m (e.g. for fuel cost) without touching this file.

─── How the algorithm works ─────────────────────────────────────────────────
Dijkstra maintains a best-known cost to reach every node, initialised to ∞.
It uses a min-heap as the frontier so the next node to settle is always the
one with the currently lowest tentative cost.

  1. Seed the heap with (cost=0, source).
  2. Pop (cost, node) — the globally cheapest unsettled entry.
  3. If cost > dist[node] this entry is stale (see lazy deletion) — skip.
  4. If node == target: path is found; reconstruct and return.
  5. For every outgoing edge (node → v, weight w):
       new_cost = cost + w
       if new_cost < dist[v]:
           dist[v] = new_cost
           prev[v] = (node, edge metrics)
           heap.push(new_cost, v)
  6. Repeat until heap is empty (target unreachable → return None).

─── Why greedy correctness holds ────────────────────────────────────────────
All edge weights are ≥ 0, so once a node is popped from the min-heap its
recorded cost cannot be improved by any future path (any alternative would
have to pass through nodes with equal or higher cost).  The first pop of a
node is therefore its settled, optimal cost.  Every subsequent pop of the
same node will have cost > dist[node] and is discarded.

─── Lazy deletion vs decrease-key ───────────────────────────────────────────
Classic Dijkstra uses decrease-key: when a better path to v is found, the
existing heap entry for v is updated in place.  This requires tracking each
node's heap index, complicating the heap.

Lazy deletion is simpler: push a new (better) entry and leave the old one.
When the old entry is eventually popped, cost > dist[node] and it is
discarded in O(1).  The heap may hold up to O(E) entries instead of O(V),
but for sparse road graphs (E ≈ 3–4 × V) the extra memory is negligible
and the asymptotic complexity is unchanged.

─── Complexity ──────────────────────────────────────────────────────────────
Time  O((V + E) log V)  — each of the E edge relaxations pushes one heap
                          entry; each heap operation costs O(log E) ≈ O(log V)
                          for sparse graphs (E = O(V)).
Space O(V)              — dist and prev each hold at most V entries; the heap
                          holds O(E) entries (= O(V) for sparse graphs).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.graph.heap import MinHeap
from app.graph.road_graph import Edge, RoadGraph


@dataclass
class PathResult:
    """Outcome of a successful path search (Dijkstra or A*)."""
    node_ids: list[int]          # ordered path: source → … → target
    total_distance_m: float      # sum of edge.distance_m along the path
    total_travel_time_s: float   # sum of edge.travel_time_s along the path
    nodes_expanded: int = 0      # non-stale pops from the frontier (search-effort metric)


def dijkstra(
    graph: RoadGraph,
    source: int,
    target: int,
    weight: Callable[[Edge], float] = lambda e: e.travel_time_s,
) -> PathResult | None:
    """
    Return the shortest PathResult from source to target, or None if unreachable.

    Both total_distance_m and total_travel_time_s are always populated in the
    result, regardless of which metric the weight function optimises.

    Args:
        graph:  The in-memory road graph.
        source: Start node ID (snapped from emergency coordinate).
        target: End node ID (hospital's nearest_node_id).
        weight: Edge cost function — defaults to travel_time_s.
                Must return non-negative floats for correctness.
    """
    if source == target:
        return PathResult(node_ids=[source], total_distance_m=0.0, total_travel_time_s=0.0)

    # dist[n] = best known cost (under the weight function) to reach n from source
    dist: dict[int, float] = {source: 0.0}

    # prev[n] = (predecessor_node, edge_distance_m, edge_travel_time_s)
    # Storing both metrics here avoids a second graph traversal during reconstruction.
    prev: dict[int, tuple[int, float, float]] = {}

    heap = MinHeap()
    heap.push(0.0, source)
    nodes_expanded = 0

    while heap:
        cost, node = heap.pop_min()

        # Lazy deletion: a shorter path to this node was found after this entry
        # was pushed.  The dist dict already reflects the better cost, so this
        # entry is stale — discard it in O(1) and continue.
        if cost > dist.get(node, float("inf")):
            continue

        nodes_expanded += 1

        if node == target:
            return _reconstruct(source, target, prev, nodes_expanded)

        for edge in graph.neighbors(node):
            new_cost = cost + weight(edge)
            if new_cost < dist.get(edge.target_id, float("inf")):
                dist[edge.target_id] = new_cost
                prev[edge.target_id] = (node, edge.distance_m, edge.travel_time_s)
                heap.push(new_cost, edge.target_id)

    return None  # target is unreachable from source


# ── internal ──────────────────────────────────────────────────────────────────

def _reconstruct(
    source: int,
    target: int,
    prev: dict[int, tuple[int, float, float]],
    nodes_expanded: int = 0,
) -> PathResult:
    """Walk the predecessor map from target back to source and reverse."""
    path: list[int] = []
    total_dist_m = 0.0
    total_tt_s = 0.0

    cur = target
    while cur != source:
        path.append(cur)
        predecessor, d_m, tt_s = prev[cur]
        total_dist_m += d_m
        total_tt_s += tt_s
        cur = predecessor
    path.append(source)
    path.reverse()

    return PathResult(
        node_ids=path,
        total_distance_m=round(total_dist_m, 1),
        total_travel_time_s=round(total_tt_s, 1),
        nodes_expanded=nodes_expanded,
    )
