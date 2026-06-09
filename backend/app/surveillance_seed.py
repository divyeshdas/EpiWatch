"""
Surveillance seed: populates disease_reports with ~6 months of simulated
outbreak history for the Mumbai metropolitan area.

Run with:  docker compose exec backend python -m app.surveillance_seed

The generated data has realistic statistical structure:
  - Dengue and leptospirosis peak in the monsoon window (weeks 15–26 from
    start), reflecting Mumbai's June–September rainy season.
  - Two deliberate spike events (5–8× baseline) that B3 spike detection
    should flag: dengue in Dharavi (week 18), cholera in Govandi (week 22).
  - Baseline noise uses Poisson-like variation around a per-(region, disease)
    mean so the time series looks real and B3 has meaningful signal-to-noise.
  - ~300 individual report rows across 15 regions and 8 diseases, one row per
    (region, disease, week) combination with some weeks skipped.

Why weekly granularity:
  Real public health reporting is weekly (WHO / IDSP cadence).  Daily
  granularity would imply a reporting fidelity we don't have; monthly
  would make B3 spike detection trivial.  Weekly gives B3 a meaningful
  sliding-window problem (~12 points per 90-day window).

Idempotent — skips all inserts if any disease_report row already exists.
"""
import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.infra.database import get_session_factory
from app.infra.models import DiseaseReport

# ── geographic anchors ────────────────────────────────────────────────────────

_REGIONS: list[dict] = [
    {"name": "Dharavi",      "lat": 19.0415, "lon": 72.8540},
    {"name": "Bandra",       "lat": 19.0597, "lon": 72.8355},
    {"name": "Andheri",      "lat": 19.1196, "lon": 72.8397},
    {"name": "Thane",        "lat": 19.2183, "lon": 72.9781},
    {"name": "Kurla",        "lat": 19.0724, "lon": 72.8790},
    {"name": "Worli",        "lat": 18.9987, "lon": 72.8176},
    {"name": "Govandi",      "lat": 19.0726, "lon": 72.9127},
    {"name": "Malad",        "lat": 19.1868, "lon": 72.8484},
    {"name": "Dadar",        "lat": 19.0178, "lon": 72.8478},
    {"name": "Kalyan",       "lat": 19.2403, "lon": 73.1305},
    {"name": "Navi Mumbai",  "lat": 19.0330, "lon": 73.0297},
    {"name": "Borivali",     "lat": 19.2280, "lon": 72.8567},
    {"name": "Matunga",      "lat": 19.0280, "lon": 72.8595},
    {"name": "Chembur",      "lat": 19.0626, "lon": 72.9050},
    {"name": "Mulund",       "lat": 19.1726, "lon": 72.9560},
]

# ── disease baselines and seasonality ─────────────────────────────────────────
# Each disease: (base_cases_per_week, monsoon_multiplier, primarily_in_regions)
# Monsoon = weeks 15–26 of the 26-week window (roughly June–September).

_DISEASES: list[dict] = [
    {
        "name": "dengue",
        "base": 8,
        "monsoon_mult": 3.5,
        "hot_regions": {"Dharavi", "Govandi", "Kurla", "Malad"},
    },
    {
        "name": "malaria",
        "base": 5,
        "monsoon_mult": 2.8,
        "hot_regions": {"Dharavi", "Govandi", "Thane", "Kalyan"},
    },
    {
        "name": "leptospirosis",
        "base": 2,
        "monsoon_mult": 4.0,
        "hot_regions": {"Dharavi", "Kurla", "Govandi"},
    },
    {
        "name": "cholera",
        "base": 3,
        "monsoon_mult": 2.0,
        "hot_regions": {"Govandi", "Dharavi", "Chembur"},
    },
    {
        "name": "typhoid",
        "base": 4,
        "monsoon_mult": 1.5,
        "hot_regions": set(),   # fairly uniform
    },
    {
        "name": "hepatitis_a",
        "base": 2,
        "monsoon_mult": 1.3,
        "hot_regions": {"Dadar", "Matunga", "Worli"},
    },
    {
        "name": "covid_19",
        "base": 12,
        "monsoon_mult": 1.0,
        "hot_regions": set(),   # no strong geographic concentration
    },
    {
        "name": "tuberculosis",
        "base": 6,
        "monsoon_mult": 1.0,
        "hot_regions": {"Dharavi", "Govandi", "Kurla"},
    },
]

# ── deliberate spike events ───────────────────────────────────────────────────
# These are 5–8× the expected baseline, designed to be caught by B3 z-score.

_SPIKES: list[dict] = [
    {"disease": "dengue",  "region": "Dharavi",  "week": 18, "multiplier": 7},
    {"disease": "cholera", "region": "Govandi",  "week": 22, "multiplier": 6},
    {"disease": "malaria", "region": "Kurla",    "week": 20, "multiplier": 5},
    {"disease": "dengue",  "region": "Govandi",  "week": 19, "multiplier": 6},
]

_WEEKS = 26         # ~6 months of weekly data
_RNG_SEED = 42


def _build_rows(start: datetime) -> list[dict]:
    """
    Generate all report rows deterministically.
    Returns a list of dicts ready for DiseaseReport(**row) insertion.
    """
    rng = random.Random(_RNG_SEED)

    spike_index: dict[tuple, int] = {
        (s["disease"], s["region"], s["week"]): s["multiplier"]
        for s in _SPIKES
    }

    rows: list[dict] = []

    for week in range(_WEEKS):
        reported_at = start + timedelta(weeks=week)
        in_monsoon = 15 <= week <= 26

        for disease in _DISEASES:
            for region in _REGIONS:
                base = disease["base"]

                # Hot-region multiplier: 2× baseline in primary regions
                if region["name"] in disease["hot_regions"]:
                    base = int(base * 2)

                # Seasonal monsoon multiplier
                if in_monsoon:
                    base = int(base * disease["monsoon_mult"])

                # Deliberate spike override
                spike_mult = spike_index.get(
                    (disease["name"], region["name"], week), 1
                )
                base = int(base * spike_mult)

                # Skip weeks where base is very low — not every region reports
                # every week.  Keeps the dataset sparse and realistic.
                if base < 2:
                    if rng.random() > 0.3:   # 70% chance of skipping low-count weeks
                        continue

                # Poisson-like noise: ±30% around base, minimum 1
                noise = rng.uniform(0.7, 1.3)
                case_count = max(1, int(base * noise))

                rows.append({
                    "disease_name": disease["name"],
                    "region": region["name"],
                    "latitude": region["lat"] + rng.uniform(-0.002, 0.002),
                    "longitude": region["lon"] + rng.uniform(-0.002, 0.002),
                    "case_count": case_count,
                    "reported_at": reported_at.replace(tzinfo=timezone.utc),
                })

    return rows


async def seed() -> None:
    async with get_session_factory()() as db:
        existing = await db.execute(select(DiseaseReport).limit(1))
        if existing.scalar_one_or_none() is not None:
            print("disease_reports already seeded — skipping")
            return

        # Start 26 weeks (≈6 months) before today
        start = datetime.now(timezone.utc) - timedelta(weeks=_WEEKS)
        rows = _build_rows(start)

        for row in rows:
            db.add(DiseaseReport(**row))

        await db.commit()
        print(f"seeded {len(rows)} disease reports across {_WEEKS} weeks")
        print(
            f"  ({len(_REGIONS)} regions × {len(_DISEASES)} diseases"
            f" × {_WEEKS} weeks, with {len(_SPIKES)} deliberate spike events)"
        )


if __name__ == "__main__":
    asyncio.run(seed())
