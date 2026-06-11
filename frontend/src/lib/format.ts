import { DISEASE_LABELS } from './constants';

export function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function formatZ(z: number | null): string {
  if (z === null) return '—';
  if (z >= 999) return '>5σ';
  return `${z.toFixed(2)}σ`;
}

export function diseaseLabel(slug: string | null): string {
  if (!slug) return '—';
  return DISEASE_LABELS[slug] ?? slug;
}

export function fmt(n: number): string {
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return n.toLocaleString();
}
