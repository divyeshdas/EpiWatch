<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { theme } from '$lib/stores/theme';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import Ticker from '$lib/components/Ticker.svelte';
  import TopTabs from '$lib/components/TopTabs.svelte';
  import { downloadCsv } from '$lib/csv';
  import { ICONS } from '$lib/icons';
  import { sidebarCollapsed, toggleSidebar } from '$lib/stores/sidebar';
  import { API_BASE, WS_BASE } from '$lib/api';

  // ── Types ──────────────────────────────────────────────────────────────────

  type DiseaseInfo = {
    disease_name: string;
    regions: string[];
    date_from: string;
    date_to: string;
    total_records: number;
  };

  type OutbreakPoint = {
    date: string;
    case_count: number;
    deaths: number;
    source: string;
  };

  type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

  type SpikeDetection = {
    date: string;
    value: number;
    rolling_mean: number;
    rolling_std: number;
    z_score: number;
    severity: Severity;
  };

  type AlertRow = {
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

  type ScanResponse = {
    disease_name: string;
    region: string;
    window: number;
    points_scanned: number;
    detections: SpikeDetection[];
    new_alerts: AlertRow[];
  };

  type RiskLevel = 'LOW' | 'MODERATE' | 'HIGH' | 'SEVERE';

  // Per (disease, country) combination — the unit everything else aggregates.
  type DiseaseSeries = {
    disease: string;
    series: OutbreakPoint[];
    spikes: SpikeDetection[];
    topSpike: SpikeDetection | null;
    latestCases: number;
    latestDeaths: number;
    pctChange: number | null;
    riskScore: number;
  };

  // One country: its diseases, plus the aggregate that drives the map +
  // detail panel (the "primary" disease is whichever currently scores
  // highest risk for that country).
  type CountryEntry = {
    country: string;
    geoName: string;
    diseases: DiseaseSeries[];
    primary: DiseaseSeries;
    riskScore: number;
    riskLevel: RiskLevel;
    totalCases: number;
    pctChange: number | null;
    anomalyZ: number | null;
  };

  // ── Constants ──────────────────────────────────────────────────────────────

  const API = `${API_BASE}/surveillance`;

  // Restrained, fixed per-disease colors — kept consistent everywhere a
  // disease is shown (trend lines, disease table, hotspot bars).
  const DISEASE_COLORS: Record<string, string> = {
    covid_19: '#14b8a6',
    measles: '#c94a45',
    dengue: '#a8893f',
    cholera: '#78716c',
  };

  const DISEASE_LABELS: Record<string, string> = {
    covid_19: 'COVID-19',
    measles: 'Measles',
    dengue: 'Dengue',
    cholera: 'Cholera',
  };

  // Alert severity reuses the same risk scale as the map — low to severe
  // is the one meaningful colour code across the whole app.
  const SEVERITY_COLORS: Record<Severity, string> = {
    LOW: '#5f806b',
    MEDIUM: '#a8893f',
    HIGH: '#b96532',
    CRITICAL: '#c94a45',
  };
  const SEVERITY_LABELS: Record<Severity, string> = {
    LOW: 'Low', MEDIUM: 'Medium', HIGH: 'High', CRITICAL: 'Critical',
  };
  const SEVERITY_MARK_SIZE: Record<Severity, number> = {
    LOW: 7, MEDIUM: 10, HIGH: 13, CRITICAL: 17,
  };

  // Risk levels reuse the same colour scale as alert severity — low to
  // severe is the one meaningful colour code across the whole app.
  const RISK_COLORS: Record<RiskLevel, string> = {
    LOW: '#5f806b',
    MODERATE: '#a8893f',
    HIGH: '#b96532',
    SEVERE: '#c94a45',
  };
  const RISK_LABELS: Record<RiskLevel, string> = {
    LOW: 'Low', MODERATE: 'Moderate', HIGH: 'High', SEVERE: 'Severe',
  };

  // Maps backend region/country names to the feature names used by the
  // bundled world-atlas (Natural Earth) GeoJSON.
  const COUNTRY_GEO_NAMES: Record<string, string> = {
    India: 'India',
    Brazil: 'Brazil',
    Germany: 'Germany',
    'United States': 'United States of America',
    DRC: 'Dem. Rep. Congo',
    Yemen: 'Yemen',
    Indonesia: 'Indonesia',
    Philippines: 'Philippines',
    Ethiopia: 'Ethiopia',
    Nigeria: 'Nigeria',
    Pakistan: 'Pakistan',
  };

  // Mirrors app.config.settings.spike_window_size (backend) — the trailing
  // window the z-score detector uses as its baseline.
  const SPIKE_BASELINE_MONTHS = 6;

  // ── Risk scoring ───────────────────────────────────────────────────────────
  //
  // There's no separate "risk model" on the backend — the risk score shown
  // here is a transparent re-expression of the B3 z-score/severity spike
  // detector already used for alerts. Each severity tier gets a base score;
  // the magnitude of the anomaly (z-score, capped) nudges it within that
  // tier. This keeps "risk" explainable in terms of a number that's already
  // on screen elsewhere (the alert feed), rather than inventing a new metric.
  const RISK_SEVERITY_BASE: Record<Severity, number> = {
    LOW: 12, MEDIUM: 38, HIGH: 64, CRITICAL: 84,
  };

  function riskScoreFor(top: SpikeDetection | null): number {
    if (!top) return 8;
    const z = top.z_score >= 999 ? 5 : Math.max(0, top.z_score);
    return Math.min(100, Math.round(RISK_SEVERITY_BASE[top.severity] + Math.min(12, z * 2)));
  }

  function riskLevelFor(score: number): RiskLevel {
    if (score >= 80) return 'SEVERE';
    if (score >= 60) return 'HIGH';
    if (score >= 35) return 'MODERATE';
    return 'LOW';
  }

  function topSpike(list: SpikeDetection[]): SpikeDetection | null {
    if (list.length === 0) return null;
    return list.reduce((max, s) => (s.z_score > max.z_score ? s : max), list[0]);
  }

  // ── State ──────────────────────────────────────────────────────────────────

  let diseases: DiseaseInfo[] = [];
  let countryEntries: CountryEntry[] = [];
  let selectedCountry = 'India';
  let selectedCountryDisease = 'covid_19';
  let loadingData = true;
  let loadError: string | null = null;
  let lastUpdated: Date | null = null;

  // Right intelligence panel — collapses to an off-canvas drawer below 1100px.
  let panelOpen = false;

  // Map filters — both are real filters over countryEntries, not decoration.
  let mapDiseaseFilter = 'all';
  let mapRiskFilter: 'all' | RiskLevel = 'all';

  // Trends panel
  let trendMetric: 'cases' | 'deaths' = 'cases';

  // Search box (top bar) — jumps the map/selection to a matching disease or country.
  let searchQuery = '';
  let searchFocused = false;
  let debouncedQuery = '';
  let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  // Topbar filters popover — these drive the same map/alert filters the page
  // already has, plus a new alert-severity filter.
  let filtersOpen = false;
  let alertSeverityFilter: 'all' | Severity = 'all';

  // Topbar share — encodes the current region/disease/filters as URL params,
  // restored by the one-shot reactive block below on load.
  let shareCopied = false;
  let shareCopyTimer: ReturnType<typeof setTimeout> | null = null;
  let appliedShareParams = false;

  // Spike detection / alert feed
  let alerts: AlertRow[] = [];
  let newAlertIds = new Set<number>();
  let scanning = false;
  let scanMessage: string | null = null;
  let ws: WebSocket | null = null;
  let wsConnected = false;

  // ECharts instances — browser-only
  let echarts: any = null;
  let mapEl: HTMLDivElement;
  let mapChart: any = null;
  let worldMapReady = false;
  let trendEl: HTMLDivElement;
  let trendChart: any = null;
  let countryEl: HTMLDivElement;
  let countryChart: any = null;

  // ── Data loading ───────────────────────────────────────────────────────────

  async function loadAll() {
    loadingData = true;
    loadError = null;
    try {
      const r = await fetch(`${API}/diseases`);
      diseases = await r.json();

      const combos: { disease: string; region: string }[] = [];
      for (const d of diseases) for (const region of d.regions) combos.push({ disease: d.disease_name, region });

      const fetched = await Promise.all(combos.map(async (c) => {
        const [sr, zr] = await Promise.all([
          fetch(`${API}/timeseries?disease=${encodeURIComponent(c.disease)}&region=${encodeURIComponent(c.region)}`),
          fetch(`${API}/spikes?disease=${encodeURIComponent(c.disease)}&region=${encodeURIComponent(c.region)}`),
        ]);
        const series: OutbreakPoint[] = sr.ok ? await sr.json() : [];
        const spikes: SpikeDetection[] = zr.ok ? await zr.json() : [];
        const top = topSpike(spikes);
        const last = series[series.length - 1] ?? null;
        const prev = series[series.length - 2] ?? null;
        const pctChange = (last && prev && prev.case_count > 0)
          ? ((last.case_count - prev.case_count) / prev.case_count) * 100
          : null;
        const ds: DiseaseSeries = {
          disease: c.disease,
          series, spikes, topSpike: top,
          latestCases: last?.case_count ?? 0,
          latestDeaths: last?.deaths ?? 0,
          pctChange,
          riskScore: riskScoreFor(top),
        };
        return { region: c.region, ds };
      }));

      const byCountry = new Map<string, DiseaseSeries[]>();
      for (const { region, ds } of fetched) {
        if (!byCountry.has(region)) byCountry.set(region, []);
        byCountry.get(region)!.push(ds);
      }

      countryEntries = Array.from(byCountry.entries()).map(([country, ds]) => {
        const sorted = [...ds].sort((a, b) => b.riskScore - a.riskScore);
        const primary = sorted[0];
        return {
          country,
          geoName: COUNTRY_GEO_NAMES[country] ?? country,
          diseases: [...ds].sort((a, b) => b.latestCases - a.latestCases),
          primary,
          riskScore: primary.riskScore,
          riskLevel: riskLevelFor(primary.riskScore),
          totalCases: ds.reduce((sum, d) => sum + d.latestCases, 0),
          pctChange: primary.pctChange,
          anomalyZ: primary.topSpike?.z_score ?? null,
        };
      }).sort((a, b) => b.riskScore - a.riskScore);

      if (!countryEntries.find(c => c.country === selectedCountry)) {
        selectedCountry = countryEntries[0]?.country ?? '';
      }
      lastUpdated = new Date();
    } catch (e) {
      loadError = 'Could not reach the surveillance API. Showing the last known data.';
    } finally {
      loadingData = false;
    }
  }

  // ── Derived aggregates ─────────────────────────────────────────────────────

  $: selectedEntry = countryEntries.find(c => c.country === selectedCountry) ?? null;

  // Keep the country-detail disease selection valid as the country changes —
  // default to that country's primary (highest-risk) disease.
  $: if (selectedEntry && !selectedEntry.diseases.find(d => d.disease === selectedCountryDisease)) {
    selectedCountryDisease = selectedEntry.primary.disease;
  }
  $: selectedDiseaseSeries = selectedEntry?.diseases.find(d => d.disease === selectedCountryDisease) ?? null;

  $: allCombos = countryEntries.flatMap(c => c.diseases.map(d => ({ country: c.country, ...d })));

  $: globalStats = {
    countries: countryEntries.length,
    activeOutbreaks: allCombos.filter(d => d.topSpike && (d.topSpike.severity === 'HIGH' || d.topSpike.severity === 'CRITICAL')).length,
    highRisk: countryEntries.filter(c => c.riskLevel === 'HIGH' || c.riskLevel === 'SEVERE').length,
    avgChange: (() => {
      const vals = allCombos.map(d => d.pctChange).filter((v): v is number => v !== null);
      if (!vals.length) return null;
      return vals.reduce((a, b) => a + b, 0) / vals.length;
    })(),
    records: diseases.reduce((sum, d) => sum + d.total_records, 0),
  };

  $: topHotspots = [...allCombos]
    .filter(d => d.topSpike)
    .sort((a, b) => (b.topSpike!.z_score) - (a.topSpike!.z_score))
    .slice(0, 5);

  // Map data with the disease/risk filters applied — when a single disease
  // is selected, each country's score/level reflect just that disease.
  $: mapEntries = countryEntries
    .map(c => {
      if (mapDiseaseFilter === 'all') return { ...c, hasData: true };
      const ds = c.diseases.find(d => d.disease === mapDiseaseFilter);
      if (!ds) return { ...c, riskScore: 0, riskLevel: 'LOW' as RiskLevel, hasData: false };
      return { ...c, riskScore: ds.riskScore, riskLevel: riskLevelFor(ds.riskScore), pctChange: ds.pctChange, anomalyZ: ds.topSpike?.z_score ?? null, hasData: true };
    })
    .filter(c => mapRiskFilter === 'all' || c.riskLevel === mapRiskFilter);

  // Deep-link from the Diseases tab (/surveillance?disease=<slug>) —
  // pre-selects that disease in the Global Risk Map filter once the
  // diseases list has loaded.
  $: {
    const d = $page.url.searchParams.get('disease');
    if (d && diseases.some(x => x.disease_name === d)) mapDiseaseFilter = d;
  }

  // Restore a shared view (?region=&disease=&risk=&severity=) once the
  // country data has loaded. One-shot — afterwards the user's own filter
  // changes take over.
  $: if (!appliedShareParams && countryEntries.length) {
    appliedShareParams = true;
    const region = $page.url.searchParams.get('region');
    const target = region && countryEntries.find(c => c.country === region);
    if (target) {
      selectedCountry = target.country;
      panelOpen = true;
      const d = $page.url.searchParams.get('disease');
      if (d && target.diseases.some(x => x.disease === d)) selectedCountryDisease = d;
    }
    const risk = $page.url.searchParams.get('risk');
    if (risk === 'LOW' || risk === 'MODERATE' || risk === 'HIGH' || risk === 'SEVERE') mapRiskFilter = risk;
    const severity = $page.url.searchParams.get('severity');
    if (severity === 'LOW' || severity === 'MEDIUM' || severity === 'HIGH' || severity === 'CRITICAL') alertSeverityFilter = severity;
  }

  // ── Topbar search ──────────────────────────────────────────────────────────

  $: {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    const q = searchQuery;
    searchDebounceTimer = setTimeout(() => { debouncedQuery = q; }, 200);
  }

  type SearchMatch = { kind: 'disease' | 'country'; id: string; label: string; sub: string };

  $: searchMatches = ((): SearchMatch[] => {
    const q = debouncedQuery.trim().toLowerCase();
    if (!q) return [];
    const diseaseMatches: SearchMatch[] = diseases
      .filter(d => diseaseLabel(d.disease_name).toLowerCase().includes(q) || d.disease_name.toLowerCase().includes(q))
      .map(d => ({ kind: 'disease', id: d.disease_name, label: diseaseLabel(d.disease_name), sub: 'Disease' }));
    const countryMatches: SearchMatch[] = countryEntries
      .filter(c => c.country.toLowerCase().includes(q))
      .map(c => ({ kind: 'country', id: c.country, label: c.country, sub: `${RISK_LABELS[c.riskLevel]} risk` }));
    return [...diseaseMatches, ...countryMatches].slice(0, 8);
  })();

  $: searchOpen = searchFocused && searchQuery.trim().length > 0;

  $: recommendedActions = selectedEntry ? buildRecommendedActions(selectedEntry) : [];

  function buildRecommendedActions(entry: CountryEntry): string[] {
    const actions: string[] = [];
    for (const d of entry.diseases) {
      if (d.topSpike && (d.topSpike.severity === 'HIGH' || d.topSpike.severity === 'CRITICAL')) {
        actions.push(`Scale up ${diseaseLabel(d.disease).toLowerCase()} surveillance and case reporting in ${entry.country}`);
      }
    }
    const elevated = (name: string) => entry.diseases.find(d => d.disease === name && d.topSpike && d.topSpike.severity !== 'LOW');
    if (elevated('dengue')) actions.push('Increase vector control in affected districts');
    if (elevated('measles')) actions.push('Review immunization coverage and catch-up campaigns');
    if (elevated('cholera')) actions.push('Audit water and sanitation infrastructure in hotspot areas');
    if (actions.length === 0) actions.push(`Maintain routine monitoring for ${entry.country}`);
    return actions.slice(0, 4);
  }

  // ── Alerts + live feed ──────────────────────────────────────────────────────

  async function loadAlerts() {
    const r = await fetch(`${API_BASE}/alerts?limit=30`);
    if (r.ok) alerts = await r.json();
  }

  function addAlert(a: AlertRow) {
    if (alerts.find(x => x.id === a.id)) return;
    alerts = [a, ...alerts].slice(0, 50);
    newAlertIds.add(a.id);
    newAlertIds = newAlertIds;
    setTimeout(() => {
      newAlertIds.delete(a.id);
      newAlertIds = newAlertIds;
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
    ws.onmessage = (msg: MessageEvent) => {
      const e = JSON.parse(msg.data);
      if (e.type === 'AlertGenerated') {
        const p = e.payload;
        addAlert({
          id: p.alert_id,
          type: p.type,
          severity: p.severity,
          message: p.message,
          region: p.region,
          disease_name: p.disease_name,
          event_date: p.event_date,
          z_score: p.z_score,
          created_at: p.created_at,
          resolved_at: null,
        });
      }
    };
  }

  // Re-runs the detector for the selected country's primary disease, then
  // refreshes the whole aggregate (small dataset — a full reload is cheap
  // and guarantees every panel reflects the new detections).
  async function scanSelected() {
    if (!selectedEntry || scanning) return;
    scanning = true;
    scanMessage = null;
    try {
      const { country, primary } = selectedEntry;
      const url = `${API}/scan?disease=${encodeURIComponent(primary.disease)}&region=${encodeURIComponent(country)}`;
      const r = await fetch(url, { method: 'POST' });
      if (!r.ok) { scanMessage = 'scan failed'; return; }
      const body: ScanResponse = await r.json();
      scanMessage = `${body.detections.length} detection(s) · ${body.new_alerts.length} new alert(s)`;
      for (const a of body.new_alerts) addAlert(a);
      await loadAll();
    } finally {
      scanning = false;
    }
  }

  // ── Formatting helpers ─────────────────────────────────────────────────────

  function fmt(n: number): string {
    if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toLocaleString();
  }

  function fmtPct(n: number | null): string {
    if (n === null) return '—';
    return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`;
  }

  function formatZ(z: number | null): string {
    if (z === null) return '—';
    if (z >= 999) return '>5σ';
    return `${z.toFixed(2)}σ`;
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

  function diseaseLabel(slug: string): string {
    return DISEASE_LABELS[slug] ?? slug;
  }

  function diseaseColor(slug: string): string {
    return DISEASE_COLORS[slug] ?? '#94a3b8';
  }

  function riskColor(level: string): string {
    return RISK_COLORS[level as RiskLevel] ?? '#94a3b8';
  }

  // Tiny inline-SVG sparkline path for the active-diseases table — last 12
  // points of case_count, normalized to a 64x24 box.
  function sparklinePath(series: OutbreakPoint[], w = 64, h = 24): string {
    const vals = series.slice(-12).map(p => p.case_count);
    if (vals.length < 2) return '';
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const range = max - min || 1;
    return vals.map((v, i) => {
      const x = (i / (vals.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 2) - 1;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }

  function selectCountry(country: string) {
    if (!countryEntries.find(c => c.country === country)) return;
    selectedCountry = country;
    panelOpen = true;
  }

  function onRegionFilterChange(e: Event) {
    selectCountry((e.target as HTMLSelectElement).value);
  }

  function selectSearchMatch(m: SearchMatch) {
    if (m.kind === 'disease') {
      mapDiseaseFilter = m.id;
    } else {
      selectCountry(m.id);
    }
    searchQuery = '';
    searchFocused = false;
  }

  function handleSearch(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      if (searchMatches.length) selectSearchMatch(searchMatches[0]);
    } else if (e.key === 'Escape') {
      searchQuery = '';
      searchFocused = false;
    }
  }

  // Download → CSV export of the currently-viewed time series (the country
  // detail panel's selected disease), falling back to the global hotspots
  // table if nothing is selected yet.
  function downloadCurrentView() {
    if (selectedEntry && selectedDiseaseSeries) {
      const region = selectedEntry.country.toLowerCase().replace(/\s+/g, '_');
      const rows = selectedDiseaseSeries.series.map(p => [p.date, p.case_count, p.deaths]);
      downloadCsv(`${selectedCountryDisease}_${region}_timeseries.csv`, ['Date', 'Cases', 'Deaths'], rows);
    } else {
      const rows = topHotspots.map(h => [h.country, diseaseLabel(h.disease), h.latestCases, formatZ(h.topSpike?.z_score ?? null), h.topSpike?.severity ?? '—']);
      downloadCsv('hotspots.csv', ['Country', 'Disease', 'Cases', 'Z-Score', 'Severity'], rows);
    }
  }

  // Share → encode the current region/disease + active filters as URL params
  // and copy the link to the clipboard.
  async function shareView() {
    const url = new URL(window.location.href);
    url.search = '';
    if (selectedCountry) url.searchParams.set('region', selectedCountry);
    if (selectedCountryDisease) url.searchParams.set('disease', selectedCountryDisease);
    if (mapRiskFilter !== 'all') url.searchParams.set('risk', mapRiskFilter);
    if (alertSeverityFilter !== 'all') url.searchParams.set('severity', alertSeverityFilter);
    await navigator.clipboard.writeText(url.toString());
    shareCopied = true;
    if (shareCopyTimer) clearTimeout(shareCopyTimer);
    shareCopyTimer = setTimeout(() => { shareCopied = false; }, 2000);
  }

  // ── ECharts ────────────────────────────────────────────────────────────────

  function chartPalette() {
    const dark = $theme !== 'light';
    return {
      text:          dark ? '#f5f5f4' : '#1f1c19',
      muted:         dark ? '#a8a29e' : '#6b645d',
      grid:          dark ? '#3a332e' : '#e2dcd4',
      axis:          dark ? '#51483f' : '#cfc6bb',
      tooltipBg:     dark ? '#26221f' : '#faf7f3',
      tooltipBorder: dark ? '#3a332e' : '#e2dcd4',
      bg:            dark ? '#34302b' : '#e6dfd7',
      noData:        dark ? '#34302b' : '#e6dfd7',
      hover:         dark ? '#2b2723' : '#f0ebe5',
      border:        dark ? '#51483f' : '#cfc6bb',
      selected:      dark ? '#f5f5f4' : '#1f1c19',
    };
  }

  function spikeMarkPoint(s: SpikeDetection, pal: ReturnType<typeof chartPalette>) {
    return {
      name: s.severity,
      coord: [s.date, s.value],
      symbolSize: SEVERITY_MARK_SIZE[s.severity] ?? 7,
      itemStyle: {
        color: SEVERITY_COLORS[s.severity] ?? '#94a3b8',
        borderColor: pal.bg,
        borderWidth: 1.5,
      },
      label: { show: false },
    };
  }

  function spikeTooltip(spikes: SpikeDetection[]) {
    return (params: any): string => {
      const s = spikes.find(sp => sp.date === params.data.coord[0] && sp.value === params.data.coord[1]);
      if (!s) return params.name;
      return `<div style="font-weight:700;color:${SEVERITY_COLORS[s.severity]};margin-bottom:4px">`
        + `${formatZ(s.z_score)} · ${s.severity}</div>`
        + `${s.value.toLocaleString()} on ${s.date} (baseline μ ${Math.round(s.rolling_mean).toLocaleString()})`;
    };
  }

  // CRITICAL anomalies ripple continuously on a chart — same convention as
  // the live alert feed's "CRITICAL pulses, LOW doesn't".
  function criticalRippleSeries(list: SpikeDetection[]) {
    return {
      name: 'critical-pulse',
      type: 'effectScatter',
      coordinateSystem: 'cartesian2d',
      silent: true,
      tooltip: { show: false },
      symbolSize: 9,
      rippleEffect: { brushType: 'stroke', scale: 3.5, period: 3 },
      itemStyle: { color: SEVERITY_COLORS.CRITICAL },
      data: list.filter(s => s.severity === 'CRITICAL').map(s => [s.date, s.value]),
      z: 5,
    };
  }

  // A handful of features in the bundled world-atlas topology (Russia,
  // Fiji, Antarctica) have rings that cross the +/-180 degree antimeridian.
  // Plotted directly on an equirectangular map, the segment that "jumps"
  // from one edge of the map to the other renders as a long stray line
  // across the whole map. Split each ring at antimeridian crossings into
  // fragments that each close along a single edge instead.
  function splitAntimeridian(ring: number[][]): number[][][] {
    const fragments: number[][][] = [];
    let current: number[][] = [ring[0]];
    for (let i = 1; i < ring.length; i++) {
      const prev = ring[i - 1];
      const pt = ring[i];
      const dLon = pt[0] - prev[0];
      if (dLon > 180 || dLon < -180) {
        const endLon = dLon > 180 ? -180 : 180;
        const startLon = -endLon;
        const ptCont = dLon > 180 ? pt[0] - 360 : pt[0] + 360;
        const t = (endLon - prev[0]) / (ptCont - prev[0]);
        const lat = prev[1] + t * (pt[1] - prev[1]);
        current.push([endLon, lat]);
        fragments.push(current);
        current = [[startLon, lat]];
      }
      current.push(pt);
    }
    fragments.push(current);
    if (fragments.length > 1) {
      const first = fragments.shift()!;
      const last = fragments.pop()!;
      fragments.push(last.concat(first.slice(1)));
    }
    return fragments.filter((f) => f.length >= 3);
  }

  function ringCrossesAntimeridian(ring: number[][]): boolean {
    return ring.some((pt, i) => i > 0 && Math.abs(pt[0] - ring[i - 1][0]) > 180);
  }

  function fixAntimeridian(geo: any) {
    for (const f of geo.features) {
      const geom = f.geometry;
      if (!geom) continue;
      if (geom.type === 'Polygon') {
        const rings: number[][][] = geom.coordinates;
        if (!rings.some(ringCrossesAntimeridian)) continue;
        geom.type = 'MultiPolygon';
        geom.coordinates = rings.flatMap((r) => splitAntimeridian(r).map((frag) => [frag]));
      } else if (geom.type === 'MultiPolygon') {
        const polys: number[][][][] = geom.coordinates;
        const out: number[][][][] = [];
        for (const poly of polys) {
          if (!poly.some(ringCrossesAntimeridian)) {
            out.push(poly);
            continue;
          }
          for (const r of poly) {
            for (const frag of splitAntimeridian(r)) out.push([frag]);
          }
        }
        geom.coordinates = out;
      }
    }
  }

  // Loads the world GeoJSON (converted from the bundled world-atlas
  // TopoJSON) and registers it once with ECharts.
  async function loadWorldMap() {
    const [topojson, topoRes] = await Promise.all([
      import('topojson-client'),
      fetch('/world-110m.json'),
    ]);
    const topo = await topoRes.json();
    const geo = topojson.feature(topo, topo.objects.countries as any);
    fixAntimeridian(geo as any);
    echarts.registerMap('world', geo as any);
    worldMapReady = true;
  }

  function renderMapChart() {
    if (!mapChart || !echarts || !worldMapReady) return;
    const pal = chartPalette();
    const data = mapEntries.map(c => ({
      name: c.geoName,
      value: c.riskScore,
      countryMeta: c,
      itemStyle: {
        areaColor: c.hasData ? RISK_COLORS[c.riskLevel] : pal.noData,
        opacity: c.hasData ? 0.78 : 1,
        borderColor: c.country === selectedCountry ? pal.selected : pal.border,
        borderWidth: c.country === selectedCountry ? 1.5 : 0.5,
      },
    }));
    mapChart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        backgroundColor: pal.tooltipBg,
        borderColor: pal.tooltipBorder,
        textStyle: { color: pal.text, fontSize: 12, fontFamily: 'var(--sans)' },
        formatter: (params: any) => {
          const meta = params.data?.countryMeta as (CountryEntry & { hasData: boolean }) | undefined;
          if (!meta || !meta.hasData) return params.name;
          const lines = [
            `<div style="font-weight:600;margin-bottom:4px;font-family:var(--sans)">${meta.country}</div>`,
            `<div style="color:${RISK_COLORS[meta.riskLevel]};margin-bottom:4px">${RISK_LABELS[meta.riskLevel]} risk · ${meta.riskScore}/100</div>`,
            `Latest cases: <strong>${meta.totalCases.toLocaleString()}</strong>`,
          ];
          if (meta.pctChange !== null) lines.push(`<br/>Change: ${fmtPct(meta.pctChange)}`);
          if (meta.anomalyZ !== null) lines.push(`<br/>Anomaly: ${formatZ(meta.anomalyZ)}`);
          const diseases = meta.diseases.map(d => diseaseLabel(d.disease)).join(', ');
          if (diseases) lines.push(`<br/>Active diseases: ${diseases}`);
          return lines.join('');
        },
      },
      series: [{
        type: 'map',
        map: 'world',
        roam: true,
        zoom: 1.15,
        scaleLimit: { min: 1, max: 6 },
        itemStyle: { areaColor: pal.noData, borderColor: pal.border, borderWidth: 0.5 },
        emphasis: { itemStyle: { areaColor: pal.hover }, label: { show: false } },
        select: { disabled: true },
        label: { show: false },
        data,
      }],
    }, true);
  }

  function renderTrendChart() {
    if (!trendChart || !echarts || !selectedEntry) return;
    const pal = chartPalette();
    const field: keyof OutbreakPoint = trendMetric === 'cases' ? 'case_count' : 'deaths';

    const series = selectedEntry.diseases.map(d => ({
      name: diseaseLabel(d.disease),
      type: 'line',
      data: d.series.map(p => [p.date, p[field]]),
      smooth: 0.4,
      symbol: 'none',
      lineStyle: { color: diseaseColor(d.disease), width: 2 },
      emphasis: { focus: 'series' },
      markPoint: trendMetric === 'cases' ? {
        symbol: 'circle',
        data: d.spikes.map(s => spikeMarkPoint(s, pal)),
        tooltip: { formatter: spikeTooltip(d.spikes) },
      } : undefined,
    }));

    const ripples = trendMetric === 'cases'
      ? selectedEntry.diseases.map(d => criticalRippleSeries(d.spikes))
      : [];

    trendChart.setOption({
      backgroundColor: 'transparent',
      animationDurationUpdate: 500,
      grid: { top: 40, right: 16, bottom: 32, left: 56, containLabel: false },
      tooltip: {
        trigger: 'axis',
        backgroundColor: pal.tooltipBg,
        borderColor: pal.tooltipBorder,
        textStyle: { color: pal.text, fontSize: 12, fontFamily: 'var(--sans)' },
        formatter: (params: any[]) => {
          const date = params[0]?.axisValue ?? '';
          let html = `<div style="margin-bottom:4px;color:${pal.muted};font-size:11px">${date}</div>`;
          for (const p of params) {
            if (p.seriesName === 'critical-pulse') continue;
            const val = Number(p.value?.[1] ?? 0).toLocaleString();
            html += `<div><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${p.color};margin-right:6px"></span>${p.seriesName}: <strong>${val}</strong></div>`;
          }
          return html;
        },
      },
      legend: {
        top: 0, right: 0,
        textStyle: { color: pal.muted, fontSize: 11, fontFamily: 'var(--sans)' },
        itemWidth: 14, itemHeight: 8,
      },
      xAxis: {
        type: 'time',
        axisLine: { lineStyle: { color: pal.axis } },
        splitLine: { show: false },
        axisLabel: { color: pal.muted, fontSize: 11, fontFamily: 'var(--sans)' },
        axisTick: { lineStyle: { color: pal.axis } },
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        splitLine: { lineStyle: { color: pal.grid, type: 'dashed' } },
        axisLabel: {
          color: pal.muted, fontSize: 11, fontFamily: 'var(--sans)',
          formatter: (v: number) => {
            if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
            if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
            return String(v);
          },
        },
      },
      series: [...series, ...ripples],
    }, true);
  }

  function renderCountryChart() {
    if (!countryChart || !echarts || !selectedDiseaseSeries) return;
    const pal = chartPalette();
    const ds = selectedDiseaseSeries;
    const color = diseaseColor(ds.disease);

    countryChart.setOption({
      backgroundColor: 'transparent',
      animationDurationUpdate: 500,
      grid: { top: 16, right: 12, bottom: 28, left: 48, containLabel: false },
      tooltip: {
        trigger: 'axis',
        backgroundColor: pal.tooltipBg,
        borderColor: pal.tooltipBorder,
        textStyle: { color: pal.text, fontSize: 12, fontFamily: 'var(--sans)' },
        formatter: (params: any[]) => {
          const p = params[0];
          if (!p) return '';
          return `<div style="color:${pal.muted};font-size:11px;margin-bottom:2px">${p.axisValue}</div>${Number(p.value[1]).toLocaleString()} cases`;
        },
      },
      xAxis: {
        type: 'time',
        axisLine: { lineStyle: { color: pal.axis } },
        splitLine: { show: false },
        axisLabel: { color: pal.muted, fontSize: 10, fontFamily: 'var(--sans)' },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        splitLine: { lineStyle: { color: pal.grid, type: 'dashed' } },
        axisLabel: {
          color: pal.muted, fontSize: 10, fontFamily: 'var(--sans)',
          formatter: (v: number) => {
            if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
            if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
            return String(v);
          },
        },
      },
      series: [
        {
          type: 'line',
          data: ds.series.map(p => [p.date, p.case_count]),
          smooth: 0.4,
          symbol: 'none',
          lineStyle: { color, width: 2 },
          areaStyle: {
            color: echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: color + 'aa' },
              { offset: 1, color: color + '05' },
            ]),
          },
          markPoint: {
            symbol: 'circle',
            data: ds.spikes.map(s => spikeMarkPoint(s, pal)),
            tooltip: { formatter: spikeTooltip(ds.spikes) },
          },
        },
        criticalRippleSeries(ds.spikes),
      ],
    }, true);
  }

  // ── Reactivity ────────────────────────────────────────────────────────────

  $: if (mapChart && echarts && worldMapReady) {
    mapEntries; selectedCountry; $theme;
    renderMapChart();
  }
  $: if (trendChart && echarts && selectedEntry) {
    trendMetric; $theme;
    renderTrendChart();
  }
  $: if (countryChart && echarts && selectedDiseaseSeries) {
    $theme;
    renderCountryChart();
  }

  // The country-detail chart only mounts once a country is selected (its
  // container lives inside an {#if selectedEntry} block), so it's
  // initialized lazily here rather than alongside the other charts.
  $: if (browser && echarts && countryEl && !countryChart) {
    countryChart = echarts.init(countryEl, null, { renderer: 'canvas' });
    renderCountryChart();
  }

  // Resize charts after the sidebar collapses/expands — skip the initial
  // run (the store's starting value), only react to actual toggles.
  let sidebarReady = false;
  $: if (browser) {
    $sidebarCollapsed;
    if (sidebarReady) {
      setTimeout(() => {
        mapChart?.resize();
        trendChart?.resize();
        countryChart?.resize();
      }, 240);
    } else {
      sidebarReady = true;
    }
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  onMount(() => {
    if (!browser) return;

    const resize = () => { mapChart?.resize(); trendChart?.resize(); countryChart?.resize(); };
    window.addEventListener('resize', resize);

    (async () => {
      echarts = await import('echarts');
      mapChart = echarts.init(mapEl, null, { renderer: 'canvas' });
      trendChart = echarts.init(trendEl, null, { renderer: 'canvas' });

      mapChart.on('click', (params: any) => {
        const meta = params.data?.countryMeta;
        if (meta?.hasData) selectCountry(meta.country);
      });

      await Promise.all([loadAll(), loadAlerts(), loadWorldMap()]);
      await tick();
      renderMapChart();
      renderTrendChart();
    })();

    connectWs();

    return () => window.removeEventListener('resize', resize);
  });

  onDestroy(() => {
    mapChart?.dispose();
    trendChart?.dispose();
    countryChart?.dispose();
    ws?.close();
  });
</script>

<div class="shell">

  <!-- ── Sidebar ───────────────────────────────────────────────────────────── -->
  <Sidebar section="Surveillance" alertCount={alerts.length} />

  <!-- ── Main column ───────────────────────────────────────────────────────── -->
  <div class="main">

    <header class="topbar">
      <button class="icon-btn menu-btn" aria-label="Toggle sidebar" on:click={toggleSidebar}>{@html ICONS.menu}</button>
      <div class="search-box">
        {@html ICONS.search}
        <input
          type="text"
          placeholder="Search disease, country, or region…"
          bind:value={searchQuery}
          on:keydown={handleSearch}
          on:focus={() => searchFocused = true}
          on:blur={() => setTimeout(() => searchFocused = false, 150)}
        />
        <span class="kbd">↵</span>
        {#if searchOpen}
          <div class="search-dropdown">
            {#if searchMatches.length === 0}
              <div class="search-empty">No diseases, countries, or regions match "{searchQuery}"</div>
            {:else}
              {#each searchMatches as m, i (m.kind + m.id)}
                <button class="search-match {i === 0 ? 'top' : ''}" on:mousedown={() => selectSearchMatch(m)}>
                  <span class="search-match-label">{m.label}</span>
                  <span class="search-match-sub">{m.sub}</span>
                </button>
              {/each}
            {/if}
          </div>
        {/if}
      </div>
      <div class="topbar-right">
        <div class="data-updated">
          <span class="ws-dot {wsConnected ? 'connected' : ''}"></span>
          Data updated {lastUpdated ? timeAgo(lastUpdated.toISOString()) : '—'}
        </div>
        <button class="topbar-btn" on:click={shareView}>{@html ICONS.share}<span>{shareCopied ? 'Link copied' : 'Share'}</span></button>
        <button class="topbar-btn" on:click={downloadCurrentView}>{@html ICONS.download}<span>Download</span></button>
        <div class="topbar-action">
          <button class="topbar-btn {filtersOpen ? 'active' : ''}" on:click={() => filtersOpen = !filtersOpen}>{@html ICONS.filter}<span>Filters</span></button>
          {#if filtersOpen}
            <div class="popover-overlay" role="presentation" on:click={() => filtersOpen = false}></div>
            <div class="filters-popover">
              <label class="filter-field">
                <span>Disease</span>
                <select class="quiet-select" bind:value={mapDiseaseFilter}>
                  <option value="all">All Diseases</option>
                  {#each diseases as d}
                    <option value={d.disease_name}>{diseaseLabel(d.disease_name)}</option>
                  {/each}
                </select>
              </label>
              <label class="filter-field">
                <span>Risk Level</span>
                <select class="quiet-select" bind:value={mapRiskFilter}>
                  <option value="all">All Risk Levels</option>
                  {#each Object.entries(RISK_LABELS) as [lvl, label]}
                    <option value={lvl}>{label}</option>
                  {/each}
                </select>
              </label>
              <label class="filter-field">
                <span>Region</span>
                <select class="quiet-select" value={selectedCountry} on:change={onRegionFilterChange}>
                  {#each countryEntries as c}
                    <option value={c.country}>{c.country}</option>
                  {/each}
                </select>
              </label>
              <label class="filter-field">
                <span>Alert Severity</span>
                <select class="quiet-select" bind:value={alertSeverityFilter}>
                  <option value="all">All Severities</option>
                  {#each Object.entries(SEVERITY_LABELS) as [sev, label]}
                    <option value={sev}>{label}</option>
                  {/each}
                </select>
              </label>
            </div>
          {/if}
        </div>
        <button
          class="icon-btn panel-toggle-btn"
          aria-label="Open country intelligence panel"
          on:click={() => panelOpen = true}
        >{@html ICONS.panel}</button>
      </div>
    </header>

    <Ticker />

    <div class="content">
      <div class="content-main">

        <TopTabs tabs={[
          { label: 'Overview', href: '/surveillance' },
          { label: 'Trends', href: '/surveillance/trends' },
          { label: 'Diseases', href: '/surveillance/diseases' },
          { label: 'Alerts', href: '/alerts' },
          { label: 'Reports', href: '/surveillance/reports' },
        ]} />

        {#if loadError}
          <div class="error-banner">{@html ICONS.bell}{loadError}</div>
        {/if}

        <!-- Global Risk Map -->
        <section class="panel">
          <div class="panel-header">
            <h2>Global Risk Map</h2>
            <div class="panel-controls">
              <select class="quiet-select" bind:value={mapDiseaseFilter}>
                <option value="all">All Diseases</option>
                {#each diseases as d}
                  <option value={d.disease_name}>{diseaseLabel(d.disease_name)}</option>
                {/each}
              </select>
              <select class="quiet-select" bind:value={mapRiskFilter}>
                <option value="all">All Risk Levels</option>
                {#each Object.entries(RISK_LABELS) as [lvl, label]}
                  <option value={lvl}>{label}</option>
                {/each}
              </select>
            </div>
          </div>

          <div class="risk-legend">
            <span class="legend-caption">Risk Level</span>
            {#each Object.entries(RISK_LABELS) as [lvl, label]}
              <span class="legend-item">
                <span class="legend-dot" style="background: {riskColor(lvl)}"></span>{label}
              </span>
            {/each}
          </div>

          <div class="map-wrap">
            <div bind:this={mapEl} class="map-canvas"></div>
            {#if loadingData}<div class="loading-bar"></div>{/if}
          </div>

          <div class="stat-row">
            <div class="stat-card">
              {@html ICONS.globe}
              <div>
                <div class="stat-label">Countries Monitoring</div>
                <div class="stat-value">{globalStats.countries}</div>
                <div class="stat-sub">across {diseases.length} diseases</div>
              </div>
            </div>
            <div class="stat-card">
              {@html ICONS.activity}
              <div>
                <div class="stat-label">Active Outbreaks</div>
                <div class="stat-value">{globalStats.activeOutbreaks}</div>
                <div class="stat-sub">HIGH / CRITICAL severity</div>
              </div>
            </div>
            <div class="stat-card">
              {@html ICONS.bell}
              <div>
                <div class="stat-label">High-Risk Regions</div>
                <div class="stat-value">{globalStats.highRisk}</div>
                <div class="stat-sub">of {globalStats.countries} countries</div>
              </div>
            </div>
            <div class="stat-card">
              {@html ICONS.trend}
              <div>
                <div class="stat-label">Avg. Case Growth</div>
                <div class="stat-value {globalStats.avgChange !== null && globalStats.avgChange >= 0 ? 'stat-up' : 'stat-down'}">
                  {fmtPct(globalStats.avgChange)}
                </div>
                <div class="stat-sub">vs. previous period</div>
              </div>
            </div>
            <div class="stat-card">
              {@html ICONS.database}
              <div>
                <div class="stat-label">Records Analyzed</div>
                <div class="stat-value">{fmt(globalStats.records)}</div>
                <div class="stat-sub">{SPIKE_BASELINE_MONTHS}-month baseline window</div>
              </div>
            </div>
          </div>
        </section>

        <!-- Disease Trends + Top Hotspots -->
        <div class="panel-row">
          <section class="panel trends-panel">
            <div class="panel-header">
              <h2>Disease Trends — {selectedCountry || '—'}</h2>
              <div class="metric-toggle">
                <button class:active={trendMetric === 'cases'} on:click={() => trendMetric = 'cases'}>Cases</button>
                <button class:active={trendMetric === 'deaths'} on:click={() => trendMetric = 'deaths'}>Deaths</button>
              </div>
            </div>
            <div class="chart-wrap">
              <div bind:this={trendEl} class="echarts-container chart-trends"></div>
            </div>
            <a class="panel-link inert" href="/surveillance">View all disease trends {@html ICONS.arrowRight}</a>
          </section>

          <section class="panel hotspots-panel">
            <div class="panel-header">
              <h2>Top Emerging Hotspots</h2>
            </div>
            <div class="hotspot-list">
              {#each topHotspots as h, i (h.country + h.disease)}
                <button class="hotspot-row" on:click={() => { selectCountry(h.country); selectedCountryDisease = h.disease; }}>
                  <span class="hotspot-rank">{i + 1}</span>
                  <div class="hotspot-info">
                    <div class="hotspot-name">{h.country}</div>
                    <div class="hotspot-disease">{diseaseLabel(h.disease)}</div>
                  </div>
                  <div class="hotspot-bar-wrap">
                    <div class="hotspot-bar" style="width: {Math.min(100, h.riskScore)}%; background: {SEVERITY_COLORS[h.topSpike?.severity ?? 'LOW']}"></div>
                  </div>
                  <div class="hotspot-score">{h.riskScore}<span>/100</span></div>
                </button>
              {/each}
              {#if topHotspots.length === 0}
                <div class="empty-note">No anomalies detected yet.</div>
              {/if}
            </div>
            <a class="panel-link inert" href="/surveillance">View all hotspots {@html ICONS.arrowRight}</a>
          </section>
        </div>

      </div>

      <!-- ── Country detail panel ────────────────────────────────────────── -->
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
        {#if selectedEntry}
          {@const entry = selectedEntry}
          <div class="detail-header">
            <h2>{entry.country}</h2>
          </div>

          <div class="risk-score-block">
            <div class="risk-label">Risk Score</div>
            <div class="risk-score">
              <span class="risk-number">{entry.riskScore}</span><span class="risk-max">/100</span>
            </div>
            <div class="risk-level" style="color: {RISK_COLORS[entry.riskLevel]}">{RISK_LABELS[entry.riskLevel]} Risk</div>
          </div>

          <div class="detail-grid">
            <div class="detail-cell">
              <div class="detail-label">Latest Cases</div>
              <div class="detail-value">{fmt(entry.totalCases)}</div>
            </div>
            <div class="detail-cell">
              <div class="detail-label">Period Change</div>
              <div class="detail-value {entry.pctChange !== null && entry.pctChange >= 0 ? 'stat-up' : 'stat-down'}">{fmtPct(entry.pctChange)}</div>
            </div>
            <div class="detail-cell">
              <div class="detail-label">Anomaly (z-score)</div>
              <div class="detail-value">{formatZ(entry.anomalyZ)}</div>
            </div>
            <div class="detail-cell">
              <div class="detail-label">Active Outbreaks</div>
              <div class="detail-value">{entry.diseases.filter(d => d.topSpike && (d.topSpike.severity === 'HIGH' || d.topSpike.severity === 'CRITICAL')).length}</div>
            </div>
          </div>

          <div class="detail-section">
            <div class="detail-section-title">Active Diseases</div>
            <div class="disease-table">
              <div class="disease-table-head">
                <span>Disease</span><span>Cases</span><span>Change</span><span>Trend</span>
              </div>
              {#each entry.diseases as d (d.disease)}
                <button class="disease-row {selectedCountryDisease === d.disease ? 'active' : ''}" on:click={() => selectedCountryDisease = d.disease}>
                  <span class="disease-name">
                    <span class="disease-dot" style="background: {diseaseColor(d.disease)}"></span>
                    {diseaseLabel(d.disease)}
                  </span>
                  <span class="disease-cases">{fmt(d.latestCases)}</span>
                  <span class="disease-change {d.pctChange !== null && d.pctChange >= 0 ? 'stat-up' : 'stat-down'}">{fmtPct(d.pctChange)}</span>
                  <svg class="sparkline" viewBox="0 0 64 24" preserveAspectRatio="none">
                    <path d={sparklinePath(d.series)} fill="none" stroke={diseaseColor(d.disease)} stroke-width="1.5" />
                  </svg>
                </button>
              {/each}
            </div>
          </div>

          <div class="detail-section">
            <div class="detail-section-title">
              Cases Over Time
              <span class="detail-section-sub">{diseaseLabel(selectedCountryDisease)}</span>
            </div>
            <div class="chart-wrap small">
              <div bind:this={countryEl} class="echarts-container chart-country"></div>
            </div>
          </div>

          <div class="detail-section">
            <div class="detail-section-title-row">
              <div class="detail-section-title">Recent Alerts</div>
              <button class="text-btn" on:click={scanSelected} disabled={scanning}>
                {@html ICONS.refresh}{scanning ? 'Scanning…' : 'Run scan'}
              </button>
            </div>
            {#if scanMessage}<div class="scan-msg">{scanMessage}</div>{/if}
            <div class="alert-list">
              {#each alerts.filter(a => a.region === entry.country && (alertSeverityFilter === 'all' || a.severity === alertSeverityFilter)).slice(0, 5) as a (a.id)}
                <div
                  class="alert-item {newAlertIds.has(a.id) ? (a.severity === 'HIGH' || a.severity === 'CRITICAL' ? 'alert-pulse' : 'alert-fade') : ''}"
                  style="--sev: {SEVERITY_COLORS[a.severity]}"
                >
                  <div class="alert-top">
                    <span class="alert-sev" style="color: {SEVERITY_COLORS[a.severity]}">{a.severity}</span>
                    <span class="alert-time">{timeAgo(a.created_at)}</span>
                  </div>
                  <div class="alert-msg">{a.message}</div>
                </div>
              {/each}
              {#if alerts.filter(a => a.region === entry.country && (alertSeverityFilter === 'all' || a.severity === alertSeverityFilter)).length === 0}
                <div class="empty-note">No {alertSeverityFilter === 'all' ? '' : SEVERITY_LABELS[alertSeverityFilter].toLowerCase() + ' '}alerts for {entry.country} yet.</div>
              {/if}
            </div>
          </div>

          <div class="detail-section">
            <div class="detail-section-title">Recommended Actions</div>
            <ul class="action-list">
              {#each recommendedActions as action}
                <li>{action}</li>
              {/each}
            </ul>
          </div>

          <a class="full-report-btn inert" href="/surveillance">View Full Country Report {@html ICONS.arrowRight}</a>
        {:else}
          <div class="empty-note">Loading country data…</div>
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
    position: relative;
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
    padding: 10px 12px;
    font-size: 0.83rem;
    color: var(--text-faint);
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
    gap: 10px;
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
  .panel-controls { display: flex; gap: 8px; }
  .quiet-select {
    background: var(--bg-sunken);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 5px 8px;
    font-family: var(--sans);
    font-size: 0.78rem;
    color: var(--text-muted);
    cursor: pointer;
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
  .loading-bar {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--border);
    overflow: hidden;
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
    font-family: var(--sans);
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum';
    font-size: 1.35rem;
    font-weight: 600;
    margin-top: 3px;
    color: var(--text);
  }
  .stat-sub { font-size: 0.7rem; color: var(--text-faint); margin-top: 2px; }
  .stat-up { color: var(--success); }
  .stat-down { color: var(--danger); }

  /* ── Trends + hotspots row ────────────────────────────────────────────── */

  .panel-row {
    display: flex;
    gap: 16px;
    align-items: stretch;
  }
  .trends-panel { flex: 1.7; min-width: 0; display: flex; flex-direction: column; }
  .hotspots-panel { flex: 1; min-width: 0; display: flex; flex-direction: column; }

  .metric-toggle {
    display: flex;
    background: var(--bg-sunken);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 2px;
  }
  .metric-toggle button {
    padding: 4px 12px;
    border: none;
    background: transparent;
    color: var(--text-muted);
    font-family: var(--sans);
    font-size: 0.78rem;
    border-radius: 4px;
    cursor: pointer;
  }
  .metric-toggle button.active {
    background: var(--bg-panel);
    color: var(--text);
  }

  .chart-wrap { height: 280px; }
  .chart-wrap.small { height: 150px; }
  .echarts-container { width: 100%; height: 100%; }

  .panel-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-top: 12px;
    font-size: 0.78rem;
    color: var(--accent);
    text-decoration: none;
  }
  .panel-link :global(svg) { width: 13px; height: 13px; }
  .panel-link.inert { color: var(--text-faint); pointer-events: none; }

  .hotspot-list { display: flex; flex-direction: column; gap: 6px; flex: 1; }
  .hotspot-row {
    display: grid;
    grid-template-columns: 20px 1fr 60px 48px;
    align-items: center;
    gap: 10px;
    padding: 9px 8px;
    border-radius: 6px;
    border: none;
    background: transparent;
    font-family: var(--sans);
    text-align: left;
    cursor: pointer;
    width: 100%;
  }
  .hotspot-row:hover { background: var(--bg-hover); }
  .hotspot-rank { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; font-size: 0.75rem; color: var(--text-faint); text-align: center; }
  .hotspot-info { min-width: 0; }
  .hotspot-name {
    font-size: 0.83rem;
    font-weight: 500;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .hotspot-disease { font-size: 0.7rem; color: var(--text-muted); }
  .hotspot-bar-wrap { height: 4px; border-radius: 2px; background: var(--border); overflow: hidden; }
  .hotspot-bar { height: 100%; border-radius: 2px; transition: width 0.4s ease; }
  .hotspot-score { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; font-size: 0.83rem; font-weight: 600; color: var(--text); text-align: right; }
  .hotspot-score span { color: var(--text-faint); font-weight: 400; font-size: 0.7rem; }

  .empty-note { font-size: 0.8rem; color: var(--text-faint); padding: 16px 8px; text-align: center; }

  /* ── Country detail panel ─────────────────────────────────────────────── */

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
  .risk-score { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; margin-top: 6px; }
  .risk-number { font-size: 2.4rem; font-weight: 700; color: var(--text); }
  .risk-max { font-size: 1rem; color: var(--text-faint); }
  .risk-level { font-size: 0.83rem; font-weight: 600; margin-top: 4px; }

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
  .detail-value { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; font-size: 1.05rem; font-weight: 600; margin-top: 4px; color: var(--text); }

  .detail-section { padding-top: 14px; border-top: 1px solid var(--border-soft); }
  .detail-section-title {
    font-size: 0.6875rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
  }
  .detail-section-sub {
    text-transform: none;
    font-weight: 400;
    color: var(--text-faint);
    letter-spacing: normal;
    margin-left: 6px;
  }
  .detail-section-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .detail-section-title-row .detail-section-title { margin-bottom: 0; }

  .disease-table { display: flex; flex-direction: column; gap: 2px; }
  .disease-table-head,
  .disease-row {
    display: grid;
    grid-template-columns: 1fr 52px 48px 52px;
    align-items: center;
    gap: 8px;
  }
  .disease-table-head {
    font-size: 0.6875rem;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 0 8px 4px;
  }
  .disease-table-head span:not(:first-child) { text-align: right; }
  .disease-row {
    border: none;
    background: transparent;
    border-radius: 6px;
    padding: 7px 8px;
    font-family: var(--sans);
    cursor: pointer;
    text-align: left;
  }
  .disease-row:hover { background: var(--bg-hover); }
  .disease-row.active { background: var(--accent-soft); }
  .disease-name { display: flex; align-items: center; gap: 7px; font-size: 0.8rem; color: var(--text); min-width: 0; }
  .disease-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .disease-cases { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; font-size: 0.8rem; color: var(--text); text-align: right; }
  .disease-change { font-family: var(--sans); font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; font-size: 0.74rem; text-align: right; }
  .sparkline { width: 48px; height: 20px; justify-self: end; }

  .text-btn {
    display: flex;
    align-items: center;
    gap: 5px;
    border: none;
    background: transparent;
    color: var(--accent);
    font-family: var(--sans);
    font-size: 0.74rem;
    cursor: pointer;
    padding: 0;
  }
  .text-btn:disabled { color: var(--text-faint); cursor: default; }
  .text-btn :global(svg) { width: 12px; height: 12px; }
  .text-btn:disabled :global(svg) { animation: spin 1s linear infinite; }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .scan-msg { font-size: 0.74rem; color: var(--accent); margin-bottom: 8px; }

  .alert-list { display: flex; flex-direction: column; gap: 6px; }
  .alert-item {
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    border-left: 3px solid var(--sev, var(--border));
    border-radius: 6px;
    padding: 8px 10px;
  }
  .alert-top { display: flex; justify-content: space-between; align-items: center; }
  .alert-sev { font-size: 0.6875rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  .alert-time { font-size: 0.66rem; color: var(--text-faint); font-family: var(--mono); }
  .alert-msg { font-size: 0.78rem; color: var(--text); margin-top: 4px; line-height: 1.4; }

  .alert-fade { animation: alertFade 0.4s ease-out; }
  .alert-pulse { animation: alertFade 0.4s ease-out, alertPulse 0.7s ease-out 2; }
  @keyframes alertFade {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes alertPulse {
    0% { box-shadow: 0 0 0 0 var(--sev); }
    70% { box-shadow: 0 0 0 6px transparent; }
    100% { box-shadow: 0 0 0 0 transparent; }
  }

  .action-list {
    margin: 0;
    padding-left: 1.1rem;
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 0.8rem;
    color: var(--text-muted);
    line-height: 1.45;
  }
  .action-list li::marker { color: var(--accent); }

  .full-report-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 10px;
    border-radius: 6px;
    border: 1px solid var(--border);
    color: var(--text-muted);
    text-decoration: none;
    font-size: 0.83rem;
  }
  .full-report-btn :global(svg) { width: 14px; height: 14px; }
  .full-report-btn.inert { opacity: 0.5; pointer-events: none; }

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
  }
</style>
