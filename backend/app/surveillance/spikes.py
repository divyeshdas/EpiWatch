"""
Sliding-window z-score spike detection for outbreak time series.

Algorithm
---------
For each point i in an ordered (oldest -> newest) series, look at the
trailing window of the N points *before* i (points[i-N : i]) and compute
their mean and standard deviation.  Then:

    z = (value[i] - rolling_mean) / rolling_std

A large positive z means today's value is far above what the recent past
looked like -> a spike.

Why the window must be causal (trailing, not centered)
-------------------------------------------------------
A real-time detector only ever has data up to "now".  If the window included
points *after* i (a centered window), the detector would need to see the
future to flag the present -- impossible outside of backtesting, and it
would also smear a single spike's influence backwards onto earlier points
that were perfectly normal when they happened.  Using only points[i-N:i]
means: "is this new value unusual compared to everything we knew right
before it arrived?" -- exactly the question an operator monitoring a live
feed needs answered.

Severity tiers
--------------
Thresholds are config-driven (see app.config.Settings), not hardcoded here.
The caller passes a dict mapping each Severity to its minimum z-score.  The
highest tier whose threshold is met wins:

    z >= critical_threshold -> CRITICAL
    z >= high_threshold     -> HIGH
    z >= medium_threshold   -> MEDIUM
    z >= low_threshold      -> LOW
    otherwise               -> no detection (not anomalous)

Edge cases
----------
- Cold start: points 0..window-1 don't have a full trailing window yet, so
  no detection is emitted for them.  A series with <= window points produces
  no detections at all.
- Flat window (rolling_std == 0): every point in the window was identical,
  so the ordinary z formula divides by zero.  Two cases:
    * value[i] == rolling_mean too -> nothing changed; z = 0.0 (no spike).
    * value[i] != rolling_mean     -> the series just broke out of a
      perfectly flat baseline.  That is a real anomaly, but "infinite sigma"
      isn't a useful or JSON-safe number, so we clamp z to SENTINEL_Z
      (well above every default threshold) which always classifies as
      CRITICAL while staying a normal float.

Complexity
----------
O(n) over a series of n points.  The trailing sum and sum-of-squares of the
window are maintained incrementally: moving from point i to i+1 removes
points[i-window] and adds points[i] from both running totals in O(1), so the
mean/variance for each point is O(1) to derive.  The naive approach -- for
each point, re-summing its window from scratch -- is O(n * window); for a
bounded window this is the same asymptotic class, but the incremental form
avoids the repeated work entirely.
Space: O(n) for the output detections (worst case every point is anomalous);
O(1) auxiliary state for the rolling sums.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Stand-in for "infinite" z when the trailing window has zero variance but
# the current value differs from it.  Large enough to exceed any sane
# severity threshold, small enough to serialize safely as JSON.
SENTINEL_Z = 999.0


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Highest tier first -- the first threshold a z-score clears wins.
_TIER_ORDER = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW)


@dataclass
class SeriesPoint:
    """One observation in an ordered (oldest -> newest) time series."""
    date: str   # ISO 8601 date (YYYY-MM-DD)
    value: int


@dataclass
class SpikeDetection:
    """One anomalous point flagged by detect_spikes()."""
    date: str
    value: int
    rolling_mean: float
    rolling_std: float
    z_score: float
    severity: Severity


def _severity_for_z(z: float, thresholds: dict[Severity, float]) -> Severity | None:
    for tier in _TIER_ORDER:
        if z >= thresholds[tier]:
            return tier
    return None


def detect_spikes(
    points: list[SeriesPoint],
    window: int,
    thresholds: dict[Severity, float],
) -> list[SpikeDetection]:
    """
    Run the trailing-window z-score detector over an ordered series.

    Args:
        points:     series in chronological order (oldest first)
        window:     number of preceding points used as the baseline
        thresholds: Severity -> minimum z-score for that tier

    Returns:
        One SpikeDetection per point whose z-score clears the lowest
        configured threshold, in chronological order.
    """
    n = len(points)
    detections: list[SpikeDetection] = []

    # Cold start: the first `window` points have no full trailing window.
    if n <= window:
        return detections

    roll_sum = sum(p.value for p in points[:window])
    roll_sq = sum(p.value * p.value for p in points[:window])

    for i in range(window, n):
        mean = roll_sum / window
        # Clamp to 0: floating-point error can push this fractionally
        # negative when the window is genuinely flat.
        variance = max(0.0, roll_sq / window - mean * mean)
        std = variance ** 0.5

        current = points[i].value
        if std == 0.0:
            # Flat baseline. If the new value matches it too, nothing
            # happened (z = 0). Otherwise this is a break from a perfectly
            # flat series -- treat as the most severe possible anomaly
            # without dividing by zero.
            z = 0.0 if current == mean else SENTINEL_Z
        else:
            z = (current - mean) / std

        severity = _severity_for_z(z, thresholds)
        if severity is not None:
            detections.append(SpikeDetection(
                date=points[i].date,
                value=current,
                rolling_mean=round(mean, 3),
                rolling_std=round(std, 3),
                z_score=round(z, 3),
                severity=severity,
            ))

        # Slide the window forward by one point.
        outgoing = points[i - window].value
        roll_sum += current - outgoing
        roll_sq += current * current - outgoing * outgoing

    return detections
