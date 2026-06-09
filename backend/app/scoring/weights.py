"""
Condition-keyed scoring weights for the hospital selection algorithm.

─── Why weights are condition-dependent ──────────────────────────────────────
Triage is not "nearest hospital." What constitutes the *best* hospital depends
entirely on what the patient needs:

  CRITICAL   Trauma / life-threatening emergency.
             Speed dominates — every minute in transit raises mortality.
             ICU availability is second priority: the patient will likely need
             intensive post-stabilisation care.

  CARDIAC    Cardiac arrest or severe cardiac event.
             Specialization is the primary filter: a cardiac unit with trained
             cardiologists, cath-labs, and cardiac ICU beds dramatically
             improves outcomes.  A general hospital that is 5 minutes closer
             cannot compensate for lack of cardiac capability.

  SERIOUS    Acutely ill, not immediately life-threatening.
             Balanced across speed, bed availability, and hospital load.
             ICU is a secondary concern — the patient may need it, but other
             factors also matter meaningfully.

  STABLE     Non-urgent.  The best use of the system is load-balancing: send
             the patient to a less-burdened hospital rather than always piling
             onto the nearest one.  Bed availability and load factor dominate.

This dynamic re-weighting is what makes the scoring a triage algorithm rather
than a simple nearest-hospital lookup.  The SAME hospital can rank #1 for
STABLE and #3 for CRITICAL, because the definition of "best" shifts.

─── How the score is computed ────────────────────────────────────────────────
Every factor is mapped to a penalty ∈ [0, 1]:
  0 = ideal for that factor   (fastest, most available, perfectly matched)
  1 = worst for that factor   (slowest, fully occupied, no specialization)

Total score = Σ (weight_i × penalty_i)   — lower is better.

Because all penalties share the [0,1] scale and weights sum to 1.0, the total
score is also in [0, 1] and is directly interpretable as a weighted average
penalty across factors.

─── Why this file is separate from scorer.py ─────────────────────────────────
The weights capture the clinical policy of the triage system.  Separating them
from the algorithmic logic means tuning the policy requires no code change —
only this file.  In a production deployment these would be loaded from a
configuration store (e.g. a YAML file or an admin-editable database table) so
a clinical lead can adjust them without a code deploy.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringWeights:
    """
    All weights must sum to exactly 1.0 so the total score is in [0, 1].

    Fields (all are penalty weights — larger weight means more influence):
      travel_time      Normalized travel time to the hospital (0 = fastest)
      icu_availability 1 − (available_icu / total_icu)  (0 = all ICU beds free)
      bed_availability 1 − (available_beds / total_beds) (0 = all beds free)
      load_factor      current_load / total_beds         (0 = empty hospital)
      specialization   0 if hospital handles this condition, 1 otherwise
    """
    travel_time: float
    icu_availability: float
    bed_availability: float
    load_factor: float
    specialization: float

    def __post_init__(self) -> None:
        total = (
            self.travel_time
            + self.icu_availability
            + self.bed_availability
            + self.load_factor
            + self.specialization
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"ScoringWeights must sum to 1.0, got {total:.6f}")


# ── Condition-keyed weights ───────────────────────────────────────────────────

WEIGHTS: dict[str, ScoringWeights] = {
    # CRITICAL: speed and ICU dominate; specialization is least important
    # (any well-equipped trauma center can handle most critical cases).
    "CRITICAL": ScoringWeights(
        travel_time=0.45,
        icu_availability=0.30,
        bed_availability=0.10,
        load_factor=0.10,
        specialization=0.05,
    ),

    # CARDIAC: specialization is the primary factor — a cardiac unit with
    # cath-labs and cardiac-trained staff dramatically improves survival.
    # Speed is still important, but a 10-minute detour to a cardiac centre
    # is almost always worth it.
    "CARDIAC": ScoringWeights(
        travel_time=0.30,
        icu_availability=0.20,
        bed_availability=0.05,
        load_factor=0.05,
        specialization=0.40,
    ),

    # SERIOUS: balanced — the patient needs timely care and a hospital that
    # can admit them, but no single factor overwhelmingly dominates.
    "SERIOUS": ScoringWeights(
        travel_time=0.35,
        icu_availability=0.20,
        bed_availability=0.20,
        load_factor=0.15,
        specialization=0.10,
    ),

    # STABLE: load-balancing mode.  Bed availability and current load dominate
    # so the system distributes demand across the hospital network rather than
    # funnelling everyone to the nearest (and often most saturated) facility.
    "STABLE": ScoringWeights(
        travel_time=0.20,
        icu_availability=0.05,
        bed_availability=0.35,
        load_factor=0.30,
        specialization=0.10,
    ),
}


# ── Per-condition specialization requirement ──────────────────────────────────
# Maps each patient condition to the hospital specialization tag that earns a
# full match (penalty=0).  None means any hospital matches.

SPECIALTY_REQUIREMENT: dict[str, str | None] = {
    "CARDIAC":  "cardiac",
    "CRITICAL": "trauma",
    "SERIOUS":  "general",
    "STABLE":   None,      # any hospital is appropriate
}
