"""
A* shortest-path over the in-memory RoadGraph.

─── Relationship to Dijkstra ────────────────────────────────────────────────
A* is Dijkstra with an extra term added to the heap priority:

  Dijkstra priority  =  g(n)           (cost so far)
  A* priority        =  f(n) = g(n) + h(n)    (cost so far + estimated cost to goal)

When h ≡ 0, A* and Dijkstra are identical.  A non-zero h biases the frontier
toward nodes that are both cheap to reach AND geographically close to the goal,
so the search expands far fewer nodes for the same optimal path.

─── Admissibility: why dividing Haversine by max-Haversine-speed keeps h correct ──
The edge weights are travel_time_s, so h must also be in seconds and must
never overestimate the true remaining travel time.

  h(n) = haversine(n, goal) / max_haversine_speed_m_per_s

where max_haversine_speed_m_per_s = max over all edges of
        haversine(edge_src, edge_tgt) / edge.travel_time_s.

Step-by-step proof that this never overestimates:

  1. For any path n → v1 → v2 → … → goal via edges e1 … ek, the Haversine
     triangle inequality gives:
       haversine(n, goal) ≤ Σ haversine(eᵢ_src, eᵢ_tgt)

  2. For each edge eᵢ:
       haversine(eᵢ) / max_haversine_speed ≤ haversine(eᵢ) / (haversine(eᵢ) / tt(eᵢ))
                                           = tt(eᵢ)
     (dividing by the maximum haversine-speed, which is ≥ this edge's, gives
      a time ≤ this edge's travel_time_s)

  3. Combining steps 1 and 2:
       h(n) = haversine(n, goal) / max_speed
            ≤ Σ haversine(eᵢ) / max_speed    (step 1)
            ≤ Σ tt(eᵢ)                        (step 2 per edge)
            = actual_travel_time

  So h(n) ≤ true remaining travel time → ADMISSIBLE.

  Why we use haversine-speed instead of distance_m-speed:
  The fixture (and real graph approximations) may store edge.distance_m as a
  value slightly different from the exact Haversine of the two endpoints.
  Computing max_speed from distance_m/tt could give a speed that, when applied
  to the haversine heuristic, overestimates for some node pairs.  Using
  haversine/tt for both the speed scan and the per-node h ensures the two are
  in the same metric and the inequality holds exactly.

─── Why A* expands fewer nodes than Dijkstra ─────────────────────────────────
Dijkstra expands nodes in order of g(n), radiating outward in all directions.
A* expands nodes in order of f(n) = g(n) + h(n).  Nodes far from the goal
direction have a large h, so their f is large even if g is small — they are
deprioritised and often never expanded at all.  The search forms an ellipse
between source and goal rather than a circle around the source.

─── Consistency and the closed-set approach ─────────────────────────────────
The heuristic is also consistent (monotone): for every edge n→n',
  h(n) ≤ w(n, n') + h(n')
because haversine satisfies the triangle inequality.

With a consistent heuristic, the first time a node is popped from the heap
its g-score is already optimal and it never needs to be re-opened.  We track
this with a `closed` set: once a node is settled, subsequent heap entries for
it are discarded in O(1).

This avoids computing `f - h(node)` for the staleness check, which is
numerically fragile when h is large (floating-point cancellation of large
nearly-equal values can make a valid entry look stale and cause the algorithm
to return None incorrectly).

─── Complexity ───────────────────────────────────────────────────────────────
Time  O((V + E) log V)  — same asymptotic class as Dijkstra; in practice the
                          constant is much smaller because far fewer nodes are
                          expanded when h is informative.
Space O(V)              — g_dist, prev, closed, and heap each O(V) entries.
"""
from __future__ import annotations

from typing import Callable

from app.graph.dijkstra import PathResult, _reconstruct
from app.graph.haversine import haversine
from app.graph.heap import MinHeap
from app.graph.road_graph import Edge, RoadGraph


