"""
Latency benchmark — route computation, hotspot clustering, and hospital
assignment scoring.

Usage:
  docker compose exec backend python -m app.perf_bench
  (or locally, from backend/: python -m app.perf_bench)

Requires the graph (ingest + snap) and surveillance/hospital/emergency seed
data to already be loaded.

Methodology
-----------
Each operation runs N times (default 100) on a fixed, representative input.
A handful of warm-up runs are executed first and discarded. Per-run
wall-clock time is measured with time.perf_counter() and reported in
milliseconds as mean, median, p95, and min/max.

These are single-process, local, unloaded measurements taken on one machine —
they describe per-call latency of the algorithmic core, NOT throughput,
concurrency, or load behaviour. What is included/excluded per operation:

  - Route (A* / Dijkstra): pathfinding over the in-memory road graph only.
    Excludes the K-D tree "snap" lookup, HTTP handling, and DB access.
  - DBSCAN clustering: the K-D tree build + DBSCAN pass over the geolocated
    disease reports already loaded into memory — the same computation
    /surveillance/hotspots performs. Excludes the DB fetch.
  - Hospital assignment: the full filter -> route (A* to every surviving
    candidate) -> normalize -> weight -> rank pipeline (score_hospitals) for
    one representative emergency against the seeded hospital set. Excludes
    the DB fetch, the assignment write, and the event-bus publish.
"""
import asyncio
import logging
import statistics
import time

# Silence startup noise so only the benchmark table and notes are printed.
logging.disable(logging.CRITICAL)

N_RUNS = 100
WARMUP_RUNS = 5


def _percentile_95(samples_ms: list[float]) -> float:
    if len(samples_ms) < 2:
        return samples_ms[0]
    return statistics.quantiles(samples_ms, n=100, method="inclusive")[94]


def _time_calls(fn, n: int = N_RUNS, warmup: int = WARMUP_RUNS) -> list[float]:
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1_000)
    return samples


def _row(label: str, input_size: str, samples_ms: list[float]) -> dict:
    return {
        "label": label,
        "n": len(samples_ms),
        "input_size": input_size,
        "mean": statistics.mean(samples_ms),
        "median": statistics.median(samples_ms),
        "p95": _percentile_95(samples_ms),
        "min": min(samples_ms),
        "max": max(samples_ms),
    }


async def _load_context():
    """Load the road graph and fetch hospitals / reports / emergencies once."""
    from app.graph.loader import load_graph
    from app.infra.database import get_session_factory
    from app.repositories.emergency import EmergencyCaseRepository
    from app.repositories.hospital import HospitalRepository
    from app.repositories.surveillance import SurveillanceRepository

    factory = get_session_factory()
    async with factory() as db:
        await load_graph(db)
        hospitals = await HospitalRepository(db).list_all()
        reports = await SurveillanceRepository(db).reports_for_clustering()
        emergencies = await EmergencyCaseRepository(db).list_all()

    import app.graph.loader as _loader
    return _loader.road_graph, _loader.kd_tree, hospitals, reports, emergencies


