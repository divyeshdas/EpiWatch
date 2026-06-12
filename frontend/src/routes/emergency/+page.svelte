<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { theme } from '$lib/stores/theme';
  import Ticker from '$lib/components/Ticker.svelte';
  import TopNav from '$lib/components/TopNav.svelte';
  import TopTabs from '$lib/components/TopTabs.svelte';
  import { downloadCsv } from '$lib/csv';
  import { ICONS } from '$lib/icons';
  import { API_BASE, WS_BASE } from '$lib/api';
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

  const API = API_BASE;

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
  let searchFocused = false;
  let debouncedQuery = '';
  let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  // Topbar filters popover — filters the Hospital Network table (and its
  // CSV export) by load and specialization.
  let filtersOpen = false;
  let loadFilter: 'all' | 'available' | 'busy' | 'critical' = 'all';
  let specializationFilter = 'all';

  // Topbar share — copies the current view (highlighted hospital + filters)
  // as a URL; restored by the param-read block below on load.
  let shareCopied = false;
  let shareCopyTimer: ReturnType<typeof setTimeout> | null = null;
  let appliedShareParams = false;

  let ws: WebSocket | null = null;
  let wsConnected = false;

  // Map (Leaflet — initialized client-side only, see onMount)
  let L: any = null;
  let mapEl: HTMLDivElement;
  let leafletMap: any = null;
  let hospitalLayer: any = null;
  let emergencyMarker: any = null;
  let routeLine: any = null;
  let routeSource: 'osrm' | 'synthetic-fallback' | null = null;
  let showFallbackNote = false;
  let fallbackNoteTimer: ReturnType<typeof setTimeout> | null = null;
  let osrmRouteCoords: number[][] | null = null;
  let osrmRouteFor: number | null = null;
  let osrmRequestId = 0;
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

  // ── Topbar search / filters / share ──────────────────────────────────────

  $: {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    const q = searchQuery;
    searchDebounceTimer = setTimeout(() => { debouncedQuery = q; }, 200);
  }

  type HospitalMatch = { id: number; label: string; sub: string };

  $: searchMatches = ((): HospitalMatch[] => {
    const q = debouncedQuery.trim().toLowerCase();
    if (!q) return [];
    return hospitals
      .filter(h => h.name.toLowerCase().includes(q) || (h.region ?? '').toLowerCase().includes(q))
      .slice(0, 8)
      .map(h => ({ id: h.id, label: h.name, sub: h.region ?? '—' }));
  })();

  $: searchOpen = searchFocused && searchQuery.trim().length > 0;

  $: specializations = Array.from(new Set(hospitals.flatMap(h => h.specializations))).sort();

  function loadBucket(h: Hospital): 'available' | 'busy' | 'critical' {
    const lf = loadFactor(h);
    if (lf >= 0.85) return 'critical';
    if (lf >= 0.6) return 'busy';
    return 'available';
  }

  $: filteredHospitals = hospitals.filter(h => {
    if (loadFilter !== 'all' && loadBucket(h) !== loadFilter) return false;
    if (specializationFilter !== 'all' && !h.specializations.includes(specializationFilter)) return false;
    return true;
  });

  // Restore a shared view (?hospital=&load=&spec=) once the map and hospital
  // list are both ready.
  $: if (!appliedShareParams && leafletMap && hospitals.length) {
    appliedShareParams = true;
    const hParam = $page.url.searchParams.get('hospital');
    if (hParam) {
      const id = Number(hParam);
      if (!Number.isNaN(id) && hospitalsById.has(id)) focusHospital(id);
    }
    const loadParam = $page.url.searchParams.get('load');
    if (loadParam === 'available' || loadParam === 'busy' || loadParam === 'critical') loadFilter = loadParam;
    const specParam = $page.url.searchParams.get('spec');
    if (specParam && specializations.includes(specParam)) specializationFilter = specParam;
  }

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
    routeSource = null;
    osrmRouteCoords = null;
    osrmRouteFor = null;
    osrmRequestId++;
    showFallbackNote = false;
    if (fallbackNoteTimer) clearTimeout(fallbackNoteTimer);
    fallbackNoteTimer = null;
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
    ws = new WebSocket(`${WS_BASE}/ws`);
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

  // Highlights a hospital on the map and table, panning/zooming the map to it.
  function focusHospital(id: number) {
    highlightedHospitalId = id;
    const h = hospitalsById.get(id);
    if (h && leafletMap) {
      leafletMap.setView([h.latitude, h.longitude], Math.max(leafletMap.getZoom(), 13));
    }
  }

  function selectSearchMatch(m: HospitalMatch) {
    focusHospital(m.id);
    searchQuery = '';
    searchFocused = false;
  }

  function handleSearch(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      if (searchMatches.length) selectSearchMatch(searchMatches[0]);
      else highlightedHospitalId = null;
    } else if (e.key === 'Escape') {
      searchQuery = '';
      searchFocused = false;
    }
  }

  // Download → CSV export of the Hospital Network table, respecting the
  // active load/specialization filters.
  function downloadCurrentView() {
    const rows = filteredHospitals.map(h => [
      h.name,
      h.region ?? '',
      h.available_beds,
      h.total_beds,
      h.available_icu_beds,
      h.total_icu_beds,
      Math.round(loadFactor(h) * 100),
      h.specializations.join('; '),
    ]);
    const parts = ['hospitals'];
    if (loadFilter !== 'all') parts.push(loadFilter);
    if (specializationFilter !== 'all') parts.push(specializationFilter.toLowerCase().replace(/\s+/g, '_'));
    downloadCsv(`${parts.join('_')}.csv`, [
      'Hospital', 'Region', 'Beds Available', 'Beds Total', 'ICU Available', 'ICU Total', 'Load %', 'Specializations',
    ], rows);
  }

  // Share → encode the current highlighted hospital + filters as URL params
  // and copy the link to the clipboard.
  async function shareView() {
    const url = new URL(window.location.href);
    url.search = '';
    if (highlightedHospitalId !== null) url.searchParams.set('hospital', String(highlightedHospitalId));
    if (loadFilter !== 'all') url.searchParams.set('load', loadFilter);
    if (specializationFilter !== 'all') url.searchParams.set('spec', specializationFilter);
    await navigator.clipboard.writeText(url.toString());
    shareCopied = true;
    if (shareCopyTimer) clearTimeout(shareCopyTimer);
    shareCopyTimer = setTimeout(() => { shareCopied = false; }, 2000);
  }

  // ── Map (Leaflet) ──────────────────────────────────────────────────────────

  function chartPalette() {
    const dark = $theme !== 'light';
    return {
      bg:     dark ? '#34302b' : '#e6dfd7',
      accent: dark ? '#14b8a6' : '#0f9d8e',
    };
  }

  // CARTO Voyager: a free OSM-based basemap with light, legible roads/labels.
  // Used for both themes — the dashboard's own light/dark surfaces provide
  // the theme contrast; CARTO's near-black "dark_all" tiles read as
  // illegible against a dark UI, and plain "light_all" is too faint to show
  // road detail in light mode either.
  const TILE_URL = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
  const TILE_ATTRIBUTION =
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors ' +
    '&copy; <a href="https://carto.com/attributions">CARTO</a>';

  function initTileLayer() {
    if (!leafletMap || !L) return;
    L.tileLayer(TILE_URL, {
      maxZoom: 19,
      subdomains: 'abcd',
      attribution: TILE_ATTRIBUTION,
    }).addTo(leafletMap);
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

  function drawRouteLine(latlngs: number[][]) {
    if (routeLine) {
      leafletMap.removeLayer(routeLine);
    }
    routeLine = L.polyline(latlngs, {
      color: chartPalette().accent,
      weight: 4,
      opacity: 0.85,
      dashArray: '1, 10',
      lineCap: 'round',
      className: 'route-line',
    }).addTo(leafletMap);
  }

  // OSRM is used only to draw a geographically realistic line on the map. The
  // hospital choice, ranking, score breakdown and ETA all come from A* over
  // our own synthetic routing graph (unchanged) — OSRM never feeds back into
  // that decision, it just makes the drawn line follow real Mumbai streets.
  const OSRM_TIMEOUT_MS = 4000;

  async function fetchOsrmRoute(assignedId: number) {
    if (!pendingLocation) return;
    const hospital = hospitals.find(h => h.id === assignedId);
    if (!hospital) return;

    const requestId = ++osrmRequestId;
    const url = `https://router.project-osrm.org/route/v1/driving/` +
      `${pendingLocation.lon},${pendingLocation.lat};${hospital.longitude},${hospital.latitude}` +
      `?overview=full&geometries=geojson`;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), OSRM_TIMEOUT_MS);
    try {
      const r = await fetch(url, { signal: controller.signal });
      if (!r.ok) throw new Error('OSRM request failed');
      const data = await r.json();
      const coords: number[][] | undefined = data?.routes?.[0]?.geometry?.coordinates;
      if (!coords || coords.length < 2) throw new Error('OSRM returned no route');

      // Bail if a newer request superseded this one, or the assignment moved
      // on while we were waiting (new emergency, reset, etc.).
      if (requestId !== osrmRequestId || !leafletMap || !L) return;
      if ((assignment?.assigned_hospital_id ?? null) !== assignedId) return;

      osrmRouteCoords = coords.map(([lon, lat]) => [lat, lon]);
      osrmRouteFor = assignedId;
      drawRouteLine(osrmRouteCoords);
      routeSource = 'osrm';
      showFallbackNote = false;
      if (fallbackNoteTimer) clearTimeout(fallbackNoteTimer);
      fallbackNoteTimer = null;
    } catch {
      // OSRM unavailable, rate-limited, or too slow — keep the synthetic-graph
      // polyline already drawn by renderRoute() so a route is always shown.
    } finally {
      clearTimeout(timeout);
    }
  }

  function renderRoute() {
    if (!leafletMap || !L) return;
    const winner = assignment?.candidates?.[0];
    const assignedId = assignment?.assigned_hospital_id ?? null;
    if (!winner || winner.path.length < 2 || assignedId === null) {
      if (routeLine) {
        leafletMap.removeLayer(routeLine);
        routeLine = null;
      }
      routeSource = null;
      osrmRouteCoords = null;
      osrmRouteFor = null;
      osrmRequestId++;
      showFallbackNote = false;
      if (fallbackNoteTimer) clearTimeout(fallbackNoteTimer);
      fallbackNoteTimer = null;
      return;
    }

    if (osrmRouteFor === assignedId && osrmRouteCoords) {
      // Already have a real-road line for this assignment — just redraw it
      // (e.g. on a theme change, which only affects the line color).
      drawRouteLine(osrmRouteCoords);
      routeSource = 'osrm';
    } else {
      // Draw the synthetic-graph path immediately as a fallback — see
      // backend/app/graph/ingest.py for why it's a smoothed grid path, not
      // real streets. fetchOsrmRoute() then tries to replace this with a
      // real-road line; if it fails or times out, this stays on screen.
      const latlngs = smoothPath(winner.path.map(p => [p.latitude, p.longitude]));
      drawRouteLine(latlngs);
      routeSource = 'synthetic-fallback';

      // Only surface the "approximate route" note if OSRM hasn't replaced
      // this within a moment — avoids a flash on the common fast-success path.
      if (fallbackNoteTimer) clearTimeout(fallbackNoteTimer);
      fallbackNoteTimer = setTimeout(() => {
        if (routeSource === 'synthetic-fallback') showFallbackNote = true;
      }, 600);
    }

    if (fittedAssignmentId !== assignedId) {
      leafletMap.fitBounds(routeLine.getBounds(), { padding: [48, 48], maxZoom: 14 });
      fittedAssignmentId = assignedId;
    }

    if (osrmRouteFor !== assignedId) {
      fetchOsrmRoute(assignedId);
    }
  }

  function renderMap() {
    if (!leafletMap || !L) return;
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
      initTileLayer();

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
    if (fallbackNoteTimer) clearTimeout(fallbackNoteTimer);
  });
