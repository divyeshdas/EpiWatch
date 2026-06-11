// Inline icon set (lucide-style strokes). Static, developer-authored
// markup — safe to render with {@html}. Kept as plain strings so templates
// aren't drowned in SVG path data.

const ICON_ATTRS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';

export const ICONS: Record<string, string> = {
  brand: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="9"/><polyline points="7,12 9.5,12 11,8 13,16 14.5,12 17,12"/></svg>`,
  surveillance: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/></svg>`,
  truck: `<svg ${ICON_ATTRS}><path d="M10 17h4V5H2v12h2"/><path d="M14 9h4l3 3v5h-3"/><circle cx="6.5" cy="17.5" r="1.5"/><circle cx="17.5" cy="17.5" r="1.5"/></svg>`,
  globe: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><line x1="3" y1="12" x2="21" y2="12"/></svg>`,
  trend: `<svg ${ICON_ATTRS}><polyline points="3,17 9,11 13,15 21,7"/><polyline points="15,7 21,7 21,13"/></svg>`,
  activity: `<svg ${ICON_ATTRS}><polyline points="2,12 6,12 9,5 14,19 17,12 22,12"/></svg>`,
  bell: `<svg ${ICON_ATTRS}><path d="M6 8a6 6 0 0 1 12 0c0 6 2.5 8 2.5 8h-17S6 14 6 8z"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>`,
  database: `<svg ${ICON_ATTRS}><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></svg>`,
  file: `<svg ${ICON_ATTRS}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/></svg>`,
  book: `<svg ${ICON_ATTRS}><path d="M2 4h7a4 4 0 0 1 4 4v12a3 3 0 0 0-3-3H2z"/><path d="M22 4h-7a4 4 0 0 0-4 4v12a3 3 0 0 1 3-3h8z"/></svg>`,
  settings: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
  help: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 4.9.7c0 1.7-2.4 2-2.4 3.8"/><line x1="12" y1="17.5" x2="12" y2="17.5"/></svg>`,
  search: `<svg ${ICON_ATTRS}><circle cx="11" cy="11" r="7"/><line x1="20" y1="20" x2="16" y2="16"/></svg>`,
  share: `<svg ${ICON_ATTRS}><circle cx="6" cy="12" r="2.5"/><circle cx="17.5" cy="5.5" r="2.5"/><circle cx="17.5" cy="18.5" r="2.5"/><line x1="8.2" y1="10.8" x2="15.3" y2="6.7"/><line x1="8.2" y1="13.2" x2="15.3" y2="17.3"/></svg>`,
  download: `<svg ${ICON_ATTRS}><path d="M12 3v12"/><polyline points="7,10 12,15 17,10"/><path d="M4 20h16"/></svg>`,
  filter: `<svg ${ICON_ATTRS}><line x1="4" y1="6" x2="20" y2="6"/><circle cx="9" cy="6" r="1.8"/><line x1="4" y1="12" x2="20" y2="12"/><circle cx="15" cy="12" r="1.8"/><line x1="4" y1="18" x2="20" y2="18"/><circle cx="9" cy="18" r="1.8"/></svg>`,
  menu: `<svg ${ICON_ATTRS}><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>`,
  refresh: `<svg ${ICON_ATTRS}><path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21,3 21,9 15,9"/></svg>`,
  sun: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8 6 18M18 6l1.8-1.8"/></svg>`,
  moon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>`,
  arrowRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12,5 19,12 12,19"/></svg>`,
  panel: `<svg ${ICON_ATTRS}><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="15" y1="4" x2="15" y2="20"/></svg>`,
  x: `<svg ${ICON_ATTRS}><line x1="6" y1="6" x2="18" y2="18"/><line x1="6" y1="18" x2="18" y2="6"/></svg>`,
  clock: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="9"/><polyline points="12,7 12,12 15,14"/></svg>`,
  table: `<svg ${ICON_ATTRS}><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="9" y1="4" x2="9" y2="20"/></svg>`,
  map: `<svg ${ICON_ATTRS}><polygon points="3,6 9,3 15,6 21,3 21,18 15,21 9,18 3,21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>`,
  layers: `<svg ${ICON_ATTRS}><polygon points="12,2 22,8 12,14 2,8"/><polyline points="2,14 12,20 22,14"/></svg>`,
};