def _run() -> None:
    road_graph, kd_tree, hospitals, reports, emergencies = asyncio.run(_load_context())

    from app.config import settings
    from app.graph.astar import astar, make_heuristic
    from app.graph.dijkstra import dijkstra
    from app.scoring.scorer import score_hospitals
    from app.surveillance.clustering import ClusterPoint, dbscan

    all_nodes = road_graph.all_node_tuples()
    n_nodes = len(all_nodes)
    if n_nodes < 10:
        print("Graph not loaded. Run `python -m app.graph.ingest` and "
              "`python -m app.graph.snap` first.")
        return
    if not hospitals:
        print("No hospitals seeded. Run `python -m app.seed` first.")
        return
    if not emergencies:
        print("No emergencies seeded. Run `python -m app.seed` first.")
        return
    if kd_tree is None:
        print("K-D tree not built (graph not snapped). Run "
              "`python -m app.graph.snap` first.")
        return

    rows = []

    # ── 1. Route computation latency (A* and Dijkstra) ──────────────────────
    # Same four representative (source, target) pairs as app.graph.benchmark.
    pairs = [
        (all_nodes[0][0], all_nodes[n_nodes // 8][0]),
        (all_nodes[0][0], all_nodes[n_nodes // 2][0]),
        (all_nodes[0][0], all_nodes[-1][0]),
        (all_nodes[n_nodes // 4][0], all_nodes[3 * n_nodes // 4][0]),
    ]

    dijkstra_samples: list[float] = []
    astar_samples: list[float] = []
    per_pair = N_RUNS // len(pairs)
    for src, tgt in pairs:
        h = make_heuristic(road_graph, tgt)
        for _ in range(WARMUP_RUNS):
            dijkstra(road_graph, src, tgt)
            astar(road_graph, src, tgt, h)
        for _ in range(per_pair):
            t0 = time.perf_counter()
            dijkstra(road_graph, src, tgt)
            dijkstra_samples.append((time.perf_counter() - t0) * 1_000)
        for _ in range(per_pair):
            t0 = time.perf_counter()
            astar(road_graph, src, tgt, h)
            astar_samples.append((time.perf_counter() - t0) * 1_000)

    route_input = f"{n_nodes} nodes, 4 pairs x {per_pair}"
    rows.append(_row("Route — Dijkstra", route_input, dijkstra_samples))
    rows.append(_row("Route — A*", route_input, astar_samples))

    # ── 2. DBSCAN hotspot clustering latency ─────────────────────────────────
    points = [
        ClusterPoint(
            idx=i,
            report_id=r.id,
            lat=float(r.latitude),
            lon=float(r.longitude),
            case_count=r.case_count,
        )
        for i, r in enumerate(reports)
    ]
    cluster_samples = _time_calls(
        lambda: dbscan(points, eps_km=settings.hotspot_eps_km, min_pts=settings.hotspot_min_pts)
    )
    rows.append(_row("DBSCAN clustering", f"{len(points)} reports", cluster_samples))

    # ── 3. Hospital assignment scoring latency ───────────────────────────────
    # Most recently created emergency that was successfully assigned, so the
    # pipeline produces a non-empty ranked candidate list.
    case = next((e for e in emergencies if e.assigned_hospital_id is not None), emergencies[0])
    src_node_id, _, _, _ = kd_tree.nearest(case.latitude, case.longitude)
    assign_samples = _time_calls(
        lambda: score_hospitals(
            hospitals=hospitals,
            src_node_id=src_node_id,
            condition=case.patient_condition,
            road_graph=road_graph,
        )
    )
    rows.append(_row(
        f"Hospital assignment ({case.patient_condition})",
        f"{len(hospitals)} hospitals",
        assign_samples,
    ))

    _print_table(rows)
    _print_notes(n_nodes, len(points), len(hospitals), case, settings)


def _print_table(rows: list[dict]) -> None:
    col = "{:<28} {:>5} {:>22} {:>9} {:>10} {:>9} {:>9} {:>9}"
    header = col.format(
        "Operation", "N", "Input size", "Mean ms", "Median ms", "P95 ms", "Min ms", "Max ms",
    )
    print()
    print(header)
    print("-" * len(header))
    for r in rows:
        print(col.format(
            r["label"], r["n"], r["input_size"],
            f"{r['mean']:.3f}", f"{r['median']:.3f}", f"{r['p95']:.3f}",
            f"{r['min']:.3f}", f"{r['max']:.3f}",
        ))
    print()


def _print_notes(n_nodes: int, n_reports: int, n_hospitals: int, case, settings) -> None:
    print(f"N = {N_RUNS} per operation ({WARMUP_RUNS} warm-up runs discarded, not counted).")
    print("Single process, single machine, no concurrent load — these are latency")
    print("numbers, not throughput or stress-test numbers.")
    print()
    print(f"- Route: A*/Dijkstra pathfinding over the {n_nodes}-node road graph, cycled")
    print("  across 4 representative (source, target) pairs. Excludes the K-D tree")
    print("  snap lookup, HTTP handling, and database access.")
    print(f"- Clustering: DBSCAN with a K-D tree index over {n_reports} geolocated disease")
    print(f"  reports (eps_km={settings.hotspot_eps_km}, min_pts={settings.hotspot_min_pts}) — "
          "the same computation /surveillance/hotspots")
    print("  performs. Excludes the database fetch.")
    print(f"- Assignment: full filter -> route (A* to each of the {n_hospitals} candidate")
    print(f"  hospitals) -> normalize -> weight -> rank pipeline for emergency #{case.id} "
          f"(condition={case.patient_condition}).")
    print("  Excludes the database fetch, the assignment write, and the event-bus publish.")
    print()


if __name__ == "__main__":
    _run()
