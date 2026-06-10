"""hospitals: add region column for surveillance-aware routing

Revision ID: 007
Revises: 006
Create Date: 2026-06-10

Design notes:

  B4 wires Pillar B (surveillance) into Pillar A (routing) via a "surge
  penalty" on hospital scores: a hospital sitting in a region with an active
  outbreak alert should rank worse, all else equal.

  B3's alerts carry a `region`, but that string needs to mean the same thing
  on both sides of the bridge for the lookup to work.  B2's disease_reports
  (and its hotspot seed) use Mumbai-neighbourhood names -- Bandra, Dadar,
  Dharavi, Worli, Andheri, Mulund, etc. (see app/surveillance_seed.py
  _REGIONS) -- which is fine-grained enough to differentiate individual
  hospitals.  hospitals had no region column at all, so this migration adds
  one and backfills the 10 seeded hospitals with the nearest of those
  neighbourhood names by geography.

  Nullable, since a hospital with no region simply never has an active surge
  (app.scoring.surge.get_surge returns level 0 for region=None).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Hand-assigned by nearest B2 _REGIONS neighbourhood centroid to each
# hospital's coordinates (see app/seed.py for hospital lat/lon).
_HOSPITAL_REGIONS = {
    "KEM Hospital": "Dadar",
    "Hinduja Hospital": "Dharavi",
    "Lilavati Hospital": "Bandra",
    "Breach Candy Hospital": "Worli",
    "Jaslok Hospital": "Worli",
    "Nanavati Hospital": "Andheri",
    "Cooper Hospital": "Andheri",
    "Bombay Hospital": "Worli",
    "Seven Hills Hospital": "Andheri",
    "Wockhardt Hospital Mulund": "Mulund",
}


def upgrade() -> None:
    op.add_column("hospitals", sa.Column("region", sa.String(), nullable=True))

    hospitals = sa.table(
        "hospitals",
        sa.column("name", sa.String),
        sa.column("region", sa.String),
    )
    for name, region in _HOSPITAL_REGIONS.items():
        op.execute(
            hospitals.update().where(hospitals.c.name == name).values(region=region)
        )


def downgrade() -> None:
    op.drop_column("hospitals", "region")