def astar(
    graph: RoadGraph,
    source: int,
    target: int,
    heuristic: Callable[[int], float],
    weight: Callable[[Edge], float] = lambda e: e.travel_time_s,
) -> PathResult | None:
    """
    Return the shortest PathResult from source to target using A*, or None if
    unreachable.

    heuristic(node_id) must be admissible (never overestimates true remaining
    cost).  Use make_heuristic() to obtain a correctly scaled function for
    travel-time routing.

    Returns the same PathResult shape as dijkstra() so results are directly
    comparable (same optimal cost, different nodes_expanded).
    """
    if source == target:
        return PathResult(node_ids=[source], total_distance_m=0.0, total_travel_time_s=0.0)

    # g_dist[n] = best known g-score (cost-so-far from source) to reach n
    g_dist: dict[int, float] = {source: 0.0}

    # prev[n] = (predecessor, edge_distance_m, edge_travel_time_s)
    prev: dict[int, tuple[int, float, float]] = {}

    # closed: nodes whose optimal g-score is confirmed.  With a consistent
    # heuristic, a settled node never needs to be reopened, so we can skip
    # any heap entry for a node already in closed.
    closed: set[int] = set()

    heap = MinHeap()
    heap.push(heuristic(source), source)   # f = g(source) + h(source) = 0 + h
    nodes_expanded = 0

    while heap:
        _, node = heap.pop_min()

        if node in closed:
            continue   # stale entry — this node was settled by a better path
        closed.add(node)
        nodes_expanded += 1

        if node == target:
            return _reconstruct(source, target, prev, nodes_expanded)

        g_node = g_dist[node]
        for edge in graph.neighbors(node):
            if edge.target_id in closed:
                continue   # neighbour already settled; cannot improve it
            new_g = g_node + weight(edge)
            if new_g < g_dist.get(edge.target_id, float("inf")):
                g_dist[edge.target_id] = new_g
                prev[edge.target_id] = (node, edge.distance_m, edge.travel_time_s)
                heap.push(new_g + heuristic(edge.target_id), edge.target_id)

    return None  # target is unreachable from source


# ── heuristic factory ─────────────────────────────────────────────────────────

def make_heuristic(
    graph: RoadGraph,
    goal: int,
) -> Callable[[int], float]:
    """
    Build the admissible travel-time heuristic for the given goal node.

    h(n) = haversine(n, goal) / max_haversine_speed_m_per_s

    max_haversine_speed_m_per_s is derived from actual edge data so the
    heuristic is admissible for this specific graph instance.  See the module
    docstring for the full proof.

    Falls back to a zero heuristic (Dijkstra behaviour) if the graph has no
    edges or the goal node has no coordinates.

    Time: O(V + E) to compute max speed; O(1) per h(n) call thereafter.
    """
    goal_coords = graph.get_coords(goal)
    if goal_coords is None:
        return lambda _: 0.0

    goal_lat, goal_lon = goal_coords
    max_speed = _max_haversine_speed_m_per_s(graph)

    def h(node: int) -> float:
        coords = graph.get_coords(node)
        if coords is None:
            return 0.0
        return haversine(coords[0], coords[1], goal_lat, goal_lon) / max_speed

    return h


def _max_haversine_speed_m_per_s(graph: RoadGraph) -> float:
    """
    Scan all edges and return max(haversine(src, tgt) / travel_time_s).

    Using haversine distances here — not edge.distance_m — ensures the heuristic
    and the speed scale use the same metric.  See admissibility proof in module
    docstring.

    Falls back to 1.0 m/s if the graph has no edges (ultra-conservative).
    Time: O(V + E).
    """
    max_speed = 1.0
    for nid, src_lat, src_lon in graph.all_node_tuples():
        for edge in graph.neighbors(nid):
            if edge.travel_time_s <= 0:
                continue
            tgt = graph.get_coords(edge.target_id)
            if tgt is None:
                continue
            hav = haversine(src_lat, src_lon, tgt[0], tgt[1])
            speed = hav / edge.travel_time_s
            if speed > max_speed:
                max_speed = speed
    return max_speed
