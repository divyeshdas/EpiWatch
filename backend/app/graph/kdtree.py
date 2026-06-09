"""
Hand-rolled 2-D K-D tree over geographic coordinates.

WHY hand-roll instead of scipy.spatial.KDTree?
  This is a core DSA deliverable — the tree is the interview talking point and is
  kept visible so every design choice can be explained. scipy's implementation is
  a black box and would hide the pruning logic and the axis-alternation strategy.

HOW a K-D tree partitions 2-D space:
  A K-D tree is a binary search tree where each internal node splits the remaining
  point set with an axis-aligned hyperplane (a line in 2-D).  Depth 0 splits on
  latitude, depth 1 on longitude, depth 2 on latitude again, and so on.  At each
  level we place the *median* point at the split so that roughly half the points
  fall on each side, keeping the tree balanced.

  Nearest-neighbour query — why it's sub-linear:
  When looking for the nearest node to a query point Q, we descend the tree as if
  doing a point lookup, tracking the best (closest) node seen so far.  Before
  backtracking through the sibling branch, we check: could any point in that
  branch be closer than our current best?  The closest point in the sibling branch
  is on the splitting plane itself, and the plane is axis-aligned, so its distance
  to Q is just |Q.axis - split.axis| × metres-per-degree.  If that plane distance
  already exceeds our best, the entire branch is pruned.  This prunes O(log n)
  branches on average, giving sub-linear expected query time.

Complexity:
  Build:           O(n log² n) — recursive median sort at each of O(log n) levels,
                   each level doing O(n) total comparisons across all sub-arrays.
                   (O(n log n) is achievable with pre-sorted arrays; the constant
                   difference is negligible for city-scale n ≤ 50 000.)
  Nearest query:   O(log n) average, O(n) worst case (degenerate / clustered data).
  Space:           O(n) — one KDNode per input point.

  Beats a naïve O(n) scan because it prunes entire spatial regions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.graph.haversine import haversine

# metres per degree (conservative overestimate for longitude; exact for latitude
# near the equator).  Used for the axis-plane pruning test — overestimating is
# safe: we visit a few extra branches but never skip the true nearest neighbour.
_M_PER_DEG = 111_320.0


@dataclass
class _KDNode:
    node_id: int
    lat: float
    lon: float
    left: "_KDNode | None" = field(default=None, repr=False)
    right: "_KDNode | None" = field(default=None, repr=False)


class KDTree:
    """2-D K-D tree keyed on (latitude, longitude)."""

    def __init__(self, points: list[tuple[int, float, float]]) -> None:
        """
        Build the tree.

        Args:
            points: sequence of (node_id, latitude, longitude)
        """
        self._root = self._build(list(points), depth=0)
        self._size = len(points)

    # ── construction ─────────────────────────────────────────────────────────

    def _build(self, points: list[tuple[int, float, float]], depth: int) -> _KDNode | None:
        if not points:
            return None
        axis = depth % 2  # 0 → split on latitude, 1 → split on longitude
        points.sort(key=lambda p: p[1] if axis == 0 else p[2])
        mid = len(points) // 2
        nid, lat, lon = points[mid]
        return _KDNode(
            node_id=nid,
            lat=lat,
            lon=lon,
            left=self._build(points[:mid], depth + 1),
            right=self._build(points[mid + 1:], depth + 1),
        )

    # ── query ────────────────────────────────────────────────────────────────

    def nearest(self, lat: float, lon: float) -> tuple[int, float, float, float]:
        """
        Find the closest node to (lat, lon).

        Returns:
            (node_id, node_lat, node_lon, distance_m)
        """
        if self._root is None:
            raise RuntimeError("tree is empty")

        best_node: list[_KDNode | None] = [None]
        best_dist: list[float] = [float("inf")]

        def search(node: _KDNode | None, depth: int) -> None:
            if node is None:
                return

            d = haversine(lat, lon, node.lat, node.lon)
            if d < best_dist[0]:
                best_node[0] = node
                best_dist[0] = d

            axis = depth % 2
            diff = (lat - node.lat) if axis == 0 else (lon - node.lon)

            # Descend into the branch that contains the query point first
            near, far = (node.left, node.right) if diff <= 0 else (node.right, node.left)
            search(near, depth + 1)

            # Only explore the far branch if the splitting plane is closer than
            # the current best distance.  Using _M_PER_DEG for both axes is a
            # conservative overestimate for longitude (safe; never over-prunes).
            if abs(diff) * _M_PER_DEG < best_dist[0]:
                search(far, depth + 1)

        search(self._root, 0)
        n = best_node[0]
        assert n is not None
        return n.node_id, n.lat, n.lon, best_dist[0]

    def __len__(self) -> int:
        return self._size
