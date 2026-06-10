"""
Hospital scoring engine for the EpiWatch triage system.

─── The filter → normalize → weight → rank pipeline ─────────────────────────

1. FILTER
   Eliminate hospitals that physically cannot help before scoring begins.
   Filtering first saves routing computation and — more importantly — ensures
   correctness: a hospital with 0 ICU beds must never win for a CRITICAL patient
   even if it "scores well" on all other factors.

   Filter criteria:
     • Has been snapped to the road graph (nearest_node_id is not None)
     • A* returns a path (reachable from the emergency location)
     • available_beds > 0 (can actually admit the patient)
     • CRITICAL or CARDIAC patients additionally require available_icu_beds > 0

2. NORMALIZE
   The raw factor values live in incomparable units: travel time is in seconds,
   bed availability is a ratio, load factor is a ratio.  Directly summing
   "1 200 seconds + 0.75 ratio" is numerically meaningless.

   Normalization maps each factor to a penalty ∈ [0, 1]:
     travel_time      min-max across candidates: (tt − min_tt) / (max_tt − min_tt)
                      → fastest candidate gets 0, slowest gets 1
     bed_availability 1 − available_beds / total_beds  (already in [0,1])
     icu_availability 1 − available_icu / total_icu    (already in [0,1])
     load_factor      current_load / total_beds        (already in [0,1])
     specialization   binary: 0 if condition's specialty matches, 1 otherwise
     surge            current surge level for the hospital's region, looked
                       up from app.scoring.surge (already in [0,1], 0 if no
                       active surge — see below)

   Edge cases handled:
     • Single candidate: travel penalty = 0 (nothing to compare against)
     • All candidates tied on travel: travel penalty = 0 for all
     • total_beds = 0: bed and load penalties = 1.0 (safest assumption)
     • total_icu_beds = 0: icu penalty = 1.0 (would already be filtered for
       CRITICAL/CARDIAC, but handles STABLE/SERIOUS hospitals gracefully)

3. WEIGHT
   Each of the five clinical penalties is multiplied by the condition-keyed
   weight from weights.py; those five weights sum to 1.0 (enforced by
   ScoringWeights.__post_init__).  The surge penalty is then added on top,
   multiplied by settings.surge_weight:

     total_score = Σ (weight_i × penalty_i)  +  surge_weight × surge_level

   With no active surge, surge_level == 0 for every hospital, so total_score
   is identical to pre-B4 behaviour and stays in [0, 1].  With an active
   surge, a hospital in the surging region gets an extra penalty up to
   surge_weight, on top of its clinical score (total_score ∈ [0, 1 + surge_weight]).
   This is deliberate: the surge penalty is an operational layer over the
   clinical weighting, not part of it — surveillance-aware routing shouldn't
   change *how* the system reasons about a patient's clinical needs, only
   nudge it away from a region about to be saturated.

   Lower score = better hospital.

4. RANK
   Candidates are sorted by total_score ascending.  rank 1 = chosen hospital.

─── Why dynamic per-condition weights make this a triage algorithm ───────────
A static nearest-hospital rule is wrong for emergency dispatch because:
  • A cardiac arrest needs a cath-lab, not just the closest ED.
  • A critical trauma patient needs speed above all — 5 minutes closer beats
    a slightly better facility every time.
  • A stable patient should go to a less-burdened hospital so the system
    stays balanced for the next critical case.

The WEIGHTS dict in weights.py encodes this clinical policy.  The SAME
hospital can rank #1 for STABLE (good load distribution) and #3 for CRITICAL
(no trauma specialization, borderline ICU capacity).  This dynamic ranking is
what makes the algorithm a triage engine rather than a geocoder.

─── Design: pure function over in-memory data ────────────────────────────────
score_hospitals() takes pre-fetched Hospital ORM objects and the in-memory
RoadGraph.  It performs no I/O.  This makes it trivially testable in isolation
without mocking a database.  The endpoint handler is responsible for fetching
hospitals and checking graph readiness before calling the scorer.

─── Complexity ───────────────────────────────────────────────────────────────
For H hospitals and a graph with V nodes and E edges:
  Routing:     O(H × (V + E) log V) — one A* per reachable candidate
  Scoring:     O(H × F) where F = 6 (constant number of factors, including
               the B4 surge factor — its lookup is O(1) per hospital)
  Sorting:     O(H log H)
  Total:       O(H × (V + E) log V)

On the 2 500-node Mumbai grid with H = 10 hospitals, the routing step
dominates and completes in < 50 ms in practice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.config import settings
from app.graph.astar import _max_haversine_speed_m_per_s, astar
from app.graph.haversine import haversine
from app.graph.road_graph import RoadGraph
from app.infra.models import Hospital
from app.scoring.surge import SurgeInfo, get_surge
from app.scoring.weights import SPECIALTY_REQUIREMENT, WEIGHTS, ScoringWeights


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class FactorScore:
    """One factor's contribution to a hospital's total score."""
    raw: float           # Actual measurement (s, ratio, or 0/1 binary)
    penalty: float       # Mapped to [0, 1]: 0 = best, 1 = worst
    weight: float        # From the condition's ScoringWeights
    contribution: float  # penalty × weight — this factor's slice of total_score
    note: str = ""       # human-readable explanation (used by the surge factor)


@dataclass
class ScoredCandidate:
    """A hospital that passed filtering, with route metrics and breakdown."""
    hospital: Hospital
    travel_time_s: float
    distance_m: float
    node_ids: list[int]
    total_score: float = 0.0   # populated in step 3 after normalization
    rank: int = 0              # populated in step 4 after sorting
    factors: dict[str, FactorScore] = field(default_factory=dict)


@dataclass
class FilteredOutCandidate:
    """A hospital excluded before scoring, with the reason recorded."""
    hospital: Hospital
    reason: str


@dataclass
class ScoringResult:
    """Complete output of score_hospitals()."""
    scored: list[ScoredCandidate]         # ranked best → worst (rank 1 = winner)
    filtered_out: list[FilteredOutCandidate]
    condition: str
    src_node_id: int


# ── Public API ────────────────────────────────────────────────────────────────

def score_hospitals(
    hospitals: list[Hospital],
    src_node_id: int,
    condition: str,
    road_graph: RoadGraph,
    max_travel_time_s: float | None = None,
) -> ScoringResult:
    """
    Filter, score, and rank hospitals for an emergency with the given condition.

    Args:
        hospitals:         All hospitals fetched from the DB (unfiltered).
        src_node_id:       Road graph node nearest to the emergency location.
        condition:         PatientCondition string (e.g. "CRITICAL", "STABLE").
        road_graph:        In-memory road network.  Must be populated.
        max_travel_time_s: Optional hard cap — hospitals beyond this travel
                           time are excluded regardless of other factors.

    Returns:
        ScoringResult with ranked candidates and a list of filtered-out
        hospitals with their disqualification reasons.
    """
    weights = WEIGHTS.get(condition, WEIGHTS["STABLE"])
    icu_required = condition in ("CRITICAL", "CARDIAC")

    # Compute max_speed once for all per-hospital heuristics (O(V+E)).
    max_speed = _max_haversine_speed_m_per_s(road_graph)

    scored: list[ScoredCandidate] = []
    filtered_out: list[FilteredOutCandidate] = []

    # ── Step 1: filter + route ────────────────────────────────────────────────
    for hospital in hospitals:
        reason = _filter_reason(hospital, icu_required)
        if reason:
            filtered_out.append(FilteredOutCandidate(hospital=hospital, reason=reason))
            continue

        result = astar(
            road_graph,
            src_node_id,
            hospital.nearest_node_id,  # type: ignore[arg-type]
            heuristic=_make_heuristic(road_graph, hospital.nearest_node_id, max_speed),
        )

        if result is None:
            filtered_out.append(FilteredOutCandidate(
                hospital=hospital,
                reason="unreachable: no path in the road graph",
            ))
            continue

        if max_travel_time_s is not None and result.total_travel_time_s > max_travel_time_s:
            filtered_out.append(FilteredOutCandidate(
                hospital=hospital,
                reason=(
                    f"travel time {result.total_travel_time_s:.0f}s exceeds "
                    f"limit {max_travel_time_s:.0f}s"
                ),
            ))
            continue

        scored.append(ScoredCandidate(
            hospital=hospital,
            travel_time_s=result.total_travel_time_s,
            distance_m=result.total_distance_m,
            node_ids=result.node_ids,
        ))

    if not scored:
        return ScoringResult(
            scored=[],
            filtered_out=filtered_out,
            condition=condition,
            src_node_id=src_node_id,
        )

    # ── Step 2: normalize travel times ────────────────────────────────────────
    # All other factors are already in [0,1]; only travel time needs cross-
    # candidate normalization because it's in seconds.
    travel_times = [c.travel_time_s for c in scored]
    min_tt = min(travel_times)
    max_tt = max(travel_times)
    tt_range = max_tt - min_tt

    # ── Step 3: compute per-candidate score and breakdown ─────────────────────
    spec_tag = SPECIALTY_REQUIREMENT.get(condition)

    for candidate in scored:
        tt_penalty = (
            (candidate.travel_time_s - min_tt) / tt_range
            if tt_range > 0
            else 0.0
        )
        surge_info = get_surge(candidate.hospital.region)
        factors = _compute_factors(candidate.hospital, tt_penalty, spec_tag, weights, surge_info)
        candidate.factors = factors
        candidate.total_score = sum(f.contribution for f in factors.values())

    # ── Step 4: rank ascending by score ──────────────────────────────────────
    scored.sort(key=lambda c: c.total_score)
    for rank, candidate in enumerate(scored, start=1):
        candidate.rank = rank

    return ScoringResult(
        scored=scored,
        filtered_out=filtered_out,
        condition=condition,
        src_node_id=src_node_id,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _filter_reason(hospital: Hospital, icu_required: bool) -> str | None:
    """Return a disqualification reason string, or None if the hospital passes."""
    if hospital.nearest_node_id is None:
        return "not snapped to road graph — run the snap script"
    if hospital.available_beds <= 0:
        return "no available beds"
    if icu_required and hospital.available_icu_beds <= 0:
        return "no available ICU beds (required for CRITICAL/CARDIAC patients)"
    return None


def _make_heuristic(
    road_graph: RoadGraph,
    goal_id: int,
    max_speed: float,
) -> Callable[[int], float]:
    """Build an admissible Haversine heuristic for a specific goal node."""
    coords = road_graph.get_coords(goal_id)
    if coords is None:
        return lambda _: 0.0
    goal_lat, goal_lon = coords

    def h(node: int) -> float:
        c = road_graph.get_coords(node)
        if c is None:
            return 0.0
        return haversine(c[0], c[1], goal_lat, goal_lon) / max_speed

    return h


def _compute_factors(
    hospital: Hospital,
    travel_time_penalty: float,
    spec_tag: str | None,
    weights: ScoringWeights,
    surge_info: SurgeInfo,
) -> dict[str, FactorScore]:
    """
    Compute the six penalty factors for one hospital: the five clinical
    factors plus the B4 surge factor.

    Returns a dict keyed by factor name so callers can access individual
    contributions by name (e.g. factors["travel_time"].contribution).
    """
    # ── bed availability penalty ──────────────────────────────────────────────
    if hospital.total_beds > 0:
        bed_penalty = 1.0 - hospital.available_beds / hospital.total_beds
    else:
        bed_penalty = 1.0

    # ── ICU availability penalty ──────────────────────────────────────────────
    if hospital.total_icu_beds > 0:
        icu_penalty = 1.0 - hospital.available_icu_beds / hospital.total_icu_beds
    else:
        icu_penalty = 1.0   # no ICU capacity at all → worst ICU score

    # ── load factor penalty ───────────────────────────────────────────────────
    if hospital.total_beds > 0:
        load_penalty = hospital.current_load / hospital.total_beds
    else:
        load_penalty = 1.0

    # ── specialization penalty ────────────────────────────────────────────────
    if spec_tag is None:
        spec_penalty = 0.0   # any hospital matches for this condition
    else:
        spec_penalty = 0.0 if spec_tag in (hospital.specializations or []) else 1.0

    # ── surge penalty (B4) ────────────────────────────────────────────────────
    # Added on top of the existing 1.0 weight budget: with no active surge
    # (surge_info.level == 0), this contributes exactly 0 and total_score is
    # unchanged from pre-B4 behaviour.
    if surge_info.level > 0:
        surge_note = (
            f"penalized: {surge_info.disease_name} surge in "
            f"{surge_info.region}, severity {surge_info.severity}"
        )
    else:
        surge_note = f"no active outbreak surge in {hospital.region or 'an unmapped region'}"

    return {
        "travel_time": FactorScore(
            raw=_raw_tt(travel_time_penalty),
            penalty=travel_time_penalty,
            weight=weights.travel_time,
            contribution=travel_time_penalty * weights.travel_time,
        ),
        "bed_availability": FactorScore(
            raw=hospital.available_beds / max(hospital.total_beds, 1),
            penalty=bed_penalty,
            weight=weights.bed_availability,
            contribution=bed_penalty * weights.bed_availability,
        ),
        "icu_availability": FactorScore(
            raw=(hospital.available_icu_beds / hospital.total_icu_beds
                 if hospital.total_icu_beds > 0 else 0.0),
            penalty=icu_penalty,
            weight=weights.icu_availability,
            contribution=icu_penalty * weights.icu_availability,
        ),
        "load_factor": FactorScore(
            raw=hospital.current_load / max(hospital.total_beds, 1),
            penalty=load_penalty,
            weight=weights.load_factor,
            contribution=load_penalty * weights.load_factor,
        ),
        "specialization": FactorScore(
            raw=1.0 - spec_penalty,   # raw: 1 = match, 0 = no match
            penalty=spec_penalty,
            weight=weights.specialization,
            contribution=spec_penalty * weights.specialization,
        ),
        "surge": FactorScore(
            raw=surge_info.level,
            penalty=surge_info.level,
            weight=settings.surge_weight,
            contribution=surge_info.level * settings.surge_weight,
            note=surge_note,
        ),
    }


def _raw_tt(normalized_tt_penalty: float) -> float:
    """Placeholder — raw travel_time (in seconds) is stored on ScoredCandidate directly."""
    return normalized_tt_penalty  # exposed via ScoredCandidate.travel_time_s
