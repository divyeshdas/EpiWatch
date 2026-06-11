// Inline icon set (Tabler-style strokes — bolder, more distinct silhouettes
// than a generic line set). Static, developer-authored markup — safe to
// render with {@html}. Kept as plain strings so templates aren't drowned in
// SVG path data. One set, used everywhere.

const ICON_ATTRS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';

export const ICONS: Record<string, string> = {
  // Bespoke EpiWatch mark — pulse trace inside a ring. Not part of the
  // stroke-icon set above; kept as its own hand-drawn SVG.
  brand: `<svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true"><circle cx="13" cy="13" r="9.5" stroke="currentColor" stroke-width="1.6" opacity="0.35"/><path d="M5 13 H9 L11 8.5 L14 17.5 L16 13 H21" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,

  surveillance: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.8" fill="currentColor" stroke="none"/></svg>`,
  truck: `<svg ${ICON_ATTRS}><rect x="2" y="9" width="13" height="8" rx="1.5"/><path d="M15 12h3.5L21 14.5V17h-2"/><circle cx="7" cy="18" r="1.6"/><circle cx="17" cy="18" r="1.6"/><path d="M7 11v3M5.5 12.5h3"/></svg>`,
  globe: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.8 2.5 4.5 5.8 4.5 9s-1.7 6.5-4.5 9c-2.8-2.5-4.5-5.8-4.5-9S9.2 5.5 12 3z"/></svg>`,
  trend: `<svg ${ICON_ATTRS}><path d="M3 17l5-5 4 4 7-8"/><path d="M14 8h5v5"/></svg>`,
  activity: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="3.5"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/></svg>`,
  bell: `<svg ${ICON_ATTRS}><path d="M10 4.5a2 2 0 0 1 4 0c2.8 1 4.5 3.7 4.5 7v2.5l1.7 2.5H3.8l1.7-2.5V11.5c0-3.3 1.7-6 4.5-7z"/><path d="M9.5 19a2.5 2.5 0 0 0 5 0"/></svg>`,
  database: `<svg ${ICON_ATTRS}><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.66 3.58 3 8 3s8-1.34 8-3V6"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/></svg>`,
  file: `<svg ${ICON_ATTRS}><path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/><path d="M9 13h6M9 17h6"/></svg>`,
  book: `<svg ${ICON_ATTRS}><path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v16H6.5A1.5 1.5 0 0 0 5 20.5z"/><path d="M19 19v2"/><path d="M8.5 7.5h7M8.5 10.5h7"/></svg>`,
  settings: `<svg ${ICON_ATTRS}><path d="M10.3 3.2a1.7 1.7 0 0 1 3.4 0l.15.86a1.7 1.7 0 0 0 2.5 1.1l.74-.43a1.7 1.7 0 0 1 2.34 2.34l-.43.74a1.7 1.7 0 0 0 1.1 2.5l.86.15a1.7 1.7 0 0 1 0 3.4l-.86.15a1.7 1.7 0 0 0-1.1 2.5l.43.74a1.7 1.7 0 0 1-2.34 2.34l-.74-.43a1.7 1.7 0 0 0-2.5 1.1l-.15.86a1.7 1.7 0 0 1-3.4 0l-.15-.86a1.7 1.7 0 0 0-2.5-1.1l-.74.43a1.7 1.7 0 0 1-2.34-2.34l.43-.74a1.7 1.7 0 0 0-1.1-2.5l-.86-.15a1.7 1.7 0 0 1 0-3.4l.86-.15a1.7 1.7 0 0 0 1.1-2.5l-.43-.74A1.7 1.7 0 0 1 6.9 3.83l.74.43a1.7 1.7 0 0 0 2.5-1.1z"/><circle cx="12" cy="12" r="3.2"/></svg>`,
  help: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="9"/><path d="M9.2 9.2a3 3 0 0 1 5.7 1.3c0 2-3 2.5-3 4.5"/><path d="M12 17.7v.01"/></svg>`,
  search: `<svg ${ICON_ATTRS}><circle cx="10.5" cy="10.5" r="6.5"/><path d="M19.5 19.5l-4-4"/></svg>`,
  share: `<svg ${ICON_ATTRS}><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.2 10.7l7.6-4.4M8.2 13.3l7.6 4.4"/></svg>`,
  download: `<svg ${ICON_ATTRS}><path d="M12 3v12"/><path d="M7 11l5 5 5-5"/><path d="M4 21h16"/></svg>`,
  filter: `<svg ${ICON_ATTRS}><path d="M4 5h16l-6.2 7v5.2l-3.6 1.8v-7z"/></svg>`,
  menu: `<svg ${ICON_ATTRS}><path d="M4 6h16M4 12h16M4 18h16"/></svg>`,
  refresh: `<svg ${ICON_ATTRS}><path d="M19.95 11a8 8 0 1 0-.5 4.2"/><path d="M20 4.5v5h-5"/></svg>`,
  sun: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12h2.5M19 12h2.5M5 5l1.8 1.8M17.2 17.2L19 19M19 5l-1.8 1.8M6.8 17.2L5 19"/></svg>`,
  moon: `<svg ${ICON_ATTRS}><path d="M12.5 3a7.5 7.5 0 1 0 8.5 10.7A9 9 0 0 1 12.5 3z"/></svg>`,
  arrowRight: `<svg ${ICON_ATTRS}><path d="M4 12h16"/><path d="M14 6l6 6-6 6"/></svg>`,
  panel: `<svg ${ICON_ATTRS}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/></svg>`,
  x: `<svg ${ICON_ATTRS}><path d="M6 6l12 12"/><path d="M6 18L18 6"/></svg>`,
  cross: `<svg ${ICON_ATTRS}><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M12 7.5v9M7.5 12h9"/></svg>`,
  zap: `<svg ${ICON_ATTRS}><path d="M13 2 4 14h6l-1 8 9-12h-6z"/></svg>`,
  bed: `<svg ${ICON_ATTRS}><path d="M3 19v-9"/><path d="M3 13h18a1 1 0 0 1 1 1v5"/><path d="M3 18h19"/><circle cx="7.5" cy="10" r="1.5"/><path d="M10.5 13V9.5a1 1 0 0 1 1-1H20a1 1 0 0 1 1 1V13"/></svg>`,
  alertTriangle: `<svg ${ICON_ATTRS}><path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>`,
};
