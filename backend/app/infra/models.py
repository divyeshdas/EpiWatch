from sqlalchemy import Column, Double, ForeignKey, Integer, String, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB

from app.infra.database import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    latitude = Column(Double, nullable=False)
    longitude = Column(Double, nullable=False)
    total_beds = Column(Integer, nullable=False, default=0)
    available_beds = Column(Integer, nullable=False, default=0)
    total_icu_beds = Column(Integer, nullable=False, default=0)
    available_icu_beds = Column(Integer, nullable=False, default=0)
    emergency_capacity = Column(Integer, nullable=False, default=0)
    current_load = Column(Integer, nullable=False, default=0)
    specializations = Column(JSONB, nullable=False, default=list)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    # set by snap script using K-D tree; null until graph is loaded
    nearest_node_id = Column(Integer, ForeignKey("graph_nodes.id"), nullable=True)


class DiseaseReport(Base):
    __tablename__ = "disease_reports"

    id = Column(Integer, primary_key=True)
    disease_name = Column(String, nullable=False)
    region = Column(String, nullable=False)
    latitude = Column(Double, nullable=True)
    longitude = Column(Double, nullable=True)
    case_count = Column(Integer, nullable=False, default=0)
    reported_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class EmergencyCase(Base):
    __tablename__ = "emergency_cases"

    id = Column(Integer, primary_key=True)
    latitude = Column(Double, nullable=False)
    longitude = Column(Double, nullable=False)
    patient_condition = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
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
    latitude = Column(Double, nullable=False)
    longitude = Column(Double, nullable=False)
    # "intersection" for road junctions, "hospital" for hospital-snapped nodes
    node_type = Column(String, nullable=False, default="intersection")
    meta = Column("meta", JSONB, nullable=False, default=dict)


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True)
    source_node_id = Column(Integer, ForeignKey("graph_nodes.id"), nullable=False)
    target_node_id = Column(Integer, ForeignKey("graph_nodes.id"), nullable=False)
    # distance_m: physical road distance in metres (from OSM length attribute)
    distance_m = Column(Double, nullable=False)
    # travel_time_s: estimated traversal time in seconds (distance / speed_kph)
    travel_time_s = Column(Double, nullable=False)
    meta = Column("meta", JSONB, nullable=False, default=dict)
