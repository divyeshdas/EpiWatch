"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hospitals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("total_beds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_beds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("icu_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("icu_available", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("specializations", JSONB(), nullable=False, server_default="[]"),
        sa.Column("load_factor", sa.Double(), nullable=False, server_default="0.0"),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "disease_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("disease_name", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=False),
        sa.Column("lat", sa.Double(), nullable=True),
        sa.Column("lon", sa.Double(), nullable=True),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "reported_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "emergency_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_lat", sa.Double(), nullable=False),
        sa.Column("location_lon", sa.Double(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="'PENDING'"),
        sa.Column(
            "reported_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("assigned_hospital_id", sa.Integer(), sa.ForeignKey("hospitals.id"), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("node_type", sa.String(), nullable=False, server_default="'intersection'"),
        sa.Column("meta", JSONB(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "graph_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_node_id", sa.Integer(), sa.ForeignKey("graph_nodes.id"), nullable=False),
        sa.Column("target_node_id", sa.Integer(), sa.ForeignKey("graph_nodes.id"), nullable=False),
        sa.Column("weight", sa.Double(), nullable=False),
        sa.Column("distance_km", sa.Double(), nullable=False),
        sa.Column("meta", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_table("graph_edges")
    op.drop_table("graph_nodes")
    op.drop_table("alerts")
    op.drop_table("emergency_cases")
    op.drop_table("disease_reports")
    op.drop_table("hospitals")
