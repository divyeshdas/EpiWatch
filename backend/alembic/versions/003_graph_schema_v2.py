"""graph schema v2: typed node_type, renamed edge weights, nearest_node on hospitals

Revision ID: 003
Revises: 002
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # graph_edges: rename weight → travel_time_s, distance_km → distance_m
    # travel_time_s and distance_m are the primary edge weights for Dijkstra / A*.
    op.alter_column("graph_edges", "weight", new_column_name="travel_time_s")
    op.alter_column("graph_edges", "distance_km", new_column_name="distance_m")

    # Index on source_node_id — every neighbor lookup does WHERE source_node_id = ?
    op.create_index("ix_graph_edges_source", "graph_edges", ["source_node_id"])

    # hospitals.nearest_node_id — K-D tree snap result; null until snap script runs
    op.add_column(
        "hospitals",
        sa.Column(
            "nearest_node_id",
            sa.Integer(),
            sa.ForeignKey("graph_nodes.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("hospitals", "nearest_node_id")
    op.drop_index("ix_graph_edges_source", "graph_edges")
    op.alter_column("graph_edges", "distance_m", new_column_name="distance_km")
    op.alter_column("graph_edges", "travel_time_s", new_column_name="weight")
