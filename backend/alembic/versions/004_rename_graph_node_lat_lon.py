"""rename lat/lon → latitude/longitude on graph_nodes and disease_reports

Revision ID: 004
Revises: 003
Create Date: 2026-06-09

Root cause of the fix:
  Migration 002 renamed lat/lon on `hospitals` and `emergency_cases` but missed
  the same columns on `graph_nodes` and `disease_reports`.  The ORM models were
  updated to use latitude/longitude in Phase A2, causing a column-not-found crash
  on startup because the DB still had the old names.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("graph_nodes", "lat", new_column_name="latitude")
    op.alter_column("graph_nodes", "lon", new_column_name="longitude")
    op.alter_column("disease_reports", "lat", new_column_name="latitude")
    op.alter_column("disease_reports", "lon", new_column_name="longitude")


def downgrade() -> None:
    op.alter_column("disease_reports", "longitude", new_column_name="lon")
    op.alter_column("disease_reports", "latitude", new_column_name="lat")
    op.alter_column("graph_nodes", "longitude", new_column_name="lon")
    op.alter_column("graph_nodes", "latitude", new_column_name="lat")
