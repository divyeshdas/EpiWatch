"""outbreak_timeseries: historical disease case counts indexed for range queries

Revision ID: 005
Revises: 004
Create Date: 2026-06-09

Design notes:

  outbreak_timeseries is separate from disease_reports because they serve
  different purposes:
    - disease_reports: operational, incident-level reports from field workers
      (one row per report, timestamptz precision, no deaths column)
    - outbreak_timeseries: analytical, calendar-day aggregated case counts from
      public health data sources like OWID (one row per disease × region × day)

  Column types:
    date  DATE (not TIMESTAMP) — the observation is identified by its calendar
    day, not a clock time.  DATE is 4 bytes vs 8, and GROUP BY date works
    without date_trunc.

  Index strategy:
    (disease_name, region, date) composite index rather than three separate
    indexes.  Our dominant query pattern is:
      WHERE disease_name = ? AND region = ? AND date BETWEEN ? AND ?
    A composite index on (disease_name, region, date) in this order satisfies
    that query with a single B-tree scan: the first two columns narrow to one
    time series, then date is a range scan within that slice.  Creating the
    date equality index first would be wrong because date is the range column.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbreak_timeseries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("disease_name", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=False),
        # DATE (not TIMESTAMP) — calendar day is the natural granularity for
        # public health surveillance data.
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        # deaths may be absent in some datasets; default 0 rather than nullable
        # so aggregation doesn't need COALESCE everywhere.
        sa.Column("deaths", sa.Integer(), nullable=False, server_default="0"),
        # source tracks provenance (e.g. "OWID", "WHO", "NVBDCP") so queries
        # can filter or attribute correctly.
        sa.Column("source", sa.String(), nullable=False, server_default="'OWID'"),
    )

    op.create_index(
        "ix_outbreak_disease_region_date",
        "outbreak_timeseries",
        ["disease_name", "region", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbreak_disease_region_date", "outbreak_timeseries")
    op.drop_table("outbreak_timeseries")
