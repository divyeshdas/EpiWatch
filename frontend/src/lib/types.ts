// Shared API response types for the dispatch (Pillar A) tab views —
// /emergency/hospitals, /emergency/history, /emergency/routes,
// /emergency/reports. Mirrors the Pydantic response models in
// backend/app/domain/schemas.py.

export type Hospital = {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  total_beds: number;
  available_beds: number;
  total_icu_beds: number;
  available_icu_beds: number;
  emergency_capacity: number;
  current_load: number;
  specializations: string[];
  region: string | null;
  updated_at: string;
};

export type EmergencyCase = {
  id: number;
  latitude: number;
  longitude: number;
  patient_condition: string;
  status: string;
  created_at: string;
  assigned_hospital_id: number | null;
};

export type RouteNode = { node_id: number; latitude: number; longitude: number };

export type RouteDetail = {
  path: RouteNode[];
  total_distance_m: number;
  total_travel_time_s: number;
  node_count: number;
};

export type RouteResponse = {
  route: RouteDetail | null;
  reason?: string;
};
