"""
Dijkstra vs A* benchmark — nodes expanded and wall-clock time.

Usage:
  docker compose exec backend python -m app.graph.benchmark
  (or locally: python -m app.graph.benchmark from backend/)

Requires the graph to be populated (run ingest + snap first).

For each of four representative routes the benchmark runs both algorithms and
reports:
  - nodes_expanded: how many non-stale nodes were popped from the frontier
  - wall-clock time in milliseconds
  - whether the two algorithms agree on the optimal path cost

Expected qualitative result:
  A* expands significantly fewer nodes than Dijkstra for the same optimal cost.
  The Haversine heuristic guides the A* frontier toward the goal so it avoids
  exploring large portions of the graph that Dijkstra visits unconditionally.
  On a 2 500-node Mumbai grid, expect A* to expand 30–60 % of the nodes
  Dijkstra expands, depending on the straightness of the route.
"""
import asyncio
import logging
import time

# Silence startup noise so only the benchmark table is printed.
logging.disable(logging.CRITICAL)


async def _load_graph() -> None:
    from app.graph.loader import load_graph
    from app.infra.database import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        await load_graph(db)


def _run() -> None:
    asyncio.run(_load_graph())

    import app.graph.loader as _loader
    from app.graph.astar import astar, make_heuristic
    from app.graph.dijkstra import dijkstra

    g = _loader.road_graph
    all_nodes = g.all_node_tuples()   # [(id, lat, lon), …] in insertion order
    n = len(all_nodes)

    if n < 10:
        print("Graph not loaded. Run `python -m app.graph.ingest` first.")
        return

    pairs = [
        ("short",    all_nodes[0][0],      all_nodes[n // 8][0]),
        ("medium",   all_nodes[0][0],      all_nodes[n // 2][0]),
        ("long",     all_nodes[0][0],      all_nodes[-1][0]),
        ("diagonal", all_nodes[n // 4][0], all_nodes[3 * n // 4][0]),
    ]

    col = "{:<10} {:>14} {:>10} {:>8} {:>11} {:>9} {:>7}"
    header = col.format(
        "Route", "Dijk nodes", "A* nodes", "Ratio",
        "Dijk ms", "A* ms", "Match",
    )
    print()
    print(header)
    print("-" * len(header))

    for label, src, tgt in pairs:
        # ── Dijkstra ──────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        d = dijkstra(g, src, tgt)
        d_ms = (time.perf_counter() - t0) * 1_000

        # ── A* ────────────────────────────────────────────────────────────────
        h = make_heuristic(g, tgt)
        t0 = time.perf_counter()
        a = astar(g, src, tgt, h)
        a_ms = (time.perf_counter() - t0) * 1_000

        if d is None or a is None:
            print(f"{label:<10}  no path found")
            continue

        match = abs(d.total_travel_time_s - a.total_travel_time_s) < 0.5
        ratio = d.nodes_expanded / max(a.nodes_expanded, 1)

        print(col.format(
            label,
            d.nodes_expanded,
            a.nodes_expanded,
            f"{ratio:.2f}×",
            f"{d_ms:.1f}",
            f"{a_ms:.1f}",
            "✓" if match else "✗ MISMATCH",
        ))

    print()
    print("nodes_expanded = non-stale pops from the min-heap frontier")
    print("Ratio > 1 means A* did less work for the same optimal cost.")
    print()


if __name__ == "__main__":
    _run()
