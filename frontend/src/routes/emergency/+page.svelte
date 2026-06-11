<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { theme, toggleTheme } from '$lib/stores/theme';
  import 'leaflet/dist/leaflet.css';

  // ── Types ──────────────────────────────────────────────────────────────────

  type PatientCondition = 'STABLE' | 'SERIOUS' | 'CRITICAL' | 'CARDIAC';

  type Hospital = {
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

  type EmergencyCase = {
    id: number;
    latitude: number;
    longitude: number;
    patient_condition: string;
    status: string;
    created_at: string;
    assigned_hospital_id: number | null;
  };

  type RouteNode = { node_id: number; latitude: number; longitude: number };

  type FactorScore = {
    raw: number;
    penalty: number;
    weight: number;
    contribution: number;
    note: string;
  };

  type ScoredCandidate = {
    hospital_id: number;
    hospital_name: string;
    region: string | null;
    rank: number;
    total_score: number;
    travel_time_s: number;
    distance_m: number;
    path: RouteNode[];
    factors: Record<string, FactorScore>;
  };

  type FilteredHospital = { hospital_id: number; hospital_name: string; reason: string };

  type AssignmentResponse = {
    emergency_id: number;
    assigned_hospital_id: number | null;
    status: string;
    reason?: string;
    condition: string;
    candidates: ScoredCandidate[];
    filtered_out: FilteredHospital[];
  };

  type GraphBounds = { min_lat: number; max_lat: number; min_lon: number; max_lon: number };

  // ── Constants ──────────────────────────────────────────────────────────────

  const API = 'http://localhost:8000';

  const CONDITIONS: PatientCondition[] = ['STABLE', 'SERIOUS', 'CRITICAL', 'CARDIAC'];

  const CONDITION_LABELS: Record<PatientCondition, string> = {
    STABLE: 'Stable',
    SERIOUS: 'Serious',
    CRITICAL: 'Critical',
    CARDIAC: 'Cardiac',
  };

  const CONDITION_COLORS: Record<PatientCondition, string> = {
    STABLE: '#5f806b',
    SERIOUS: '#a8893f',
    CARDIAC: '#b96532',
    CRITICAL: '#c94a45',
  };

  // Order matches the breakdown the scorer returns (see scoring/scorer.py) —
  // each candidate's total_score is the sum of these weighted contributions.
  const FACTOR_ORDER = [
    'travel_time',
    'icu_availability',
    'bed_availability',
    'load_factor',
    'specialization',
    'surge',
  ];

  const FACTOR_LABELS: Record<string, string> = {
    travel_time: 'Travel time',
    icu_availability: 'ICU availability',
    bed_availability: 'Bed availability',
    load_factor: 'Hospital load',
    specialization: 'Specialization match',
    surge: 'Outbreak surge',
  };

  // Ordered "good factor" (teal/green) -> "penalty" (red).
  const FACTOR_COLORS: Record<string, string> = {
    travel_time: '#14b8a6',
    icu_availability: '#6fa37f',
    bed_availability: '#5f806b',
    load_factor: '#a8893f',
    specialization: '#b96532',
    surge: '#c94a45',
  };

  // Inline icon set (lucide-style strokes), same convention as the
  // surveillance page. Static, developer-authored markup — safe to render
  // with {@html}.
  const ICON_ATTRS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';
  const ICONS: Record<string, string> = {
    brand: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="9"/><polyline points="7,12 9.5,12 11,8 13,16 14.5,12 17,12"/></svg>`,
    surveillance: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/></svg>`,
    truck: `<svg ${ICON_ATTRS}><path d="M10 17h4V5H2v12h2"/><path d="M14 9h4l3 3v5h-3"/><circle cx="6.5" cy="17.5" r="1.5"/><circle cx="17.5" cy="17.5" r="1.5"/></svg>`,
    globe: `<svg ${ICON_ATTRS}><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><line x1="3" y1="12" x2="21" y2="12"/></svg>`,
    cross: `<svg ${ICON_ATTRS}><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>`,
    zap: `<svg ${ICON_ATTRS}><path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z"/></svg>`,
    bed: `<svg ${ICON_ATTRS}><path d="M2 4v16"/><path d="M2 8h18a2 2 0 0 1 2 2v10"/><path d="M2 17h20"/><path d="M6 8v9"/></svg>`,
    activity: `<svg ${ICON_ATTRS}><polyline points="2,12 6,12 9,5 14,19 17,12 22,12"/></svg>`,
    trend: `<svg ${ICON_ATTRS}><polyline points="3,17 9,11 13,15 21,5"/><polyline points="14,5 21,5 21,12"/></svg>`,
    alertTriangle: `<svg ${ICON_ATTRS}><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12" y2="17.01"/></svg>`,
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
    panel: `<svg ${ICON_ATTRS}><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="15" y1="4" x2="15" y2="20"/></svg>`,
    x: `<svg ${ICON_ATTRS}><line x1="6" y1="6" x2="18" y2="18"/><line x1="6" y1="18" x2="18" y2="6"/></svg>`,
  };

  // ── State ──────────────────────────────────────────────────────────────────

  let hospitals: Hospital[] = [];
  let emergencies: EmergencyCase[] = [];
  let graphBounds: GraphBounds | null = null;

  let loadingData = true;
  let loadError: string | null = null;
  let lastUpdated: Date | null = null;

  // Right dispatch panel — collapses to an off-canvas drawer below 1100px.
  let panelOpen = false;

  // The emergency the user is currently building/inspecting in the detail
  // panel. pendingLocation is set by clicking the map; activeCase exists
  // once it's been POSTed to /emergency; assignment exists once /assign
  // has run.
  let pendingLocation: { lat: number; lon: number } | null = null;
  let pendingCondition: PatientCondition = 'SERIOUS';
  let activeCase: EmergencyCase | null = null;
  let assignment: AssignmentResponse | null = null;
  let reporting = false;
  let assigning = false;
  let assignError: string | null = null;

  // Set true one tick after `assignment` arrives, so the factor-contribution
  // bars animate from 0 -> value instead of popping in at full width.
  let revealed = false;

  // Recent-emergencies feed pulse animation (mirrors the surveillance page's
  // newAlertIds pattern).
  let pulseIds = new Set<number>();

  // Topbar search — highlights a matching hospital on the map and in the table.
  let searchQuery = '';
  let highlightedHospitalId: number | null = null;

  let ws: WebSocket | null = null;
  let wsConnected = false;

  // Map (Leaflet — initialized client-side only, see onMount)
  let L: any = null;
  let mapEl: HTMLDivElement;
  let leafletMap: any = null;
  let tileLayer: any = null;
  let tileTheme: 'light' | 'dark' | null = null;
  let hospitalLayer: any = null;
  let emergencyMarker: any = null;
  let routeLine: any = null;
  let hospitalsFitted = false;
  let fittedAssignmentId: number | null = null;

  // ── Derived ────────────────────────────────────────────────────────────────

  $: globalStats = {
    hospitalsOnline: hospitals.length,
    bedsAvailable: hospitals.reduce((s, h) => s + h.available_beds, 0),
    icuAvailable: hospitals.reduce((s, h) => s + h.available_icu_beds, 0),
    avgLoadPct: hospitals.length
      ? (hospitals.reduce((s, h) => s + loadFactor(h), 0) / hospitals.length) * 100
      : 0,
    activeEmergencies: emergencies.filter(c => c.status === 'PENDING').length,
  };

  $: hospitalsById = new Map(hospitals.map(h => [h.id, h]));

  // ── Data loading ───────────────────────────────────────────────────────────

  async function loadHospitals() {
    const r = await fetch(`${API}/hospitals`);
    if (r.ok) hospitals = await r.json();
  }

  async function loadEmergencies() {
    const r = await fetch(`${API}/emergency`);
    if (r.ok) emergencies = await r.json();
  }

  async function loadGraphStats() {
    const r = await fetch(`${API}/graph/stats`);
    if (r.ok) {
      const stats = await r.json();
      graphBounds = stats.bounding_box;
    }
  }

  async function loadAll() {
    loadingData = true;
    loadError = null;
    try {
      await Promise.all([loadHospitals(), loadEmergencies(), loadGraphStats()]);
      lastUpdated = new Date();
    } catch (e) {
      loadError = 'Could not reach the dispatch API. Showing the last known data.';
    } finally {
      loadingData = false;
    }
  }

  // ── Emergency reporting flow ─────────────────────────────────────────────────

  async function reportEmergency() {
    if (!pendingLocation || reporting) return;
    reporting = true;
    assignError = null;
    try {
      const r = await fetch(`${API}/emergency`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          latitude: pendingLocation.lat,
          longitude: pendingLocation.lon,
          patient_condition: pendingCondition,
        }),
      });
      if (!r.ok) {
        assignError = 'Failed to report emergency.';
        return;
      }
      activeCase = await r.json();
      assignment = null;
    } finally {
      reporting = false;
    }
  }

  async function assignHospital() {
    if (!activeCase || assigning) return;
    assigning = true;
    assignError = null;
    revealed = false;
    try {
      const r = await fetch(`${API}/emergency/${activeCase.id}/assign`, { method: 'POST' });
      if (!r.ok) {
        assignError = 'Failed to compute assignment.';
        return;
      }
      const result: AssignmentResponse = await r.json();
      assignment = result;
      if (result.status === 'NO_CANDIDATES') {
        assignError = result.reason ?? 'No hospital could be assigned.';
      }
      await loadAll();
      await tick();
      requestAnimationFrame(() => { revealed = true; });
    } finally {
      assigning = false;
    }
  }

  function resetPending() {
    pendingLocation = null;
    activeCase = null;
    assignment = null;
    assignError = null;
    revealed = false;
    fittedAssignmentId = null;
  }

  function selectCase(c: EmergencyCase) {
    activeCase = c;
    pendingLocation = { lat: c.latitude, lon: c.longitude };
    panelOpen = true;
    pendingCondition = (CONDITIONS.includes(c.patient_condition as PatientCondition)
      ? c.patient_condition
      : 'SERIOUS') as PatientCondition;
    assignment = null;
    assignError = null;
    revealed = false;
  }

  // ── WebSocket (live updates) ─────────────────────────────────────────────────

  function pulse(id: number) {
    pulseIds.add(id);
    pulseIds = pulseIds;
    setTimeout(() => {
      pulseIds.delete(id);
      pulseIds = pulseIds;
    }, 2200);
  }

  function connectWs() {
    ws = new WebSocket('ws://localhost:8000/ws');
    ws.onopen = () => { wsConnected = true; };
    ws.onclose = () => {
      wsConnected = false;
      setTimeout(connectWs, 2000);
    };
    ws.onerror = () => ws?.close();
    ws.onmessage = async (msg: MessageEvent) => {
      const e = JSON.parse(msg.data);
      if (e.type === 'EmergencyReported') {
        await loadEmergencies();
        pulse(e.payload.case_id);
      } else if (e.type === 'AmbulanceAssigned') {
        await loadAll();
        pulse(e.payload.emergency_id);
      } else if (e.type === 'HospitalUpdated') {
        await loadHospitals();
      }
    };
  }

  // ── Formatting helpers ─────────────────────────────────────────────────────

  function loadFactor(h: Hospital): number {
    return h.total_beds > 0 ? h.current_load / h.total_beds : 0;
  }

  function loadColor(h: Hospital): string {
    const lf = loadFactor(h);
    if (lf >= 0.85) return '#c94a45';
    if (lf >= 0.6) return '#a8893f';
    return '#5f806b';
  }

  // Color for an availability bar (beds/ICU) — low remaining capacity reads
  // as severe, same risk vocabulary as hospital load.
  function occupancyColor(available: number, total: number): string {
    if (total <= 0) return '#78716c';
    const ratio = available / total;
    if (ratio <= 0.15) return '#c94a45';
    if (ratio <= 0.4) return '#a8893f';
    return '#5f806b';
  }

  function availabilityPct(available: number, total: number): number {
    return total > 0 ? (available / total) * 100 : 0;
  }

  function pct(n: number): string {
    return `${Math.round(n)}%`;
  }

  function fmtKm(m: number): string {
    return `${(m / 1000).toFixed(2)} km`;
  }

  function fmtMin(s: number): string {
    return `${Math.max(1, Math.round(s / 60))} min`;
  }

  function fmtScore(n: number): string {
    return n.toFixed(3);
  }

  function fmtCoord(n: number): string {
    return n.toFixed(4);
  }

  function timeAgo(iso: string): string {
    const diffMs = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  }

  function conditionColor(c: string): string {
    return CONDITION_COLORS[c as PatientCondition] ?? '#94a3b8';
  }

  function conditionLabel(c: string): string {
    return CONDITION_LABELS[c as PatientCondition] ?? c;
  }

  function factorLabel(name: string): string {
    return FACTOR_LABELS[name] ?? name;
  }

  function factorColor(name: string): string {
    return FACTOR_COLORS[name] ?? '#94a3b8';
  }

  // Width of a factor's segment within the stacked contribution bar, as a
  // percentage of the candidate's total_score (so the full bar always sums
  // to 100% when revealed).
  function factorWidthPct(c: ScoredCandidate, name: string): number {
    const f = c.factors[name];
    if (!f || c.total_score <= 0) return 0;
    return (f.contribution / c.total_score) * 100;
  }

  function hospitalName(id: number | null): string {
    if (id === null) return '—';
    return hospitalsById.get(id)?.name ?? `#${id}`;
  }

  function handleSearch(e: KeyboardEvent) {
    if (e.key !== 'Enter') return;
    const q = searchQuery.trim().toLowerCase();
    if (!q) {
      highlightedHospitalId = null;
      return;
    }
    const match = hospitals.find(h =>
      h.name.toLowerCase().includes(q) || (h.region ?? '').toLowerCase().includes(q)
    );
    highlightedHospitalId = match?.id ?? null;
  }

  // ── Map (Leaflet) ──────────────────────────────────────────────────────────

  function chartPalette() {
    const dark = $theme !== 'light';
    return {
      bg:     dark ? '#34302b' : '#e6dfd7',
      accent: dark ? '#14b8a6' : '#0f9d8e',
    };
  }

  // CARTO's free basemaps are OpenStreetMap data with light/dark styling, so
  // the map can follow the app's theme toggle while keeping OSM attribution.
  // "dark_all" reads as near-black against the dashboard's dark surfaces, so
  // dark mode uses Voyager — its lighter roads/labels stay legible while
  // still suiting a dark UI.
  const TILE_URLS = {
    light: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    dark: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
  };
  const TILE_ATTRIBUTION =
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors ' +
    '&copy; <a href="https://carto.com/attributions">CARTO</a>';

  function updateTileLayer() {
    if (!leafletMap || !L) return;
    const wanted = $theme === 'light' ? 'light' : 'dark';
    if (tileTheme === wanted) return;
    if (tileLayer) leafletMap.removeLayer(tileLayer);
    tileLayer = L.tileLayer(TILE_URLS[wanted], {
      maxZoom: 19,
      subdomains: 'abcd',
      attribution: TILE_ATTRIBUTION,
    }).addTo(leafletMap);
    tileLayer.bringToBack();
    tileTheme = wanted;
  }

  // Marker radius scales with bed count, same shape as the old ECharts symbol size.
  function hospitalRadius(h: Hospital, highlighted: boolean): number {
    const base = 6 + Math.sqrt(h.total_beds) * 0.45;
    return highlighted ? base * 1.4 : base;
  }

  function hospitalTooltipHtml(h: Hospital): string {
    return `<strong>${h.name}</strong><br/>` +
      `Region: ${h.region ?? '—'}<br/>` +
      `Beds: ${h.available_beds}/${h.total_beds} · ICU: ${h.available_icu_beds}/${h.total_icu_beds}<br/>` +
      `Load: ${pct(loadFactor(h) * 100)}`;
  }

  function renderHospitalMarkers() {
    if (!leafletMap || !L || !hospitalLayer) return;
    const pal = chartPalette();
    hospitalLayer.clearLayers();
    for (const h of hospitals) {
      const highlighted = h.id === assignment?.assigned_hospital_id || h.id === highlightedHospitalId;
      const marker = L.circleMarker([h.latitude, h.longitude], {
        radius: hospitalRadius(h, highlighted),
        color: highlighted ? pal.accent : pal.bg,
        weight: highlighted ? 3 : 1.5,
        fillColor: loadColor(h),
        fillOpacity: 0.9,
      });
      marker.bindTooltip(hospitalTooltipHtml(h), { direction: 'top', sticky: true, className: 'map-tooltip' });
      // Don't let a marker click also trigger the map's "report emergency here" handler.
      marker.on('click', (e: any) => L.DomEvent.stopPropagation(e));
      hospitalLayer.addLayer(marker);
    }

    if (!hospitalsFitted && hospitals.length) {
      leafletMap.fitBounds(L.latLngBounds(hospitals.map(h => [h.latitude, h.longitude])), { padding: [32, 32] });
      hospitalsFitted = true;
    }
  }

  function renderEmergencyMarker() {
    if (!leafletMap || !L) return;
    if (emergencyMarker) {
      leafletMap.removeLayer(emergencyMarker);
      emergencyMarker = null;
    }
    if (!pendingLocation) return;
    const icon = L.divIcon({
      className: 'emergency-marker',
      html: '<span class="emergency-marker-dot"></span><span class="emergency-marker-pulse"></span>',
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    });
    emergencyMarker = L.marker([pendingLocation.lat, pendingLocation.lon], {
      icon,
      interactive: false,
      keyboard: false,
    }).addTo(leafletMap);
  }

  // Catmull-Rom spline through the path nodes, purely for display: the
  // routing graph is a 4-connected grid (see backend/app/graph/ingest.py),
  // so the raw path is a sequence of right-angle jogs. Curving it makes the
  // line read as "a route" — it does NOT change the computed path/score, and
  // it still doesn't trace real streets (see comment below).
  function smoothPath(points: number[][], segmentsPerHop = 8): number[][] {
    if (points.length < 3) return points;
    const out: number[][] = [];
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[Math.max(i - 1, 0)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(i + 2, points.length - 1)];
      for (let s = 0; s < segmentsPerHop; s++) {
        const t = s / segmentsPerHop;
        const t2 = t * t;
        const t3 = t2 * t;
        out.push([
          0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
          0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
        ]);
      }
    }
    out.push(points[points.length - 1]);
    return out;
  }

  function renderRoute() {
    if (!leafletMap || !L) return;
    if (routeLine) {
      leafletMap.removeLayer(routeLine);
      routeLine = null;
    }
    const winner = assignment?.candidates?.[0];
    const assignedId = assignment?.assigned_hospital_id ?? null;
    if (!winner || winner.path.length < 2 || assignedId === null) return;

    // The path follows the synthetic road graph used for routing/scoring, not
    // real streets — it's drawn over real geography for orientation only.
    // The raw node-to-node hops are smoothed (smoothPath) for readability.
    const latlngs = smoothPath(winner.path.map(p => [p.latitude, p.longitude]));
    routeLine = L.polyline(latlngs, {
      color: chartPalette().accent,
      weight: 4,
      opacity: 0.85,
      dashArray: '1, 10',
      lineCap: 'round',
      className: 'route-line',
    }).addTo(leafletMap);

    if (fittedAssignmentId !== assignedId) {
      leafletMap.fitBounds(routeLine.getBounds(), { padding: [48, 48], maxZoom: 14 });
      fittedAssignmentId = assignedId;
    }
  }

  function renderMap() {
    if (!leafletMap || !L) return;
    updateTileLayer();
    renderHospitalMarkers();
    renderEmergencyMarker();
    renderRoute();
  }

  // ── Reactivity ────────────────────────────────────────────────────────────

  $: if (leafletMap && L) {
    hospitals; pendingLocation; assignment; highlightedHospitalId; $theme;
    renderMap();
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  onMount(() => {
    if (!browser) return;

    const resize = () => leafletMap?.invalidateSize();
    window.addEventListener('resize', resize);

    (async () => {
      const leafletModule: any = await import('leaflet');
      L = leafletModule.default ?? leafletModule;

      // Default view is Mumbai; refined to the graph bounding box (and then
      // the hospital bounds) once the data loads.
      leafletMap = L.map(mapEl, { zoomControl: true }).setView([19.076, 72.8777], 11);
      hospitalLayer = L.layerGroup().addTo(leafletMap);
      updateTileLayer();

      // Click anywhere on the map to report an emergency there — e.latlng
      // gives real coordinates directly, no pixel/axis conversion needed.
      leafletMap.on('click', (e: any) => {
        pendingLocation = { lat: e.latlng.lat, lon: e.latlng.lng };
        panelOpen = true;
        activeCase = null;
        assignment = null;
        assignError = null;
        revealed = false;
      });

      await loadAll();
      await tick();

      if (graphBounds) {
        const b = graphBounds;
        leafletMap.fitBounds([[b.min_lat, b.min_lon], [b.max_lat, b.max_lon]], { padding: [20, 20] });
      }
      leafletMap.invalidateSize();
      renderMap();
    })();

    connectWs();

    return () => window.removeEventListener('resize', resize);
  });

  onDestroy(() => {
    leafletMap?.remove();
    ws?.close();
  });
</script>

<div class="shell">

  <!-- ── Sidebar ───────────────────────────────────────────────────────────── -->
  <aside class="sidebar">
    <div class="sidebar-brand">
      <span class="brand-mark">{@html ICONS.brand}</span>
      <div>
        <div class="brand-name">EpiWatch</div>
        <div class="brand-section">Routing</div>
      </div>
    </div>

    <nav class="sidebar-nav">
      <a href="/surveillance" class="nav-item {$page.url.pathname === '/surveillance' ? 'active' : ''}">{@html ICONS.surveillance}<span>Overview</span></a>
      <a href="/emergency" class="nav-item {$page.url.pathname === '/emergency' ? 'active' : ''}">{@html ICONS.truck}<span>Emergency Response</span></a>
      <span class="nav-item inert">{@html ICONS.globe}<span>Global Map</span></span>
      <span class="nav-item inert">{@html ICONS.trend}<span>Trends</span></span>
      <span class="nav-item inert">{@html ICONS.activity}<span>Diseases</span></span>
      <span class="nav-item inert">{@html ICONS.bell}<span>Alerts</span></span>
      <span class="nav-item inert">{@html ICONS.database}<span>Data Explorer</span></span>
      <span class="nav-item inert">{@html ICONS.file}<span>Reports</span></span>
      <span class="nav-item inert">{@html ICONS.book}<span>Resources</span></span>
    </nav>

    <div class="sidebar-bottom">
      <span class="nav-item inert">{@html ICONS.settings}<span>Settings</span></span>
      <button class="nav-item theme-item" on:click={toggleTheme}>
        {@html $theme === 'light' ? ICONS.moon : ICONS.sun}
        <span>{$theme === 'light' ? 'Dark mode' : 'Light mode'}</span>
      </button>
      <span class="nav-item inert">{@html ICONS.help}<span>Help</span></span>
    </div>
  </aside>

  <!-- ── Main column ───────────────────────────────────────────────────────── -->
  <div class="main">

    <header class="topbar">
      <button class="icon-btn menu-btn" aria-label="Menu">{@html ICONS.menu}</button>
      <div class="search-box">
        {@html ICONS.search}
        <input
          type="text"
          placeholder="Search hospital or region…"
          bind:value={searchQuery}
          on:keydown={handleSearch}
        />
        <span class="kbd">↵</span>
      </div>
      <div class="topbar-right">
        <div class="data-updated">
          <span class="ws-dot {wsConnected ? 'connected' : ''}"></span>
          Data updated {lastUpdated ? timeAgo(lastUpdated.toISOString()) : '—'}
        </div>
        <button class="topbar-btn">{@html ICONS.share}<span>Share</span></button>
        <button class="topbar-btn">{@html ICONS.download}<span>Download</span></button>
        <button class="topbar-btn">{@html ICONS.filter}<span>Filters</span></button>
        <button
          class="icon-btn panel-toggle-btn"
          aria-label="Open dispatch panel"
          on:click={() => panelOpen = true}
        >{@html ICONS.panel}</button>
      </div>
    </header>

    <div class="content">
      <div class="content-main">

        <div class="tabs">
          <span class="tab active">Dispatch</span>
          <span class="tab inert">Hospitals</span>
          <span class="tab inert">History</span>
          <span class="tab inert">Routes</span>
          <span class="tab inert">Reports</span>
        </div>

        {#if loadError}
          <div class="error-banner">{@html ICONS.bell}{loadError}</div>
        {/if}

        <!-- Dispatch Map -->
        <section class="panel">
          <div class="panel-header">
            <h2>Dispatch Map</h2>
          </div>

          <div class="risk-legend">
            <span class="legend-caption">Hospital Load</span>
            <span class="legend-item"><span class="legend-dot" style="background: #5f806b"></span>Available</span>
            <span class="legend-item"><span class="legend-dot" style="background: #a8893f"></span>Busy</span>
            <span class="legend-item"><span class="legend-dot" style="background: #c94a45"></span>Critical</span>
          </div>

          <div class="map-wrap">
            <div bind:this={mapEl} class="map-canvas"></div>
            {#if loadingData}<div class="loading-bar"></div>{/if}
            {#if !pendingLocation}
              <div class="map-hint">Click the map to report an emergency location</div>
            {/if}
          </div>

          <div class="stat-row">
            <div class="stat-card">
              {@html ICONS.cross}
              <div>
                <div class="stat-label">Hospitals Online</div>
                <div class="stat-value">{globalStats.hospitalsOnline}</div>
                <div class="stat-sub">across Mumbai</div>
              </div>
            </div>
            <div class="stat-card">
              {@html ICONS.bed}
              <div>
                <div class="stat-label">Beds Available</div>
                <div class="stat-value">{globalStats.bedsAvailable}</div>
                <div class="stat-sub">general ward capacity</div>
              </div>
            </div>
            <div class="stat-card">
              {@html ICONS.activity}
              <div>
                <div class="stat-label">ICU Beds Available</div>
                <div class="stat-value">{globalStats.icuAvailable}</div>
                <div class="stat-sub">across all hospitals</div>
              </div>
            </div>
            <div class="stat-card">
              {@html ICONS.trend}
              <div>
                <div class="stat-label">Avg. Hospital Load</div>
                <div class="stat-value {globalStats.avgLoadPct >= 70 ? 'stat-down' : 'stat-up'}">{pct(globalStats.avgLoadPct)}</div>
                <div class="stat-sub">network-wide</div>
              </div>
            </div>
            <div class="stat-card">
              {@html ICONS.alertTriangle}
              <div>
                <div class="stat-label">Active Emergencies</div>
                <div class="stat-value">{globalStats.activeEmergencies}</div>
                <div class="stat-sub">pending dispatch</div>
              </div>
            </div>
          </div>
        </section>

        <!-- Hospital Network + Recent Emergencies -->
        <div class="panel-row">
          <section class="panel hospitals-panel">
            <div class="panel-header">
              <h2>Hospital Network</h2>
            </div>
            <div class="hospital-table">
              <div class="hospital-table-head">
                <span>Hospital</span><span>Region</span><span>Beds</span><span>ICU</span><span>Load</span>
              </div>
              {#each hospitals as h (h.id)}
                <div class="hospital-row {h.id === assignment?.assigned_hospital_id ? 'active' : ''}">
                  <span class="hospital-name">
                    {h.name}
                    {#if h.specializations.length}
                      <span class="hospital-spec">{h.specializations.join(', ')}</span>
                    {/if}
                  </span>
                  <span class="hospital-region">{h.region ?? '—'}</span>
                  <span class="capacity-cell">
                    <span class="capacity-text">{h.available_beds}/{h.total_beds}</span>
                    <span class="capacity-bar-wrap">
                      <span class="capacity-bar" style="width: {availabilityPct(h.available_beds, h.total_beds)}%; background: {occupancyColor(h.available_beds, h.total_beds)}"></span>
                    </span>
                  </span>
                  <span class="capacity-cell">
                    {#if h.total_icu_beds > 0}
                      <span class="capacity-text">{h.available_icu_beds}/{h.total_icu_beds}</span>
                      <span class="capacity-bar-wrap">
                        <span class="capacity-bar" style="width: {availabilityPct(h.available_icu_beds, h.total_icu_beds)}%; background: {occupancyColor(h.available_icu_beds, h.total_icu_beds)}"></span>
                      </span>
                    {:else}
                      <span class="capacity-text">—</span>
                    {/if}
                  </span>
                  <span class="load-cell" style="color: {loadColor(h)}">{pct(loadFactor(h) * 100)}</span>
                </div>
              {/each}
              {#if hospitals.length === 0}
                <div class="empty-note">Loading hospital network…</div>
              {/if}
            </div>
          </section>

          <section class="panel emergencies-panel">
            <div class="panel-header">
              <h2>Recent Emergencies</h2>
            </div>
            <div class="emergency-list">
              {#each emergencies.slice(0, 8) as c (c.id)}
                <button
                  class="emergency-row {pulseIds.has(c.id) ? 'row-pulse' : ''}"
                  style="--sev: {conditionColor(c.patient_condition)}"
                  on:click={() => selectCase(c)}
                >
                  <span class="emergency-top">
                    <span class="emergency-cond" style="color: {conditionColor(c.patient_condition)}">{conditionLabel(c.patient_condition)}</span>
                    <span class="emergency-time">{timeAgo(c.created_at)}</span>
                  </span>
                  <span class="emergency-detail">
                    {c.status === 'ASSIGNED' ? `→ ${hospitalName(c.assigned_hospital_id)}` : 'Awaiting dispatch'}
                  </span>
                </button>
              {/each}
              {#if emergencies.length === 0}
                <div class="empty-note">No emergencies reported yet.</div>
              {/if}
            </div>
          </section>
        </div>

      </div>

      <!-- ── Dispatch detail panel ───────────────────────────────────────── -->
      <div
        class="drawer-backdrop {panelOpen ? 'show' : ''}"
        role="presentation"
        aria-hidden="true"
        on:click={() => panelOpen = false}
      ></div>
      <aside class="detail-panel {panelOpen ? 'drawer-open' : ''}">
        <button class="icon-btn drawer-close" aria-label="Close panel" on:click={() => panelOpen = false}>
          {@html ICONS.x}
        </button>
        {#if !pendingLocation}
          <div class="detail-header"><h2>New Emergency</h2></div>
          <div class="empty-note">Click a location on the map to report an emergency.</div>
          <div class="detail-section">
            <div class="detail-section-title">Patient Condition</div>
            <div class="condition-picker">
              {#each CONDITIONS as c}
                <button
                  class="condition-btn {pendingCondition === c ? 'active' : ''}"
                  style="--cond: {CONDITION_COLORS[c]}"
                  on:click={() => pendingCondition = c}
                >{CONDITION_LABELS[c]}</button>
              {/each}
            </div>
          </div>

        {:else if !activeCase}
          <div class="detail-header"><h2>New Emergency</h2></div>
          <div class="detail-grid">
            <div class="detail-cell">
              <div class="detail-label">Latitude</div>
              <div class="detail-value">{fmtCoord(pendingLocation.lat)}</div>
            </div>
            <div class="detail-cell">
              <div class="detail-label">Longitude</div>
              <div class="detail-value">{fmtCoord(pendingLocation.lon)}</div>
            </div>
          </div>
          <div class="detail-section">
            <div class="detail-section-title">Patient Condition</div>
            <div class="condition-picker">
              {#each CONDITIONS as c}
                <button
                  class="condition-btn {pendingCondition === c ? 'active' : ''}"
                  style="--cond: {CONDITION_COLORS[c]}"
                  on:click={() => pendingCondition = c}
                >{CONDITION_LABELS[c]}</button>
              {/each}
            </div>
          </div>
          {#if assignError}<div class="error-msg">{assignError}</div>{/if}
          <button class="primary-btn" on:click={reportEmergency} disabled={reporting}>
            {@html ICONS.zap}{reporting ? 'Reporting…' : 'Report Emergency'}
          </button>
          <button class="text-btn" on:click={resetPending}>Cancel</button>

        {:else if !assignment}
          <div class="detail-header"><h2>Emergency #{activeCase.id}</h2></div>
          <div class="risk-score-block">
            <div class="risk-label">Patient Condition</div>
            <div class="risk-level" style="color: {conditionColor(activeCase.patient_condition)}; font-size: 1.3rem; margin-top: 6px;">
              {conditionLabel(activeCase.patient_condition)}
            </div>
          </div>
          <div class="detail-grid">
            <div class="detail-cell">
              <div class="detail-label">Latitude</div>
              <div class="detail-value">{fmtCoord(activeCase.latitude)}</div>
            </div>
            <div class="detail-cell">
              <div class="detail-label">Longitude</div>
              <div class="detail-value">{fmtCoord(activeCase.longitude)}</div>
            </div>
            <div class="detail-cell">
              <div class="detail-label">Status</div>
              <div class="detail-value">{activeCase.status}</div>
            </div>
            <div class="detail-cell">
              <div class="detail-label">Reported</div>
              <div class="detail-value">{timeAgo(activeCase.created_at)}</div>
            </div>
          </div>
          {#if assignError}<div class="error-msg">{assignError}</div>{/if}
          <button class="primary-btn" on:click={assignHospital} disabled={assigning}>
            {@html ICONS.zap}{assigning ? 'Computing route…' : 'Find Hospital'}
          </button>
          <button class="text-btn" on:click={resetPending}>{@html ICONS.refresh}New emergency</button>

        {:else}
          <div class="detail-header"><h2>Emergency #{activeCase.id}</h2></div>

          {#if assignment.assigned_hospital_id !== null}
            {@const winner = assignment.candidates[0]}
            <div class="risk-score-block">
              <div class="risk-label">Assigned Hospital</div>
              <div class="winner-name">{winner.hospital_name}</div>
              <div class="risk-level" style="color: {conditionColor(activeCase.patient_condition)}">
                {conditionLabel(activeCase.patient_condition)} · score {fmtScore(winner.total_score)}
              </div>
            </div>
            <div class="detail-grid">
              <div class="detail-cell">
                <div class="detail-label">ETA</div>
                <div class="detail-value">{fmtMin(winner.travel_time_s)}</div>
              </div>
              <div class="detail-cell">
                <div class="detail-label">Distance</div>
                <div class="detail-value">{fmtKm(winner.distance_m)}</div>
              </div>
            </div>
          {:else}
            <div class="empty-note">{assignment.reason ?? 'No hospital could be assigned.'}</div>
          {/if}

          <div class="detail-section">
            <div class="detail-section-title">Candidate Ranking</div>
            <div class="factor-legend">
              {#each FACTOR_ORDER as f}
                <span class="legend-item"><span class="legend-dot" style="background: {factorColor(f)}"></span>{factorLabel(f)}</span>
              {/each}
            </div>
            <div class="candidate-list">
              {#each assignment.candidates as c (c.hospital_id)}
                <div class="candidate-row {c.hospital_id === assignment.assigned_hospital_id ? 'winner' : ''}">
                  <div class="candidate-top">
                    <span class="candidate-rank">#{c.rank}</span>
                    <span class="candidate-name">{c.hospital_name}</span>
                    <span class="candidate-score">{fmtScore(c.total_score)}</span>
                  </div>
                  <div class="candidate-meta">{fmtMin(c.travel_time_s)} · {fmtKm(c.distance_m)}{c.region ? ` · ${c.region}` : ''}</div>
                  <div class="factor-bar">
                    {#each FACTOR_ORDER as f}
                      {#if c.factors[f]}
                        <div
                          class="factor-seg"
                          style="width: {revealed ? factorWidthPct(c, f) : 0}%; background: {factorColor(f)}"
                          title="{factorLabel(f)}: {fmtScore(c.factors[f].contribution)}"
                        ></div>
                      {/if}
                    {/each}
                  </div>
                  {#if c.factors.surge && c.factors.surge.contribution > 0}
                    <div class="surge-note">{@html ICONS.alertTriangle}{c.factors.surge.note}</div>
                  {/if}
                </div>
              {/each}
            </div>
          </div>

          {#if assignment.filtered_out.length}
            <div class="detail-section">
              <div class="detail-section-title">Filtered Out</div>
              <div class="filtered-list">
                {#each assignment.filtered_out as f (f.hospital_id)}
                  <div class="filtered-row">
                    <span class="filtered-name">{f.hospital_name}</span>
                    <span class="filtered-reason">{f.reason}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <button class="text-btn" on:click={resetPending}>{@html ICONS.refresh}Report new emergency</button>
        {/if}
      </aside>
    </div>
  </div>
</div>

<style>
  /* Theme variables, fonts, and global resets live in
     src/lib/styles/theme.css (imported once via the root layout). */

  /* ── Shell layout ─────────────────────────────────────────────────────── */

  .shell {
    display: flex;
    min-height: 100vh;
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.5;
    color: var(--text);
  }

  /* ── Sidebar ──────────────────────────────────────────────────────────── */

  .sidebar {
    width: var(--sidebar-w);
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 16px 12px;
    background: var(--bg-panel);
    border-right: 1px solid var(--border);
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
  }
  .sidebar::-webkit-scrollbar { width: 6px; }
  .sidebar::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .sidebar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 10px 16px;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--border-soft);
  }
  .brand-mark {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 7px;
    background: var(--accent-soft);
    color: var(--accent);
    flex-shrink: 0;
  }
  .brand-mark :global(svg) { width: 18px; height: 18px; }
  .brand-name { font-weight: 600; font-size: 0.92rem; color: var(--text); }
  .brand-section {
    font-size: 0.66rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 2px;
  }

  .sidebar-nav { display: flex; flex-direction: column; gap: 1px; flex: 1; }
  .sidebar-bottom {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding-top: 8px;
    margin-top: 8px;
    border-top: 1px solid var(--border-soft);
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 0.83rem;
    font-family: var(--sans);
    color: var(--text-muted);
    text-decoration: none;
    background: transparent;
    border: none;
    width: 100%;
    text-align: left;
    cursor: pointer;
    position: relative;
  }
  .nav-item :global(svg) { width: 17px; height: 17px; flex-shrink: 0; }
  a.nav-item:hover,
  .theme-item:hover { background: var(--bg-hover); color: var(--text); }
  .nav-item.active {
    color: var(--text);
    background: var(--accent-soft);
    font-weight: 500;
  }
  .nav-item.active::before {
    content: '';
    position: absolute;
    left: -12px;
    top: 8px;
    bottom: 8px;
    width: 3px;
    border-radius: 0 2px 2px 0;
    background: var(--accent);
  }
  .nav-item.inert { cursor: default; opacity: 0.5; }

  /* ── Main column ──────────────────────────────────────────────────────── */

  .main { flex: 1; min-width: 0; display: flex; flex-direction: column; }

  .topbar {
    display: flex;
    align-items: center;
    gap: 14px;
    height: var(--topbar-h);
    padding: 0 24px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-panel);
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    flex-shrink: 0;
  }
  .icon-btn:hover { background: var(--bg-hover); color: var(--text); }
  .icon-btn :global(svg) { width: 16px; height: 16px; }

  .search-box {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    max-width: 440px;
    padding: 7px 12px;
    border-radius: 6px;
    background: var(--bg-sunken);
    border: 1px solid var(--border);
    color: var(--text-muted);
  }
  .search-box :global(svg) { width: 15px; height: 15px; flex-shrink: 0; }
  .search-box input {
    flex: 1;
    border: none;
    background: transparent;
    outline: none;
    font-family: var(--sans);
    font-size: 0.83rem;
    color: var(--text);
  }
  .search-box input::placeholder { color: var(--text-faint); }
  .kbd {
    font-family: var(--mono);
    font-size: 0.68rem;
    color: var(--text-faint);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 5px;
    flex-shrink: 0;
  }

  .topbar-right { display: flex; align-items: center; gap: 10px; margin-left: auto; }
  .data-updated {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 0.75rem;
    color: var(--text-muted);
    white-space: nowrap;
  }
  .ws-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-faint);
    flex-shrink: 0;
  }
  .ws-dot.connected {
    background: var(--success);
    animation: breathe 2.4s ease-in-out infinite;
  }
  @keyframes breathe {
    0%, 100% { box-shadow: 0 0 0 0 rgba(111, 163, 127, 0.5); }
    50% { box-shadow: 0 0 0 4px rgba(111, 163, 127, 0); }
  }
  .topbar-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-muted);
    font-family: var(--sans);
    font-size: 0.8rem;
    cursor: pointer;
    white-space: nowrap;
  }
  .topbar-btn:hover { background: var(--bg-hover); color: var(--text); }
  .topbar-btn :global(svg) { width: 14px; height: 14px; }

  /* ── Content layout ───────────────────────────────────────────────────── */

  .content {
    display: flex;
    align-items: flex-start;
    gap: var(--page-pad);
    padding: var(--page-pad);
    flex: 1;
  }
  .content-main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .tabs {
    display: flex;
    gap: 4px;
    border-bottom: 1px solid var(--border);
  }
  .tab {
    padding: 8px 14px;
    font-size: 0.83rem;
    color: var(--text-muted);
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }
  .tab.active { color: var(--text); border-bottom-color: var(--accent); font-weight: 500; }
  .tab.inert { opacity: 0.45; }

  .error-banner {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--danger);
    background: rgba(220, 79, 69, 0.1);
    color: var(--danger);
    font-size: 0.83rem;
  }
  .error-banner :global(svg) { width: 15px; height: 15px; flex-shrink: 0; }

  /* ── Panels ───────────────────────────────────────────────────────────── */

  .panel {
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px;
  }
  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;
  }
  .panel-header h2 {
    font-size: 1.125rem;
    font-weight: 600;
    margin: 0;
    letter-spacing: -0.01em;
  }

  .risk-legend {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-bottom: 12px;
  }
  .legend-caption {
    font-weight: 600;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.6875rem;
  }
  .legend-item { display: flex; align-items: center; gap: 6px; }
  .legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

  .map-wrap {
    position: relative;
    height: 440px;
    border-radius: var(--radius-sm);
    overflow: hidden;
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
  }
  .map-canvas { width: 100%; height: 100%; }
  .map-canvas :global(.leaflet-container) {
    background: var(--bg-sunken);
    font-family: var(--sans);
  }
  .map-canvas :global(.leaflet-control-attribution) {
    background: var(--bg-panel);
    color: var(--text-faint);
    font-size: 0.6875rem;
  }
  .map-canvas :global(.leaflet-control-attribution a) { color: var(--text-muted); }
  .map-canvas :global(.leaflet-bar),
  .map-canvas :global(.leaflet-bar a) {
    background: var(--bg-panel);
    border-color: var(--border) !important;
    color: var(--text);
  }
  .map-canvas :global(.leaflet-bar a:hover) { background: var(--bg-hover); }
  .map-canvas :global(.map-tooltip) {
    background: var(--card);
    border: 1px solid var(--border);
    color: var(--text);
    font-size: 0.75rem;
    line-height: 1.5;
    border-radius: var(--radius-sm);
    box-shadow: none;
  }
  .map-canvas :global(.map-tooltip::before) { display: none; }

  /* Pulsing marker for the reported emergency location. */
  .map-canvas :global(.emergency-marker) { position: relative; }
  .map-canvas :global(.emergency-marker-dot),
  .map-canvas :global(.emergency-marker-pulse) {
    position: absolute;
    left: 2px; top: 2px;
    width: 12px; height: 12px;
    border-radius: 50%;
  }
  .map-canvas :global(.emergency-marker-dot) {
    background: var(--risk-severe);
    border: 2px solid var(--bg-sunken);
  }
  .map-canvas :global(.emergency-marker-pulse) {
    border: 2px solid var(--risk-severe);
    animation: emergencyPulse 1.8s ease-out infinite;
  }
  @keyframes emergencyPulse {
    0% { transform: scale(1); opacity: 0.8; }
    100% { transform: scale(2.6); opacity: 0; }
  }

  /* Flowing dashes along the assigned route. */
  .map-canvas :global(.route-line) {
    animation: routeFlow 0.6s linear infinite;
  }
  @keyframes routeFlow {
    to { stroke-dashoffset: -22; }
  }

  .loading-bar {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--border);
    overflow: hidden;
    z-index: 1000;
  }
  .loading-bar::after {
    content: '';
    position: absolute;
    top: 0; bottom: 0;
    left: -40%;
    width: 40%;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    animation: sweep 1.2s ease-in-out infinite;
  }
  @keyframes sweep {
    0% { left: -40%; }
    100% { left: 100%; }
  }
  .map-hint {
    position: absolute;
    bottom: 14px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 0.78rem;
    color: var(--text-muted);
    pointer-events: none;
    z-index: 1000;
  }

  .stat-row {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin-top: 16px;
  }
  .stat-card {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px;
    border-radius: var(--radius-sm);
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    transition: border-color var(--ease-hover), transform var(--ease-hover);
  }
  .stat-card:hover { border-color: var(--border); transform: translateY(-2px); }
  .stat-card :global(svg) {
    width: 17px;
    height: 17px;
    color: var(--accent);
    flex-shrink: 0;
    margin-top: 2px;
  }
  .stat-label {
    font-size: 0.6875rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .stat-value {
    font-family: var(--mono);
    font-size: 1.35rem;
    font-weight: 600;
    margin-top: 3px;
    color: var(--text);
  }
  .stat-sub { font-size: 0.7rem; color: var(--text-faint); margin-top: 2px; }
  .stat-up { color: var(--success); }
  .stat-down { color: var(--danger); }

  /* ── Hospital network + emergencies row ──────────────────────────────── */

  .panel-row {
    display: flex;
    gap: 16px;
    align-items: stretch;
  }
  .hospitals-panel { flex: 1.7; min-width: 0; display: flex; flex-direction: column; }
  .emergencies-panel { flex: 1; min-width: 0; display: flex; flex-direction: column; }

  .empty-note { font-size: 0.8rem; color: var(--text-faint); padding: 16px 8px; text-align: center; }

  /* ── Hospital table ───────────────────────────────────────────────────── */

  .hospital-table { display: flex; flex-direction: column; gap: 2px; }
  .hospital-table-head,
  .hospital-row {
    display: grid;
    grid-template-columns: 1.8fr 0.9fr 1fr 1fr 0.6fr;
    align-items: center;
    gap: 10px;
  }
  .hospital-table-head {
    font-size: 0.6rem;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0 8px 6px;
  }
  .hospital-table-head span:not(:first-child) { text-align: right; }
  .hospital-row {
    border-radius: 6px;
    padding: 8px;
    transition: background 0.15s ease;
  }
  .hospital-row.active { background: var(--accent-soft); }
  .hospital-name { font-size: 0.83rem; color: var(--text); display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .hospital-spec { font-size: 0.68rem; color: var(--text-faint); text-transform: capitalize; }
  .hospital-region { font-size: 0.78rem; color: var(--text-muted); text-align: right; }
  .capacity-cell { display: flex; flex-direction: column; gap: 4px; align-items: flex-end; }
  .capacity-text { font-family: var(--mono); font-size: 0.76rem; color: var(--text); }
  .capacity-bar-wrap { width: 100%; height: 4px; border-radius: 2px; background: var(--border); overflow: hidden; }
  .capacity-bar { display: block; height: 100%; border-radius: 2px; transition: width 0.4s ease; }
  .load-cell { font-family: var(--mono); font-size: 0.83rem; font-weight: 600; text-align: right; }

  /* ── Recent emergencies ───────────────────────────────────────────────── */

  .emergency-list { display: flex; flex-direction: column; gap: 6px; }
  .emergency-row {
    display: flex;
    flex-direction: column;
    gap: 4px;
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    border-left: 3px solid var(--sev, var(--border));
    border-radius: 6px;
    padding: 8px 10px;
    text-align: left;
    cursor: pointer;
    font-family: var(--sans);
    width: 100%;
  }
  .emergency-row:hover { background: var(--bg-hover); }
  .emergency-top { display: flex; justify-content: space-between; align-items: center; }
  .emergency-cond { font-size: 0.74rem; font-weight: 700; letter-spacing: 0.03em; }
  .emergency-time { font-size: 0.66rem; color: var(--text-faint); font-family: var(--mono); }
  .emergency-detail { font-size: 0.78rem; color: var(--text-muted); }

  .row-pulse { animation: rowFade 0.4s ease-out, rowPulse 0.7s ease-out 2; }
  @keyframes rowFade {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes rowPulse {
    0% { box-shadow: 0 0 0 0 var(--sev); }
    70% { box-shadow: 0 0 0 6px transparent; }
    100% { box-shadow: 0 0 0 0 transparent; }
  }

  /* ── Detail panel ─────────────────────────────────────────────────────── */

  /* Drawer controls — hidden on desktop, shown below 1100px (see media query). */
  .panel-toggle-btn { display: none; }
  .drawer-close { display: none; }
  .drawer-backdrop { display: none; }

  .detail-panel {
    width: var(--panel-w);
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px;
    position: sticky;
    top: calc(var(--topbar-h) + 8px);
    max-height: calc(100vh - var(--topbar-h) - 16px);
    overflow-y: auto;
  }
  .detail-panel::-webkit-scrollbar { width: 6px; }
  .detail-panel::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .detail-header h2 { font-size: 1.25rem; font-weight: 600; margin: 0; }

  .risk-score-block {
    text-align: center;
    padding: 16px;
    border-radius: var(--radius-sm);
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
  }
  .risk-label { font-size: 0.6875rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; }
  .risk-level { font-size: 0.83rem; font-weight: 600; margin-top: 4px; }
  .winner-name { font-family: var(--mono); font-size: 1.25rem; font-weight: 700; color: var(--text); margin-top: 6px; }

  .detail-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .detail-cell {
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm);
    padding: 10px;
  }
  .detail-label { font-size: 0.6875rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; }
  .detail-value { font-family: var(--mono); font-size: 1.05rem; font-weight: 600; margin-top: 4px; color: var(--text); }

  .detail-section { padding-top: 14px; border-top: 1px solid var(--border-soft); }
  .detail-section-title {
    font-size: 0.6875rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
  }

  /* ── Condition picker ─────────────────────────────────────────────────── */

  .condition-picker {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .condition-btn {
    padding: 8px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--bg-sunken);
    color: var(--text-muted);
    font-family: var(--sans);
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .condition-btn:hover { border-color: var(--cond); color: var(--text); }
  .condition-btn.active {
    border-color: var(--cond);
    color: var(--cond);
    background: color-mix(in srgb, var(--cond) 12%, transparent);
    font-weight: 600;
  }

  /* ── Buttons / messages ───────────────────────────────────────────────── */

  .primary-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 10px;
    border-radius: 6px;
    border: 1px solid var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
    font-family: var(--sans);
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
  }
  .primary-btn:hover { background: var(--accent); color: #fff; }
  .primary-btn:disabled { opacity: 0.6; cursor: default; background: var(--accent-soft); color: var(--accent); }
  .primary-btn :global(svg) { width: 15px; height: 15px; }

  .text-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    border: none;
    background: transparent;
    color: var(--accent);
    font-family: var(--sans);
    font-size: 0.78rem;
    cursor: pointer;
    padding: 6px;
  }
  .text-btn :global(svg) { width: 13px; height: 13px; }

  .error-msg {
    font-size: 0.78rem;
    color: var(--danger);
    background: rgba(220, 79, 69, 0.1);
    border: 1px solid rgba(220, 79, 69, 0.25);
    border-radius: var(--radius-sm);
    padding: 8px 10px;
  }

  /* ── Candidate ranking ────────────────────────────────────────────────── */

  .factor-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 0.68rem;
    color: var(--text-muted);
    margin-bottom: 10px;
  }

  .candidate-list { display: flex; flex-direction: column; gap: 8px; }
  .candidate-row {
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    border-radius: 6px;
    padding: 9px 10px;
  }
  .candidate-row.winner { background: var(--accent-soft); border-color: var(--accent); }
  .candidate-top { display: flex; align-items: center; gap: 8px; }
  .candidate-rank { font-family: var(--mono); font-size: 0.7rem; color: var(--text-faint); }
  .candidate-name { flex: 1; font-size: 0.83rem; font-weight: 500; color: var(--text); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .candidate-score { font-family: var(--mono); font-size: 0.83rem; font-weight: 600; color: var(--text); }
  .candidate-meta { font-size: 0.7rem; color: var(--text-faint); margin-top: 2px; }

  .factor-bar {
    display: flex;
    height: 6px;
    border-radius: 3px;
    overflow: hidden;
    background: var(--border);
    margin-top: 8px;
  }
  .factor-seg { height: 100%; transition: width 0.6s ease; }

  .surge-note {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
    font-size: 0.7rem;
    color: var(--risk-severe);
  }
  .surge-note :global(svg) { width: 13px; height: 13px; flex-shrink: 0; }

  /* ── Filtered out list ────────────────────────────────────────────────── */

  .filtered-list { display: flex; flex-direction: column; gap: 6px; }
  .filtered-row {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    padding: 7px 8px;
    border-radius: 6px;
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    font-size: 0.76rem;
  }
  .filtered-name { color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .filtered-reason { color: var(--text-faint); text-align: right; flex-shrink: 0; }

  /* ── Responsive ───────────────────────────────────────────────────────── */

  @media (max-width: 1280px) {
    .stat-row { grid-template-columns: repeat(3, 1fr); }
    .panel-row { flex-direction: column; }
  }
  @media (max-width: 1100px) {
    .content { flex-direction: column; }

    .panel-toggle-btn { display: flex; }
    .drawer-close {
      display: flex;
      position: absolute;
      top: 12px;
      right: 12px;
      z-index: 1;
    }
    .drawer-backdrop {
      display: block;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.4);
      opacity: 0;
      pointer-events: none;
      transition: opacity var(--ease-drawer);
      z-index: 55;
    }
    .drawer-backdrop.show { opacity: 1; pointer-events: auto; }

    .detail-panel {
      position: fixed;
      top: 0;
      right: 0;
      width: min(var(--panel-w), 100%);
      height: 100vh;
      max-height: 100vh;
      transform: translateX(100%);
      transition: transform var(--ease-drawer);
      z-index: 60;
      box-shadow: -8px 0 24px rgba(0, 0, 0, 0.3);
      border-radius: 0;
    }
    .detail-panel.drawer-open { transform: translateX(0); }
  }
  @media (max-width: 720px) {
    .sidebar { display: none; }
    .stat-row { grid-template-columns: repeat(2, 1fr); }
    .topbar-btn span { display: none; }
    .hospital-table-head, .hospital-row { grid-template-columns: 1.6fr 1fr 1fr 1fr; }
    .hospital-region { display: none; }
    .hospital-table-head span:nth-child(2) { display: none; }
  }
</style>
