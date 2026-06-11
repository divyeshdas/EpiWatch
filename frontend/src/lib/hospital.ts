// Shared hospital-load/availability helpers, used by the dispatch map
// (/emergency) and its tab views (Hospitals, Reports). Keeping the
// red/amber/green thresholds here means every view colors load and bed
// availability the same way.

import type { Hospital } from './types';

export function loadFactor(h: Hospital): number {
  return h.total_beds > 0 ? h.current_load / h.total_beds : 0;
}

export function loadColor(h: Hospital): string {
  const lf = loadFactor(h);
  if (lf >= 0.85) return '#c94a45';
  if (lf >= 0.6) return '#a8893f';
  return '#5f806b';
}

// Color for an availability bar (beds/ICU) — low remaining capacity reads
// as severe, same risk vocabulary as hospital load.
export function occupancyColor(available: number, total: number): string {
  if (total <= 0) return '#78716c';
  const ratio = available / total;
  if (ratio <= 0.15) return '#c94a45';
  if (ratio <= 0.4) return '#a8893f';
  return '#5f806b';
}

export function availabilityPct(available: number, total: number): number {
  return total > 0 ? (available / total) * 100 : 0;
}

export function pct(n: number): string {
  return `${Math.round(n)}%`;
}

export function fmtKm(m: number): string {
  return `${(m / 1000).toFixed(2)} km`;
}

export function fmtMin(s: number): string {
  return `${Math.max(1, Math.round(s / 60))} min`;
}
