import math

_R = 6_371_000.0  # Earth radius in metres


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two (lat, lon) points in metres.

    Accuracy: < 0.5 % for distances up to 20 000 km (sufficient for city-scale routing).

    Used in two places:
      - K-D tree: actual distance between query point and each candidate node.
      - A* heuristic (Phase A4): straight-line lower bound on road distance.
        The heuristic is admissible because road distance ≥ great-circle distance.

    Time: O(1).  Space: O(1).
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * _R * math.asin(math.sqrt(a))
