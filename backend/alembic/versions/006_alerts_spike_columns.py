"""alerts: add spike-detection context columns + dedup constraint

Revision ID: 006
Revises: 005
Create Date: 2026-06-10

Design notes:

  B3 spike detection turns each anomalous time-series point into an alert
  row.  The original alerts table (type, severity, message, region,
  created_at, resolved_at) has nowhere to record *which* disease/date/z-score
  a spike alert is about, so three columns are added:

    disease_name  the disease the spike was detected in
    event_date    the calendar date of the anomalous observation (not the
                   same as created_at, which is "when the alert was raised")
    z_score       the z-score that triggered the alert, for the message and
                   for the frontend to show alongside severity

  All three are nullable because non-spike alert types (none exist yet, but
  the table is generic) may not have this context.

  Idempotent re-scanning:
  -----------------------
  POST /surveillance/scan can be called repeatedly over the same series (e.g.
  whenever new data lands).  Re-running detection must not create duplicate
  alerts for a (type, disease_name, region, event_date) combination that was
  already raised.  uq_alerts_spike_dedup enforces this at the database level;
  AlertRepository.create_spike_alert() uses INSERT ... ON CONFLICT DO NOTHING
  against this constraint, so a duplicate scan is a no-op rather than a
  second row.  Postgres treats NULLs in unique constraints as distinct, which
  is fine here -- spike alerts always populate all four columns.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("disease_name", sa.String(), nullable=True))
    op.add_column("alerts", sa.Column("event_date", sa.Date(), nullable=True))
    op.add_column("alerts", sa.Column("z_score", sa.Double(), nullable=True))

    op.create_unique_constraint(
        "uq_alerts_spike_dedup",
        "alerts",
        ["type", "disease_name", "region", "event_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_alerts_spike_dedup", "alerts", type_="unique")
    op.drop_column("alerts", "z_score")
    op.drop_column("alerts", "event_date")
    op.drop_column("alerts", "disease_name")
