"""align operational schema

Revision ID: 002
Revises: 001
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- hospitals ---
    op.alter_column("hospitals", "lat", new_column_name="latitude")
    op.alter_column("hospitals", "lon", new_column_name="longitude")
    op.alter_column("hospitals", "icu_total", new_column_name="total_icu_beds")
    op.alter_column("hospitals", "icu_available", new_column_name="available_icu_beds")
    # load_factor (float ratio) is computed from current_load / total_beds at scoring time;
    # we store the raw integer count instead so hospitals report a concrete number.
    op.drop_column("hospitals", "load_factor")
    op.add_column(
        "hospitals",
        sa.Column("current_load", sa.Integer(), nullable=False, server_default="0"),
    )
    # emergency_capacity: maximum simultaneous emergency cases the ED can handle;
    # kept separate from total_beds because ED throughput ≠ inpatient capacity.
    op.add_column(
        "hospitals",
        sa.Column("emergency_capacity", sa.Integer(), nullable=False, server_default="0"),
    )

    # --- emergency_cases ---
    op.alter_column("emergency_cases", "location_lat", new_column_name="latitude")
    op.alter_column("emergency_cases", "location_lon", new_column_name="longitude")
    # patient_condition drives routing weights; enum values map directly to scoring model:
    # STABLE → load-balance, SERIOUS/CRITICAL → ICU proximity, CARDIAC → specialization.
    op.alter_column("emergency_cases", "severity", new_column_name="patient_condition")
    op.alter_column("emergency_cases", "reported_at", new_column_name="created_at")


def downgrade() -> None:
    op.alter_column("emergency_cases", "created_at", new_column_name="reported_at")
    op.alter_column("emergency_cases", "patient_condition", new_column_name="severity")
    op.alter_column("emergency_cases", "longitude", new_column_name="location_lon")
    op.alter_column("emergency_cases", "latitude", new_column_name="location_lat")

    op.drop_column("hospitals", "emergency_capacity")
    op.drop_column("hospitals", "current_load")
    op.add_column(
        "hospitals",
        sa.Column("load_factor", sa.Double(), nullable=False, server_default="0.0"),
    )
    op.alter_column("hospitals", "available_icu_beds", new_column_name="icu_available")
    op.alter_column("hospitals", "total_icu_beds", new_column_name="icu_total")
    op.alter_column("hospitals", "longitude", new_column_name="lon")
    op.alter_column("hospitals", "latitude", new_column_name="lat")
