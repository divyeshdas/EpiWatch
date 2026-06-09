from sqlalchemy import Column, Double, ForeignKey, Integer, String, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB

from app.infra.database import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    lat = Column(Double, nullable=False)
    lon = Column(Double, nullable=False)
    total_beds = Column(Integer, nullable=False, default=0)
    available_beds = Column(Integer, nullable=False, default=0)
    icu_total = Column(Integer, nullable=False, default=0)
    icu_available = Column(Integer, nullable=False, default=0)
    specializations = Column(JSONB, nullable=False, default=list)
    load_factor = Column(Double, nullable=False, default=0.0)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class DiseaseReport(Base):
    __tablename__ = "disease_reports"

    id = Column(Integer, primary_key=True)
    disease_name = Column(String, nullable=False)
    region = Column(String, nullable=False)
    lat = Column(Double, nullable=True)
    lon = Column(Double, nullable=True)
    case_count = Column(Integer, nullable=False, default=0)
    reported_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class EmergencyCase(Base):
    __tablename__ = "emergency_cases"

    id = Column(Integer, primary_key=True)
    location_lat = Column(Double, nullable=False)
    location_lon = Column(Double, nullable=False)
    severity = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    reported_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    assigned_hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=True)
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    region = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)


class GraphNode(Base):
    __tablename__ = "graph_nodes"

    id = Column(Integer, primary_key=True)
    lat = Column(Double, nullable=False)
    lon = Column(Double, nullable=False)
    node_type = Column(String, nullable=False, default="intersection")
    meta = Column("meta", JSONB, nullable=False, default=dict)


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True)
    source_node_id = Column(Integer, ForeignKey("graph_nodes.id"), nullable=False)
    target_node_id = Column(Integer, ForeignKey("graph_nodes.id"), nullable=False)
    weight = Column(Double, nullable=False)
    distance_km = Column(Double, nullable=False)
    meta = Column("meta", JSONB, nullable=False, default=dict)