</script>

<div class="shell">

  <Ticker />

  <TopNav>
    <div class="search-box">
      {@html ICONS.search}
      <input
        type="text"
        placeholder="Search hospital or region…"
        bind:value={searchQuery}
        on:keydown={handleSearch}
        on:focus={() => searchFocused = true}
        on:blur={() => setTimeout(() => searchFocused = false, 150)}
      />
      <span class="kbd">↵</span>
      {#if searchOpen}
        <div class="search-dropdown">
          {#if searchMatches.length === 0}
            <div class="search-empty">No hospitals or regions match "{searchQuery}"</div>
          {:else}
            {#each searchMatches as m, i (m.id)}
              <button class="search-match {i === 0 ? 'top' : ''}" on:mousedown={() => selectSearchMatch(m)}>
                <span class="search-match-label">{m.label}</span>
                <span class="search-match-sub">{m.sub}</span>
              </button>
            {/each}
          {/if}
        </div>
      {/if}
    </div>
    <button class="topbar-btn" on:click={shareView}>{@html ICONS.share}<span>{shareCopied ? 'Link copied' : 'Share'}</span></button>
    <button class="topbar-btn" on:click={downloadCurrentView}>{@html ICONS.download}<span>Download</span></button>
    <div class="topbar-action">
      <button class="topbar-btn {filtersOpen ? 'active' : ''}" on:click={() => filtersOpen = !filtersOpen}>{@html ICONS.filter}<span>Filters</span></button>
      {#if filtersOpen}
        <div class="popover-overlay" role="presentation" on:click={() => filtersOpen = false}></div>
        <div class="filters-popover">
          <label class="filter-field">
            <span>Hospital load</span>
            <select class="quiet-select" bind:value={loadFilter}>
              <option value="all">All</option>
              <option value="available">Available (&lt;60%)</option>
              <option value="busy">Busy (60–85%)</option>
              <option value="critical">Critical (&gt;85%)</option>
            </select>
          </label>
          <label class="filter-field">
            <span>Specialization</span>
            <select class="quiet-select" bind:value={specializationFilter}>
              <option value="all">All</option>
              {#each specializations as s}
                <option value={s}>{s}</option>
              {/each}
            </select>
          </label>
        </div>
      {/if}
    </div>
    <button
      class="icon-btn panel-toggle-btn"
      aria-label="Open dispatch panel"
      on:click={() => panelOpen = true}
    >{@html ICONS.panel}</button>
  </TopNav>

  <div class="content">
    <div class="content-main">

      <div class="page-header">
        <h1 class="section-title">Emergency Response</h1>
        <div class="data-updated">
          <span class="ws-dot {wsConnected ? 'connected' : ''}"></span>
          Data updated {lastUpdated ? timeAgo(lastUpdated.toISOString()) : '—'}
        </div>
      </div>

        <TopTabs tabs={[
          { label: 'Dispatch', href: '/emergency' },
          { label: 'Hospitals', href: '/emergency/hospitals' },
          { label: 'History', href: '/emergency/history' },
          { label: 'Routes', href: '/emergency/routes' },
          { label: 'Reports', href: '/emergency/reports' },
        ]} />

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
            {:else if showFallbackNote}
              <div class="map-hint">Live road routing unavailable — showing approximate route</div>
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
              {#each filteredHospitals as h (h.id)}
                <div class="hospital-row {h.id === assignment?.assigned_hospital_id || h.id === highlightedHospitalId ? 'active' : ''}">
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
              {:else if filteredHospitals.length === 0}
                <div class="empty-note">No hospitals match the current filters.</div>
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
            <div class="risk-level" style="color: {conditionColor(activeCase.patient_condition)}; font-size: 1.3rem; margin-top: var(--space-2);">
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

<style>
  /* Theme variables, fonts, and global resets live in
     src/lib/styles/theme.css (imported once via the root layout). */

  /* ── Shell layout ─────────────────────────────────────────────────────── */

  .shell {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.5;
    color: var(--text);
  }

  .page-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--space-4);
    flex-wrap: wrap;
  }
  .section-title {
    font-family: var(--serif);
    font-size: 1.75rem;
    font-weight: 600;
    margin: 0;
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
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    max-width: 440px;
    padding: var(--space-2) var(--space-3);
    border-radius: 6px;
    background: var(--bg-sunken);
    border: 1px solid var(--border);
    color: var(--text-muted);
  }
  .search-box :global(svg) { width: 16px; height: 16px; flex-shrink: 0; }
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

  .search-dropdown {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    right: 0;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
    z-index: 30;
    max-height: 280px;
    overflow-y: auto;
  }
  .search-match {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding: 8px 12px;
    background: transparent;
    border: none;
    border-bottom: 1px solid var(--border-soft);
    color: var(--text);
    font-family: var(--sans);
    font-size: 0.83rem;
    text-align: left;
    cursor: pointer;
  }
  .search-match:last-child { border-bottom: none; }
  .search-match:hover, .search-match.top { background: var(--bg-hover); }
  .search-match-sub {
    font-size: 0.68rem;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .search-empty {
    padding: var(--space-3) var(--space-3);
    font-size: 0.83rem;
    color: var(--text-faint);
  }

  .data-updated {
    display: flex;
    align-items: center;
    gap: var(--space-2);
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
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
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
  .topbar-btn :global(svg) { width: 16px; height: 16px; }
  .topbar-btn.active { background: var(--bg-hover); color: var(--text); border-color: var(--accent); }

  .topbar-action { position: relative; }
  .popover-overlay {
    position: fixed;
    inset: 0;
    z-index: 25;
  }
  .filters-popover {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    z-index: 30;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 200px;
  }
  .filter-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.7rem;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .quiet-select {
    background: var(--bg-sunken);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: var(--space-1) var(--space-2);
    font-family: var(--sans);
    font-size: 0.78rem;
    color: var(--text-muted);
    cursor: pointer;
  }

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

  .error-banner {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-sm);
    border: 1px solid var(--danger);
    background: rgba(220, 79, 69, 0.1);
    color: var(--danger);
    font-size: 0.83rem;
  }
  .error-banner :global(svg) { width: 16px; height: 16px; flex-shrink: 0; }

  /* ── Panels ───────────────────────────────────────────────────────────── */

  .panel {
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-4);
  }
  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: var(--space-4);
  }
  .panel-header h2 {
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0;
    letter-spacing: -0.01em;
  }

  .risk-legend {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    font-size: 0.8rem;
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
  .legend-item { display: flex; align-items: center; gap: var(--space-2); }
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
    font-size: 0.82rem;
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
    padding: var(--space-2) var(--space-4);
    font-size: 0.85rem;
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
    gap: var(--space-3);
    padding: 12px;
    border-radius: var(--radius-sm);
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    transition: border-color var(--ease-hover), transform var(--ease-hover);
  }
  .stat-card:hover { border-color: var(--border); transform: translateY(-2px); }
  .stat-card :global(svg) {
    width: 16px;
    height: 16px;
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
    font-family: var(--sans);
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum';
    font-size: 1.5rem;
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

  .empty-note { font-size: 0.88rem; color: var(--text-faint); padding: 16px 8px; text-align: center; }

  /* ── Hospital table ───────────────────────────────────────────────────── */

  .hospital-table { display: flex; flex-direction: column; gap: 2px; }
  .hospital-table-head,
  .hospital-row {
    display: grid;
    grid-template-columns: 1.8fr 0.9fr 1fr 1fr 0.6fr;
    align-items: center;
    gap: var(--space-3);
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
  .hospital-name { font-size: 0.93rem; color: var(--text); display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .hospital-spec { font-size: 0.74rem; color: var(--text-faint); text-transform: capitalize; }
  .hospital-region { font-size: 0.87rem; color: var(--text-muted); text-align: right; }
  .capacity-cell { display: flex; flex-direction: column; gap: 4px; align-items: flex-end; }
  .capacity-text { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; font-size: 0.85rem; color: var(--text); }
  .capacity-bar-wrap { width: 100%; height: 4px; border-radius: 2px; background: var(--border); overflow: hidden; }
  .capacity-bar { display: block; height: 100%; border-radius: 2px; transition: width 0.4s ease; }
  .load-cell { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; font-size: 0.93rem; font-weight: 600; text-align: right; }

  /* ── Recent emergencies ───────────────────────────────────────────────── */

  .emergency-list { display: flex; flex-direction: column; gap: var(--space-2); }
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
  .emergency-cond { font-size: 0.82rem; font-weight: 700; letter-spacing: 0.03em; }
  .emergency-time { font-size: 0.7rem; color: var(--text-faint); font-family: var(--mono); }
  .emergency-detail { font-size: 0.87rem; color: var(--text-muted); }

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
    padding: var(--space-4);
    position: sticky;
    top: calc(var(--topbar-h) + 8px);
    max-height: calc(100vh - var(--topbar-h) - 16px);
    overflow-y: auto;
  }
  .detail-panel::-webkit-scrollbar { width: 6px; }
  .detail-panel::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .detail-header h2 { font-size: 1.35rem; font-weight: 600; margin: 0; }

  .risk-score-block {
    text-align: center;
    padding: 16px;
    border-radius: var(--radius-sm);
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
  }
  .risk-label { font-size: 0.6875rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; }
  .risk-level { font-size: 0.92rem; font-weight: 600; margin-top: 4px; }
  .winner-name { font-family: var(--sans); font-size: 1.35rem; font-weight: 700; color: var(--text); margin-top: var(--space-2); }

  .detail-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .detail-cell {
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm);
    padding: var(--space-3);
  }
  .detail-label { font-size: 0.6875rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; }
  .detail-value { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; font-size: 1.15rem; font-weight: 600; margin-top: 4px; color: var(--text); }

  .detail-section { padding-top: var(--space-4); border-top: 1px solid var(--border-soft); }
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
    gap: var(--space-2);
  }
  .condition-btn {
    padding: 8px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--bg-sunken);
    color: var(--text-muted);
    font-family: var(--sans);
    font-size: 0.88rem;
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
    padding: var(--space-3);
    border-radius: 6px;
    border: 1px solid var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
    font-family: var(--sans);
    font-size: 0.92rem;
    font-weight: 600;
    cursor: pointer;
  }
  .primary-btn:hover { background: var(--accent); color: #fff; }
  .primary-btn:disabled { opacity: 0.6; cursor: default; background: var(--accent-soft); color: var(--accent); }
  .primary-btn :global(svg) { width: 16px; height: 16px; }

  .text-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    border: none;
    background: transparent;
    color: var(--accent);
    font-family: var(--sans);
    font-size: 0.85rem;
    cursor: pointer;
    padding: var(--space-2);
  }
  .text-btn :global(svg) { width: 16px; height: 16px; }

  .error-msg {
    font-size: 0.85rem;
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
    gap: var(--space-3);
    font-size: 0.68rem;
    color: var(--text-muted);
    margin-bottom: var(--space-3);
  }

  .candidate-list { display: flex; flex-direction: column; gap: 8px; }
  .candidate-row {
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    border-radius: 6px;
    padding: var(--space-2) var(--space-3);
  }
  .candidate-row.winner { background: var(--accent-soft); border-color: var(--accent); }
  .candidate-top { display: flex; align-items: center; gap: 8px; }
  .candidate-rank { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; font-size: 0.75rem; color: var(--text-faint); }
  .candidate-name { flex: 1; font-size: 0.93rem; font-weight: 500; color: var(--text); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .candidate-score { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; font-size: 0.93rem; font-weight: 600; color: var(--text); }
  .candidate-meta { font-size: 0.76rem; color: var(--text-faint); margin-top: 2px; }

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
    gap: var(--space-2);
    margin-top: 8px;
    font-size: 0.76rem;
    color: var(--risk-severe);
  }
  .surge-note :global(svg) { width: 16px; height: 16px; flex-shrink: 0; }

  /* ── Filtered out list ────────────────────────────────────────────────── */

  .filtered-list { display: flex; flex-direction: column; gap: var(--space-2); }
  .filtered-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-2);
    border-radius: 6px;
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    font-size: 0.83rem;
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
    .stat-row { grid-template-columns: repeat(2, 1fr); }
    .topbar-btn span { display: none; }
    .hospital-table-head, .hospital-row { grid-template-columns: 1.6fr 1fr 1fr 1fr; }
    .hospital-region { display: none; }
    .hospital-table-head span:nth-child(2) { display: none; }
  }
</style>
