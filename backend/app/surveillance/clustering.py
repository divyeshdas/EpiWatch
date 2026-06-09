"""
DBSCAN clustering for outbreak hotspot detection.

Algorithm choice: DBSCAN over Union-Find.
----------------------------------------------
Union-Find would link any two reports within ε of each other, treating every
nearby pair as a cluster.  Two isolated reports 1.5 km apart would form a
"hotspot" even though neither location is dense.  Epidemiologically that is
wrong: a hotspot requires *density* — many co-located cases — not just proximity.

DBSCAN encodes this with the min_pts threshold: a report is a "core point"
only if ≥ min_pts other reports fall within ε.  Reports that cannot reach
min_pts neighbours are labelled noise and excluded from hotspots.  That is
exactly the right model: one isolated field report is not a hotspot; fifteen
reports from the same slum block are.

Extending Union-Find to density awareness would mean re-implementing DBSCAN's
core-point concept from scratch, so DBSCAN is the cleaner choice.

Spatial index: K-D tree with radius query.
-------------------------------------------
DBSCAN's dominant cost is the ε-neighbourhood query: for every point, find
all points within distance ε.  A naïve scan checks every pair — O(n²).
A K-D tree stores points in a binary search tree partitioned by alternating
spatial axes (latitude at even depth, longitude at odd depth).  A radius
query descends the tree and prunes entire subtrees whenever the axis-aligned
distance from the query point to the splitting plane already exceeds ε.  This
gives O(log n + k) per query where k is the result size, and O(n log n) total.

Epidemiological meaning of parameters:
  eps_km    The "catchment radius."  Two reports within eps_km are co-located.
            2 km is appropriate for intra-city outbreaks: wider than a dense
            slum, narrower than a city ward boundary.
  min_pts   Minimum co-located reports to form a core point.  3 means an area
            needs at least 3 independent field reports before the system treats
            it as an active hotspot rather than noise.

Complexity:
  _SpatialIndex build:    O(n log² n)  (median sort at each of log n levels)
  DBSCAN with index:      O(n log n)   average; O(n²) worst (fully dense data)
  Brute-force reference:  O(n²)        used only in tests for correctness check
  Space:                  O(n)         tree + label array
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from app.graph.haversine import haversine

_M_PER_DEG = 111_320.0   # metres per degree — same constant as KDTree (safe overestimate)

NOISE: int = -1
UNVISITED: int = -2


# ── input / output types ──────────────────────────────────────────────────────

@dataclass
class ClusterPoint:
    """One disease report projected to a clustering point."""
    idx: int          # position in the input list
    report_id: int    # original DB primary key
    lat: float
    lon: float
    case_count: int


@dataclass
class ClusterResult:
    """Summary of one DBSCAN cluster or one noise point (cluster_id == -1)."""
    cluster_id: int
    member_ids: list[int]       # DB report ids
    centroid_lat: float
    centroid_lon: float
    total_cases: int
    report_count: int
    radius_km: float            # max haversine from centroid to any member, in km


# ── spatial index with radius query ──────────────────────────────────────────

@dataclass
class _Node:
    idx: int
    lat: float
    lon: float
    left: Optional["_Node"] = field(default=None, repr=False)
    right: Optional["_Node"] = field(default=None, repr=False)


class _SpatialIndex:
    """
    2-D K-D tree over (lat, lon) with O(log n + k) radius query.

    Adapted from app/graph/kdtree.py; adds range_within() which DBSCAN
    requires.  The build and pruning logic are identical to the original.
    """

    def __init__(self, points: list[ClusterPoint]) -> None:
        self._pts = points
        self._root = self._build(list(range(len(points))), depth=0)

    def _build(self, indices: list[int], depth: int) -> _Node | None:
        if not indices:
            return None
        axis = depth % 2
        indices.sort(key=lambda i: self._pts[i].lat if axis == 0 else self._pts[i].lon)
        mid = len(indices) // 2
        i = indices[mid]
        p = self._pts[i]
        return _Node(
            idx=i,
            lat=p.lat,
            lon=p.lon,
            left=self._build(indices[:mid], depth + 1),
            right=self._build(indices[mid + 1:], depth + 1),
        )

    def range_within(self, lat: float, lon: float, radius_m: float) -> list[int]:
        """
        Return the indices of all points within radius_m metres of (lat, lon).

        Pruning: before recursing into a subtree, compute the minimum possible
        distance from the query point to any point in that subtree — which is
        the perpendicular distance from the query point to the splitting plane.
        If that plane distance already exceeds radius_m, the entire subtree can
        contain no results and is skipped.

        Time: O(log n + k) average, O(n) worst case (all points in range).
        """
        result: list[int] = []
        self._search(self._root, lat, lon, radius_m, depth=0, out=result)
        return result

    def _search(
        self,
        node: _Node | None,
        lat: float,
        lon: float,
        radius_m: float,
        depth: int,
        out: list[int],
    ) -> None:
        if node is None:
            return
        if haversine(lat, lon, node.lat, node.lon) <= radius_m:
            out.append(node.idx)
        axis = depth % 2
        diff = (lat - node.lat) if axis == 0 else (lon - node.lon)
        near, far = (node.left, node.right) if diff <= 0 else (node.right, node.left)
        self._search(near, lat, lon, radius_m, depth + 1, out)
        # Prune far subtree: the closest point in it is on the splitting plane.
        if abs(diff) * _M_PER_DEG <= radius_m:
            self._search(far, lat, lon, radius_m, depth + 1, out)


# ── DBSCAN ────────────────────────────────────────────────────────────────────

def dbscan(
    points: list[ClusterPoint],
    eps_km: float,
    min_pts: int,
) -> list[ClusterResult]:
    """
    Density-Based Spatial Clustering of Applications with Noise.

    Args:
        points:   geolocated disease reports
        eps_km:   neighbourhood radius in kilometres
        min_pts:  minimum neighbours (including self) for a core point

    Returns:
        ClusterResult list: real clusters first (sorted total_cases desc),
        then one ClusterResult per noise point (cluster_id == -1).
    """
    if not points:
        return []

    n = len(points)
    eps_m = eps_km * 1_000.0
    index = _SpatialIndex(points)
    labels: list[int] = [UNVISITED] * n
    cluster_id = 0

    for i in range(n):
        if labels[i] != UNVISITED:
            continue

        neighbours = index.range_within(points[i].lat, points[i].lon, eps_m)
        if len(neighbours) < min_pts:
            labels[i] = NOISE
            continue

        # Core point: start a new cluster and expand it.
        labels[i] = cluster_id
        seed_set: list[int] = [j for j in neighbours if j != i]

        while seed_set:
            j = seed_set.pop()
            # Border point: reachable from a core, but may not be dense itself.
            if labels[j] == NOISE:
                labels[j] = cluster_id
            if labels[j] != UNVISITED:
                continue
            labels[j] = cluster_id
            j_nbrs = index.range_within(points[j].lat, points[j].lon, eps_m)
            if len(j_nbrs) >= min_pts:
                # j is also a core point; add its unvisited/noise neighbours.
                seed_set.extend(
                    k for k in j_nbrs
                    if labels[k] == UNVISITED or labels[k] == NOISE
                )

        cluster_id += 1

    return _aggregate(points, labels)


def _aggregate(points: list[ClusterPoint], labels: list[int]) -> list[ClusterResult]:
    # Real clusters: group all members that share the same cluster_id.
    cluster_groups: dict[int, list[int]] = defaultdict(list)
    noise_indices: list[int] = []

    for i, cid in enumerate(labels):
        if cid == NOISE:
            noise_indices.append(i)
        else:
            cluster_groups[cid].append(i)

    def _summarise(cid: int, member_indices: list[int]) -> ClusterResult:
        pts = [points[i] for i in member_indices]
        total = sum(p.case_count for p in pts)
        c_lat = sum(p.lat for p in pts) / len(pts)
        c_lon = sum(p.lon for p in pts) / len(pts)
        radius_km = max(
            haversine(c_lat, c_lon, p.lat, p.lon) for p in pts
        ) / 1_000.0
        return ClusterResult(
            cluster_id=cid,
            member_ids=[p.report_id for p in pts],
            centroid_lat=round(c_lat, 6),
            centroid_lon=round(c_lon, 6),
            total_cases=total,
            report_count=len(pts),
            radius_km=round(radius_km, 3),
        )

    clusters = sorted(
        (_summarise(cid, members) for cid, members in cluster_groups.items()),
        key=lambda r: r.total_cases,
        reverse=True,
    )
    # Each noise point is its own entry — they share cluster_id -1 but are
    # geographically unrelated and must be rendered individually on the map.
    noise = [_summarise(NOISE, [i]) for i in noise_indices]
    return clusters + noise


# ── brute-force reference (tests only) ───────────────────────────────────────

def _dbscan_brute_labels(
    points: list[ClusterPoint],
    eps_km: float,
    min_pts: int,
) -> list[int]:
    """
    O(n²) DBSCAN reference implementation.  Used in tests to verify that the
    K-D tree path produces identical cluster assignments.  Not used in production.
    """
    n = len(points)
    eps_m = eps_km * 1_000.0
    labels: list[int] = [UNVISITED] * n

    def nbrs(i: int) -> list[int]:
        return [
            j for j in range(n)
            if haversine(points[i].lat, points[i].lon, points[j].lat, points[j].lon) <= eps_m
        ]

    cluster_id = 0
    for i in range(n):
        if labels[i] != UNVISITED:
            continue
        nn = nbrs(i)
        if len(nn) < min_pts:
            labels[i] = NOISE
            continue
        labels[i] = cluster_id
        seed: list[int] = [j for j in nn if j != i]
        while seed:
            j = seed.pop()
            if labels[j] == NOISE:
                labels[j] = cluster_id
            if labels[j] != UNVISITED:
                continue
            labels[j] = cluster_id
            jn = nbrs(j)
            if len(jn) >= min_pts:
                seed.extend(
                    k for k in jn
                    if labels[k] == UNVISITED or labels[k] == NOISE
                )
        cluster_id += 1

    return labels
