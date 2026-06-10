<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { browser } from '$app/environment';

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

  type SummaryRow = {
    disease_name: string;
    total_cases: number;
    total_deaths: number;
    peak_cases: number;
    peak_date: string | null;
    record_count: number;
  };

  type HotspotCluster = {
    cluster_id: number;
    centroid_lat: number;
    centroid_lon: number;
    total_cases: number;
    report_count: number;
    radius_km: number;
    member_ids: number[];
  };

  type HotspotResponse = {
    clusters: HotspotCluster[];
    noise_points: HotspotCluster[];
    eps_km: number;
    min_pts: number;
    report_count: number;
    cluster_count: number;
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

  // ── State ──────────────────────────────────────────────────────────────────

  const API = 'http://localhost:8000/surveillance';

  // Disease colours: meaningful mapping — red for high-fatality diseases,
  // amber for vector-borne, cyan for water-borne, orange for highly contagious.
  const DISEASE_COLORS: Record<string, string> = {
    covid_19:    '#f59e0b',   // amber — respiratory, highly transmissible
    measles:     '#ef4444',   // red — high death toll historically
    dengue:      '#06b6d4',   // cyan — vector-borne (mosquito)
    cholera:     '#a78bfa',   // purple — water-borne
  };

  const DISEASE_LABELS: Record<string, string> = {
    covid_19: 'COVID-19',
    measles:  'Measles',
    dengue:   'Dengue',
    cholera:  'Cholera',
  };

  // Severity scale — meaningful, never decorative: green -> red as B3 alerts escalate.
  const SEVERITY_COLORS: Record<Severity, string> = {
    LOW:      '#22c55e',
    MEDIUM:   '#f59e0b',
    HIGH:     '#f97316',
    CRITICAL: '#ef4444',
  };
  const SEVERITY_MARK_SIZE: Record<Severity, number> = {
    LOW: 8, MEDIUM: 11, HIGH: 14, CRITICAL: 18,
  };

  let diseases: DiseaseInfo[] = [];
  let summaryRows: SummaryRow[] = [];
  let selectedDisease = 'covid_19';
  let selectedRegion  = 'India';
  let seriesData: OutbreakPoint[] = [];
  let regions: string[] = [];

  // Play state — controlled via dispatchAction on the ECharts dataZoom
  let isPlaying = false;
  let playTimer: ReturnType<typeof setInterval> | null = null;

  // View toggle — 'timeseries' | 'hotspots'
  let view: 'timeseries' | 'hotspots' = 'timeseries';

  // Hotspot clustering state
  let epsKm: number = 2.0;
  let minPts: number = 3;
  let hotspotData: HotspotResponse = {
    clusters: [], noise_points: [], eps_km: 2.0, min_pts: 3,
    report_count: 0, cluster_count: 0,
  };

  // Spike detection / alert feed state (B3)
  let spikes: SpikeDetection[] = [];
  let alerts: AlertRow[] = [];
  let newAlertIds = new Set<number>();
  let scanning = false;
  let scanMessage: string | null = null;
  let ws: WebSocket | null = null;
  let wsConnected = false;

  // ECharts — browser-only; never touches SSR
  let chartEl: HTMLDivElement;
  let chart: any = null;
  let echarts: any = null;
  let hotspotChartEl: HTMLDivElement;
  let hotspotChart: any = null;

  // ── Data fetching ──────────────────────────────────────────────────────────

  async function loadDiseases() {
    const r = await fetch(`${API}/diseases`);
    diseases = await r.json();
    // Prefer covid_19 on first load; fall back to first disease returned.
    if (!diseases.find(x => x.disease_name === selectedDisease)) {
      selectedDisease = diseases[0]?.disease_name ?? selectedDisease;
    }
    const d = diseases.find(x => x.disease_name === selectedDisease);
    if (d) {
      regions = d.regions;
      // Always set selectedRegion from the authoritative regions list.
      // Prefer 'India' if it exists, otherwise take the first region.
      // This must run unconditionally — never leave selectedRegion as an
      // initial guess that the DOM's empty <select> may have already reset.
      selectedRegion = regions.includes('India') ? 'India' : (regions[0] ?? '');
    }
  }

  async function loadSummary() {
    const r = await fetch(`${API}/summary`);
    summaryRows = await r.json();
  }

  async function loadTimeSeries() {
    if (!selectedDisease || !selectedRegion) return;
    const url = `${API}/timeseries?disease=${encodeURIComponent(selectedDisease)}&region=${encodeURIComponent(selectedRegion)}`;
    const r = await fetch(url);
    seriesData = await r.json();
    await loadSpikes();
    renderChart();
  }

  // ── Spike detection + alert feed (B3) ──────────────────────────────────────

  // Read-only preview of the z-score detector for the current series — used
  // to mark spikes on the chart.  No alerts are created by this call.
  async function loadSpikes() {
    if (!selectedDisease || !selectedRegion) { spikes = []; return; }
    const url = `${API}/spikes?disease=${encodeURIComponent(selectedDisease)}&region=${encodeURIComponent(selectedRegion)}`;
    const r = await fetch(url);
    spikes = r.ok ? await r.json() : [];
  }

  async function loadAlerts() {
    const r = await fetch('http://localhost:8000/alerts?limit=30');
    if (r.ok) alerts = await r.json();
  }

  // Runs the detector, persists severity-tiered alerts, and emits
  // AlertGenerated for any new ones (also picked up live via the WebSocket).
  async function scanForSpikes() {
    if (!selectedDisease || !selectedRegion || scanning) return;
    scanning = true;
    scanMessage = null;
    try {
      const url = `${API}/scan?disease=${encodeURIComponent(selectedDisease)}&region=${encodeURIComponent(selectedRegion)}`;
      const r = await fetch(url, { method: 'POST' });
      if (!r.ok) {
        scanMessage = 'scan failed';
        return;
      }
      const body: ScanResponse = await r.json();
      scanMessage = `${body.detections.length} detection(s) · ${body.new_alerts.length} new alert(s)`;
      for (const a of body.new_alerts) {
        addAlert(a);
      }
      await loadSpikes();
      renderChart();
    } finally {
      scanning = false;
    }
  }

  // Insert a new alert at the top of the feed (deduped by id) and trigger
  // its severity-pulse animation.
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

  // ── Live feed WebSocket ───────────────────────────────────────────────────

  function connectWs() {
    ws = new WebSocket('ws://localhost:8000/ws');
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

  // SENTINEL_Z (999) means "far above baseline, std==0" — show as ">5σ"
  // rather than the raw sentinel number.
  function formatZ(z: number | null): string {
    if (z === null) return '';
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

  // ── ECharts rendering ──────────────────────────────────────────────────────
  //
  // Why onMount + browser guard?  ECharts is a browser-only library — it reads
  // the DOM immediately on import.  SvelteKit prerenders pages on the server
  // (SSR), so any top-level ECharts import would crash node.  The pattern:
  //   1. import('echarts') inside onMount() — deferred to browser execution
  //   2. guard with `if (browser)` — belt-and-suspenders for SSR safety
  //
  // Why dispatchAction for the play control rather than rebuilding the option?
  // dispatchAction({ type: 'dataZoom', endValue: ... }) updates the visible
  // window without re-diffing the entire option tree, so the animation is
  // smooth at 100ms steps.

  function renderChart() {
    if (!chart || !echarts || seriesData.length === 0) return;

    stopPlay();

    const color = DISEASE_COLORS[selectedDisease] ?? '#94a3b8';
    const label = DISEASE_LABELS[selectedDisease] ?? selectedDisease;

    const data = seriesData.map(p => [p.date, p.case_count]);
    const deathData = seriesData.map(p => [p.date, p.deaths]);

    chart.setOption({
      backgroundColor: 'transparent',
      animation: true,
      animationDuration: 600,
      grid: { top: 60, right: 24, bottom: 90, left: 72, containLabel: false },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#1c2128',
        borderColor: '#30363d',
        textStyle: { color: '#e2e8f0', fontSize: 12 },
        formatter: (params: any[]) => {
          const date = params[0].axisValue;
          let html = `<div style="margin-bottom:4px;color:#94a3b8;font-size:11px">${date}</div>`;
          for (const p of params) {
            const val = Number(p.value[1]).toLocaleString();
            html += `<div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:6px"></span>${p.seriesName}: <strong>${val}</strong></div>`;
          }
          return html;
        },
      },
      legend: {
        top: 8,
        right: 24,
        textStyle: { color: '#94a3b8', fontSize: 11 },
        itemWidth: 14,
        itemHeight: 8,
      },
      xAxis: {
        type: 'time',
        axisLine: { lineStyle: { color: '#30363d' } },
        splitLine: { show: false },
        axisLabel: { color: '#6b7280', fontSize: 11 },
        axisTick: { lineStyle: { color: '#30363d' } },
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        splitLine: { lineStyle: { color: '#1c2128', type: 'dashed' } },
        axisLabel: {
          color: '#6b7280',
          fontSize: 11,
          formatter: (v: number) => {
            if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
            if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
            return String(v);
          },
        },
      },
      dataZoom: [
        {
          type: 'slider',
          bottom: 10,
          height: 22,
          borderColor: '#30363d',
          backgroundColor: '#0d1117',
          dataBackground: {
            lineStyle: { color: color, opacity: 0.3 },
            areaStyle: { color: color, opacity: 0.08 },
          },
          selectedDataBackground: {
            lineStyle: { color: color, opacity: 0.6 },
            areaStyle: { color: color, opacity: 0.2 },
          },
          fillerColor: 'rgba(255,255,255,0.04)',
          handleStyle: { color: color },
          moveHandleStyle: { color: color },
          textStyle: { color: '#6b7280', fontSize: 10 },
          // Start playing from the first 20% of the data window
          start: 0,
          end: 20,
        },
        { type: 'inside', zoomOnMouseWheel: true, moveOnMouseMove: true },
      ],
      series: [
        {
          name: `${label} — cases`,
          type: 'line',
          data,
          smooth: 0.4,
          symbol: 'none',
          lineStyle: { color, width: 2 },
          areaStyle: {
            color: echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: color + 'cc' },
              { offset: 1, color: color + '08' },
            ]),
          },
          emphasis: { disabled: true },
          // B3: severity-colored markers on detected spike dates — the
          // detection made visible against the curve that triggered it.
          markPoint: {
            symbol: 'circle',
            data: spikes.map(s => ({
              name: s.severity,
              coord: [s.date, s.value],
              symbolSize: SEVERITY_MARK_SIZE[s.severity] ?? 8,
              itemStyle: {
                color: SEVERITY_COLORS[s.severity] ?? '#94a3b8',
                borderColor: '#0d1117',
                borderWidth: 1.5,
              },
              label: { show: false },
            })),
            tooltip: {
              formatter: (params: any) => {
                const s: SpikeDetection | undefined = spikes.find(
                  sp => sp.date === params.data.coord[0] && sp.value === params.data.coord[1]
                );
                if (!s) return params.name;
                return `<div style="color:${SEVERITY_COLORS[s.severity]};font-weight:700;margin-bottom:4px">${s.severity} spike</div>`
                  + `${s.date}<br/>cases: <strong>${s.value.toLocaleString()}</strong><br/>`
                  + `z-score: <strong>${s.z_score.toFixed(2)}</strong> (baseline μ=${s.rolling_mean.toLocaleString()}, σ=${s.rolling_std.toLocaleString()})`;
              },
            },
          },
        },
        {
          name: `${label} — deaths`,
          type: 'line',
          data: deathData,
          smooth: 0.4,
          symbol: 'none',
          lineStyle: { color: '#ef4444', width: 1.5, type: 'dashed' },
          areaStyle: { color: 'transparent' },
          emphasis: { disabled: true },
        },
      ],
    }, true); // true = merge=false (full replace keeps things clean)
  }

  // ── Play control ──────────────────────────────────────────────────────────
  //
  // Advances the dataZoom end value by ~2% every 120ms.  This creates the
  // "OWID play through time" feel: the chart reveals data progressively.
  // The scrubber also updates so the user can see progress at a glance.

  function togglePlay() {
    isPlaying ? stopPlay() : startPlay();
  }

  function startPlay() {
    if (!chart) return;
    isPlaying = true;
    playTimer = setInterval(() => {
      const opt = chart.getOption() as any;
      const dz = opt.dataZoom?.[0];
      if (!dz) return;
      const currentEnd = dz.end as number;
      if (currentEnd >= 100) {
        // Wrap back to start for loop effect
        chart.dispatchAction({ type: 'dataZoom', dataZoomIndex: 0, start: 0, end: 20 });
        return;
      }
      const newEnd = Math.min(100, currentEnd + 2);
      chart.dispatchAction({ type: 'dataZoom', dataZoomIndex: 0, end: newEnd });
    }, 120);
  }

  function stopPlay() {
    if (playTimer !== null) {
      clearInterval(playTimer);
      playTimer = null;
    }
    isPlaying = false;
  }

  // ── Reactivity ────────────────────────────────────────────────────────────

  function onDiseaseChange() {
    stopPlay();
    const d = diseases.find(x => x.disease_name === selectedDisease);
    regions = d?.regions ?? [];
    // Same preference as initial load: keep India when available.
    selectedRegion = regions.includes('India') ? 'India' : (regions[0] ?? '');
    loadTimeSeries();
  }

  // Named handler so the TypeScript cast stays in the <script> block —
  // Svelte's template parser does not process TS syntax in inline expressions.
  function handleRegionChange(e: Event) {
    selectedRegion = (e.currentTarget as HTMLSelectElement).value;
    onRegionChange();
  }

  function onRegionChange() {
    stopPlay();
    loadTimeSeries();
  }

  // ── Hotspot map ───────────────────────────────────────────────────────────

  async function loadHotspots() {
    const disease = selectedDisease ? `&disease=${encodeURIComponent(selectedDisease)}` : '';
    const url = `${API}/hotspots?eps_km=${epsKm}&min_pts=${minPts}${disease}`;
    const r = await fetch(url);
    hotspotData = await r.json();
    renderHotspotChart();
  }

  function renderHotspotChart() {
    if (!hotspotChart || !echarts) return;
    const { clusters, noise_points } = hotspotData;
    const color = DISEASE_COLORS[selectedDisease] ?? '#f59e0b';

    // Scale circle size by sqrt(total_cases) so large clusters are visible
    // but don't eclipse the whole map.
    const maxCases = Math.max(1, ...clusters.map(c => c.total_cases));
    const scale = (cases: number) => Math.max(8, Math.sqrt(cases / maxCases) * 60);

    hotspotChart.setOption({
      backgroundColor: 'transparent',
      animation: true,
      animationDuration: 500,
      grid: { top: 30, right: 20, bottom: 50, left: 60, containLabel: true },
      tooltip: {
        trigger: 'item',
        backgroundColor: '#1c2128',
        borderColor: '#30363d',
        textStyle: { color: '#e2e8f0', fontSize: 12 },
        formatter: (params: any) => {
          const v = params.value as number[];
          if (params.seriesName === 'noise') {
            return `<div style="color:#4b5563;font-size:11px;margin-bottom:4px">Isolated report (noise)</div>`
              + `Cases: <strong>${v[2].toLocaleString()}</strong><br/>`
              + `Lat: ${v[1].toFixed(4)} · Lon: ${v[0].toFixed(4)}`;
          }
          return `<div style="color:${color};font-size:11px;margin-bottom:4px">Hotspot cluster</div>`
            + `<strong>${v[3]} reports → 1 cluster</strong><br/>`
            + `Total cases: <strong>${v[2].toLocaleString()}</strong><br/>`
            + `Radius: ${v[4]} km`;
        },
      },
      xAxis: {
        name: 'Longitude',
        nameTextStyle: { color: '#4b5563', fontSize: 10 },
        type: 'value',
        min: 72.75,
        max: 73.40,
        axisLine: { lineStyle: { color: '#30363d' } },
        splitLine: { lineStyle: { color: '#1c2128' } },
        axisLabel: { color: '#6b7280', fontSize: 10, formatter: (v: number) => v.toFixed(2) },
      },
      yAxis: {
        name: 'Latitude',
        nameTextStyle: { color: '#4b5563', fontSize: 10 },
        type: 'value',
        min: 18.60,
        max: 19.50,
        axisLine: { lineStyle: { color: '#30363d' } },
        splitLine: { lineStyle: { color: '#1c2128' } },
        axisLabel: { color: '#6b7280', fontSize: 10, formatter: (v: number) => v.toFixed(2) },
      },
      series: [
        {
          name: 'cluster',
          type: 'scatter',
          data: clusters.map(c => [c.centroid_lon, c.centroid_lat, c.total_cases, c.report_count, c.radius_km]),
          symbolSize: (val: number[]) => scale(val[2]),
          itemStyle: { color, opacity: 0.55, borderColor: color, borderWidth: 1 },
          emphasis: { itemStyle: { opacity: 0.85 } },
          zlevel: 2,
        },
        {
          name: 'noise',
          type: 'scatter',
          symbol: 'diamond',
          data: noise_points.map(n => [n.centroid_lon, n.centroid_lat, n.total_cases]),
          symbolSize: 9,
          itemStyle: { color: '#374151', opacity: 0.9, borderColor: '#6b7280', borderWidth: 1 },
          emphasis: { itemStyle: { opacity: 1 } },
          zlevel: 3,
        },
      ],
    }, true);
  }

  async function handleViewChange(newView: 'timeseries' | 'hotspots') {
    if (newView === view) return;
    view = newView;
    await tick();
    if (newView === 'hotspots') {
      hotspotChart?.dispose();
      hotspotChart = echarts.init(hotspotChartEl, null, { renderer: 'canvas' });
      await loadHotspots();
    } else {
      chart?.resize();
    }
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  // onMount must be synchronous to return a cleanup function that TypeScript
  // and Svelte both accept.  Async work runs in an IIFE so the cleanup can
  // be returned immediately without wrapping in a Promise.
  onMount(() => {
    if (!browser) return;

    const resize = () => { chart?.resize(); hotspotChart?.resize(); };
    window.addEventListener('resize', resize);

    // Deferred import — keeps ECharts out of SSR entirely (ssr=false in
    // +page.ts also prevents SSR, but the guard is belt-and-suspenders).
    (async () => {
      echarts = await import('echarts');
      chart = echarts.init(chartEl, null, { renderer: 'canvas' });
      await Promise.all([loadDiseases(), loadSummary(), loadAlerts()]);
      // tick() flushes Svelte's pending DOM updates — specifically the <select>
      // options re-render — before loadTimeSeries() reads selectedRegion.
      await tick();
      await loadTimeSeries();
    })();

    connectWs();

    return () => window.removeEventListener('resize', resize);
  });

  onDestroy(() => {
    stopPlay();
    chart?.dispose();
    hotspotChart?.dispose();
    ws?.close();
  });

  // ── Formatting helpers ────────────────────────────────────────────────────

  function fmt(n: number): string {
    if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toLocaleString();
  }

  function diseaseLabel(slug: string): string {
    return DISEASE_LABELS[slug] ?? slug;
  }

  function diseaseColor(slug: string): string {
    return DISEASE_COLORS[slug] ?? '#94a3b8';
  }
</script>

<!-- ── Layout ──────────────────────────────────────────────────────────────── -->

<div class="page">

  <!-- header nav -->
  <header class="topbar">
    <div class="brand">EpiWatch <span class="pill">Surveillance</span></div>
    <nav>
      <a href="/">Live Feed</a>
      <span class="active">Outbreak History</span>
    </nav>
  </header>

  <!-- main content: two-column command-center layout -->
  <div class="layout">

    <!-- LEFT: controls + stat cards -->
    <aside class="sidebar">
      <section class="controls">
        <!-- View toggle -->
        <div class="view-toggle">
          <button
            class="vtab {view === 'timeseries' ? 'active' : ''}"
            on:click={() => handleViewChange('timeseries')}
          >Time Series</button>
          <button
            class="vtab {view === 'hotspots' ? 'active' : ''}"
            on:click={() => handleViewChange('hotspots')}
          >Hotspot Map</button>
        </div>

        <label class="field-label mt">Disease</label>
        <div class="disease-list">
          {#each diseases as d}
            <button
              class="disease-btn {selectedDisease === d.disease_name ? 'active' : ''}"
              style="--accent: {diseaseColor(d.disease_name)}"
              on:click={() => {
                selectedDisease = d.disease_name;
                if (view === 'timeseries') onDiseaseChange();
                else loadHotspots();
              }}
            >
              <span class="dot" style="background: {diseaseColor(d.disease_name)}"></span>
              {diseaseLabel(d.disease_name)}
            </button>
          {/each}
        </div>

        {#if view === 'timeseries'}
          <label class="field-label mt">Region</label>
          <select on:change={handleRegionChange} class="select">
            {#each regions as r}
              <option value={r} selected={r === selectedRegion}>{r}</option>
            {/each}
          </select>

          <div class="play-row">
            <button class="play-btn {isPlaying ? 'playing' : ''}" on:click={togglePlay}>
              {#if isPlaying}
                <span class="icon">⏸</span> Pause
              {:else}
                <span class="icon">▶</span> Play
              {/if}
            </button>
            <span class="play-hint">scrubs through time</span>
          </div>
        {:else}
          <label class="field-label mt">Cluster radius (ε km)</label>
          <input
            type="number"
            class="select"
            min="0.5"
            max="20"
            step="0.5"
            bind:value={epsKm}
            on:change={loadHotspots}
          />
          <label class="field-label mt">Min reports (minPts)</label>
          <input
            type="number"
            class="select"
            min="1"
            max="50"
            step="1"
            bind:value={minPts}
            on:change={loadHotspots}
          />
          {#if hotspotData.report_count > 0}
            <div class="hotspot-meta">
              <span class="meta-val">{hotspotData.report_count.toLocaleString()}</span> reports →
              <span class="meta-val" style="color: {diseaseColor(selectedDisease)}">{hotspotData.cluster_count}</span> clusters ·
              <span class="meta-val" style="color:#6b7280">{hotspotData.noise_points.length}</span> noise
            </div>
          {/if}
        {/if}
      </section>

      <!-- Headline stat cards (one per disease) -->
      <section class="stat-cards">
        <div class="cards-label">All diseases · cumulative</div>
        {#each summaryRows as s}
          <div class="stat-card">
            <div class="stat-disease" style="color: {diseaseColor(s.disease_name)}">
              {diseaseLabel(s.disease_name)}
            </div>
            <div class="stat-row">
              <div class="stat-block">
                <div class="stat-value">{fmt(s.total_cases)}</div>
                <div class="stat-key">cases</div>
              </div>
              <div class="stat-block">
                <div class="stat-value red">{fmt(s.total_deaths)}</div>
                <div class="stat-key">deaths</div>
              </div>
              <div class="stat-block">
                <div class="stat-value">{fmt(s.peak_cases)}</div>
                <div class="stat-key">peak</div>
              </div>
            </div>
            {#if s.peak_date}
              <div class="stat-peak-date">peak: {s.peak_date}</div>
            {/if}
          </div>
        {/each}
        <div class="source-attr">
          Data: <a href="https://ourworldindata.org/" target="_blank" rel="noreferrer">Our World in Data</a>
          (CC BY) · approximated subset
        </div>
      </section>
    </aside>

    <!-- RIGHT: chart (time series or hotspot map) -->
    <main class="chart-area">
      {#if view === 'timeseries'}
        <div class="chart-header">
          <span class="chart-title">
            <span class="dot-lg" style="background: {diseaseColor(selectedDisease)}"></span>
            {diseaseLabel(selectedDisease)} — {selectedRegion}
          </span>
          <span class="chart-sub">confirmed cases &amp; deaths · use the scrubber or ▶ to play through time</span>
        </div>
        <div bind:this={chartEl} class="echarts-container"></div>
        {#if seriesData.length === 0}
          <div class="no-data">no data for {diseaseLabel(selectedDisease)} / {selectedRegion || '(no region selected)'}</div>
        {/if}
      {:else}
        <div class="chart-header">
          <span class="chart-title">
            <span class="dot-lg" style="background: {diseaseColor(selectedDisease)}"></span>
            Outbreak Hotspots — {diseaseLabel(selectedDisease)}
          </span>
          <span class="chart-sub">
            DBSCAN ε={epsKm} km · minPts={minPts} · circles = clusters (size ∝ total cases) · ◇ = isolated noise
          </span>
        </div>
        <div bind:this={hotspotChartEl} class="echarts-container"></div>
        {#if hotspotData.cluster_count === 0 && hotspotData.noise_points.length === 0}
          <div class="no-data">no geolocated reports for {diseaseLabel(selectedDisease)}</div>
        {/if}
      {/if}
    </main>

    <!-- FAR RIGHT: live alert feed (B3 spike detection) -->
    <aside class="alert-feed">
      <div class="feed-header">
        <span class="feed-title">Live Alerts</span>
        <span
          class="ws-indicator {wsConnected ? 'connected' : ''}"
          title={wsConnected ? 'live feed connected' : 'reconnecting…'}
        ></span>
      </div>

      {#if view === 'timeseries'}
        <button
          class="scan-btn"
          on:click={scanForSpikes}
          disabled={scanning || !selectedDisease || !selectedRegion}
        >
          {scanning ? 'Scanning…' : `Scan ${diseaseLabel(selectedDisease)} / ${selectedRegion || '—'}`}
        </button>
        {#if scanMessage}
          <div class="scan-msg">{scanMessage}</div>
        {/if}
      {/if}

      <div class="alert-list">
        {#each alerts as a (a.id)}
          <div
            class="alert-item {newAlertIds.has(a.id) ? (a.severity === 'HIGH' || a.severity === 'CRITICAL' ? 'alert-pulse' : 'alert-fade') : ''}"
            style="--sev: {SEVERITY_COLORS[a.severity]}"
          >
            <div class="alert-top">
              <span class="alert-sev" style="color: {SEVERITY_COLORS[a.severity]}">{a.severity}</span>
              <span class="alert-time">{timeAgo(a.created_at)}</span>
            </div>
            <div class="alert-msg">{a.message}</div>
            {#if a.z_score !== null}
              <div class="alert-meta">z = {formatZ(a.z_score)}</div>
            {/if}
          </div>
        {/each}
        {#if alerts.length === 0}
          <div class="no-alerts">no alerts yet — run a scan to check for spikes</div>
        {/if}
      </div>
    </aside>
  </div>
</div>

<!-- ── Styles ──────────────────────────────────────────────────────────────── -->

<style>
  /* ── Reset / Base ─────────────────────────────────────────────── */
  :global(body) {
    margin: 0;
    background: #0d1117;
    color: #e2e8f0;
    font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 13px;
  }

  /* ── Page shell ───────────────────────────────────────────────── */
  .page {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  /* ── Top bar ──────────────────────────────────────────────────── */
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    height: 44px;
    background: #161b22;
    border-bottom: 1px solid #21262d;
    flex-shrink: 0;
  }
  .brand {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: #e2e8f0;
  }
  .pill {
    background: #1f6feb33;
    color: #58a6ff;
    padding: 1px 8px;
    border-radius: 20px;
    font-size: 11px;
    margin-left: 8px;
    font-weight: 500;
    letter-spacing: 0.06em;
  }
  nav { display: flex; align-items: center; gap: 20px; }
  nav a {
    color: #6b7280;
    text-decoration: none;
    font-size: 12px;
    transition: color 0.15s;
  }
  nav a:hover { color: #e2e8f0; }
  nav .active { color: #e2e8f0; font-weight: 600; }

  /* ── Three-column layout ──────────────────────────────────────── */
  .layout {
    display: grid;
    grid-template-columns: 220px 1fr 270px;
    flex: 1;
    overflow: hidden;
  }

  /* ── Sidebar ──────────────────────────────────────────────────── */
  .sidebar {
    background: #0d1117;
    border-right: 1px solid #21262d;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    padding: 16px 14px;
    gap: 20px;
  }

  .controls { display: flex; flex-direction: column; gap: 8px; }

  .field-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #6b7280;
    text-transform: uppercase;
    margin-bottom: 2px;
  }
  .mt { margin-top: 8px; }

  /* Disease buttons: thin left-border accent, subtle hover */
  .disease-list { display: flex; flex-direction: column; gap: 2px; }
  .disease-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    background: none;
    border: 1px solid transparent;
    border-radius: 4px;
    color: #94a3b8;
    cursor: pointer;
    padding: 5px 8px;
    font-size: 12px;
    text-align: left;
    transition: background 0.12s, color 0.12s, border-color 0.12s;
  }
  .disease-btn:hover { background: #161b22; color: #e2e8f0; }
  .disease-btn.active {
    background: #161b22;
    color: #e2e8f0;
    border-color: var(--accent, #58a6ff);
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .select {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 4px;
    color: #e2e8f0;
    font-size: 12px;
    padding: 5px 8px;
    width: 100%;
    cursor: pointer;
    outline: none;
  }
  .select:focus { border-color: #58a6ff; }

  .play-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
  }
  .play-btn {
    display: flex;
    align-items: center;
    gap: 5px;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 4px;
    color: #e2e8f0;
    cursor: pointer;
    font-size: 12px;
    padding: 5px 12px;
    transition: border-color 0.12s, background 0.12s;
  }
  .play-btn:hover { border-color: #58a6ff; background: #1c2128; }
  .play-btn.playing { border-color: #f59e0b; color: #f59e0b; }
  .icon { font-size: 10px; }
  .play-hint { font-size: 10px; color: #4b5563; }

  /* ── Stat cards ───────────────────────────────────────────────── */
  .stat-cards { display: flex; flex-direction: column; gap: 8px; }
  .cards-label {
    font-size: 10px;
    color: #4b5563;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .stat-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 6px;
    padding: 8px 10px;
  }
  .stat-disease {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin-bottom: 5px;
  }
  .stat-row { display: flex; gap: 8px; }
  .stat-block { flex: 1; }
  .stat-value {
    font-size: 14px;
    font-weight: 700;
    color: #e2e8f0;
    line-height: 1;
  }
  .stat-value.red { color: #ef4444; }
  .stat-key {
    font-size: 9px;
    color: #4b5563;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-top: 2px;
  }
  .stat-peak-date {
    font-size: 10px;
    color: #6b7280;
    margin-top: 4px;
  }

  .source-attr {
    font-size: 10px;
    color: #374151;
    line-height: 1.5;
    margin-top: 4px;
  }
  .source-attr a { color: #4b5563; }
  .source-attr a:hover { color: #9ca3af; }

  /* ── Chart area ───────────────────────────────────────────────── */
  .chart-area {
    display: flex;
    flex-direction: column;
    padding: 14px 20px 10px;
    overflow: hidden;
    position: relative;
  }
  .chart-header {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-bottom: 10px;
    flex-shrink: 0;
  }
  .chart-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    font-weight: 700;
    color: #e2e8f0;
  }
  .dot-lg {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .chart-sub {
    font-size: 10px;
    color: #4b5563;
    letter-spacing: 0.04em;
    padding-left: 18px;
  }

  /* ECharts container fills remaining space */
  .echarts-container {
    flex: 1;
    width: 100%;
    min-height: 0;
  }

  .no-data {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: #374151;
    font-size: 13px;
  }

  /* ── View toggle ──────────────────────────────────────────────── */
  .view-toggle {
    display: flex;
    gap: 2px;
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 5px;
    padding: 2px;
  }
  .vtab {
    flex: 1;
    background: none;
    border: none;
    border-radius: 3px;
    color: #6b7280;
    cursor: pointer;
    font-size: 11px;
    padding: 4px 0;
    transition: background 0.12s, color 0.12s;
  }
  .vtab:hover { color: #e2e8f0; }
  .vtab.active { background: #161b22; color: #e2e8f0; font-weight: 600; }

  /* ── Hotspot meta line ────────────────────────────────────────── */
  .hotspot-meta {
    font-size: 10px;
    color: #4b5563;
    margin-top: 8px;
    line-height: 1.6;
  }
  .meta-val { font-weight: 700; }

  /* ── Live alert feed (B3) ─────────────────────────────────────── */
  .alert-feed {
    background: #0d1117;
    border-left: 1px solid #21262d;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 16px 14px;
    gap: 10px;
  }
  .feed-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }
  .feed-title {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #94a3b8;
  }
  .ws-indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #30363d;
    transition: background 0.3s, box-shadow 0.3s;
  }
  .ws-indicator.connected {
    background: #22c55e;
    box-shadow: 0 0 6px #22c55e88;
  }

  .scan-btn {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 4px;
    color: #e2e8f0;
    cursor: pointer;
    font-size: 11px;
    padding: 6px 10px;
    text-align: left;
    transition: border-color 0.12s, background 0.12s;
    flex-shrink: 0;
  }
  .scan-btn:hover:not(:disabled) { border-color: #58a6ff; background: #1c2128; }
  .scan-btn:disabled { opacity: 0.5; cursor: default; }
  .scan-msg {
    font-size: 10px;
    color: #6b7280;
    flex-shrink: 0;
  }

  .alert-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }
  .alert-item {
    background: #161b22;
    border: 1px solid #21262d;
    border-left: 3px solid var(--sev, #30363d);
    border-radius: 4px;
    padding: 7px 9px;
  }
  .alert-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 3px;
  }
  .alert-sev {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
  }
  .alert-time {
    font-size: 10px;
    color: #4b5563;
  }
  .alert-msg {
    font-size: 11px;
    color: #cbd5e1;
    line-height: 1.4;
  }
  .alert-meta {
    font-size: 10px;
    color: #6b7280;
    margin-top: 3px;
  }
  .no-alerts {
    font-size: 11px;
    color: #374151;
    text-align: center;
    margin-top: 20px;
  }

  /* New-alert entrance, severity-driven: LOW/MEDIUM fade in calmly,
     HIGH/CRITICAL also pulse their severity glow. */
  .alert-fade {
    animation: alert-fade-in 0.6s ease-out;
  }
  .alert-pulse {
    animation: alert-fade-in 0.4s ease-out, pulse-glow 1.8s ease-out;
  }
  @keyframes alert-fade-in {
    from { opacity: 0; transform: translateY(-6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes pulse-glow {
    0%   { box-shadow: 0 0 0 0 var(--sev); }
    40%  { box-shadow: 0 0 14px 2px var(--sev); }
    100% { box-shadow: 0 0 0 0 transparent; }
  }
</style>
