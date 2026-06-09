"""
Synthetic graph generator for tests and benchmarking.

Produces an N×N grid of nodes spaced 0.01° apart (≈ 1.1 km per step in Mumbai).
All edges are bidirectional with identical distance and travel time.

Advantages over using real OSM data in tests:
  - No network access required
  - Fully deterministic — same grid every run
  - Nearest-neighbour answers are analytically verifiable
  - Controllable size (n=5 → 25 nodes; n=10 → 100 nodes, etc.)
"""
from __future__ import annotations

# Grid spacing in degrees.  At latitude 19° N one degree ≈ 110 500 m.
_STEP = 0.01          # ≈ 1 105 m per step
_SPEED_KPH = 30.0

# Distance per step in metres (approximate — close enough for synthetic tests)
_DIST_M = _STEP * 110_500.0
_TIME_S = _DIST_M / (_SPEED_KPH * 1_000 / 3_600)

# Grid origin — roughly central Mumbai
_LAT0 = 19.00
_LON0 = 72.85


def node_id(i: int, j: int, n: int) -> int:
    """Row-major node ID for grid position (i, j) in an n×n grid.  1-indexed."""
    return i * n + j + 1


def make_grid(n: int) -> tuple[
    list[tuple[int, float, float]],          # (node_id, lat, lon)
    list[tuple[int, int, float, float]],     # (src_id, tgt_id, distance_m, travel_time_s)
]:
    """
    Build an n×n grid graph.

    Nodes are laid out on a regular lattice:
      node at (i, j)  →  lat = LAT0 + i * STEP,  lon = LON0 + j * STEP

    All horizontal and vertical edges are bidirectional.
    Diagonal neighbours are NOT connected (4-connected grid).
    """
    nodes: list[tuple[int, float, float]] = []
    edges: list[tuple[int, int, float, float]] = []

    for i in range(n):
        for j in range(n):
            nid = node_id(i, j, n)
            lat = _LAT0 + i * _STEP
            lon = _LON0 + j * _STEP
            nodes.append((nid, lat, lon))

            # right neighbour
            if j + 1 < n:
                tgt = node_id(i, j + 1, n)
                edges.append((nid, tgt, _DIST_M, _TIME_S))
                edges.append((tgt, nid, _DIST_M, _TIME_S))

            # down neighbour
            if i + 1 < n:
                tgt = node_id(i + 1, j, n)
                edges.append((nid, tgt, _DIST_M, _TIME_S))
                edges.append((tgt, nid, _DIST_M, _TIME_S))

    return nodes, edges
