// Shared types/constants for alerts and surveillance data, used by the
// /alerts and /data-explorer pages. (The /surveillance page keeps its own
// copies — left as-is to avoid touching its working logic.)

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type AlertRow = {
  id: number;
  type: string;
  severity: Severity;
  message: string;
  region: string | null;
  disease_name: string | null;
  event_date: string | null;
  z_score: number | null;
  created_at: string;
  resolved_at: string | null;
};

export const DISEASE_LABELS: Record<string, string> = {
  covid_19: 'COVID-19',
  measles: 'Measles',
  dengue: 'Dengue',
  cholera: 'Cholera',
};

export const DISEASE_COLORS: Record<string, string> = {
  covid_19: '#14b8a6',
  measles: '#c94a45',
  dengue: '#a8893f',
  cholera: '#78716c',
};

// Same low-to-severe scale used across the app (map risk levels, alert
// severity).
export const SEVERITY_COLORS: Record<Severity, string> = {
  LOW: '#5f806b',
  MEDIUM: '#a8893f',
  HIGH: '#b96532',
  CRITICAL: '#c94a45',
};
