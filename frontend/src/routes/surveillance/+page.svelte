<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
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

  let diseases: DiseaseInfo[] = [];
  let summaryRows: SummaryRow[] = [];
  let selectedDisease = 'covid_19';
  let selectedRegion  = 'India';
  let seriesData: OutbreakPoint[] = [];
  let regions: string[] = [];

  // Play state — controlled via dispatchAction on the ECharts dataZoom
  let isPlaying = false;
  let playTimer: ReturnType<typeof setInterval> | null = null;

  // ECharts — browser-only; never touches SSR
  let chartEl: HTMLDivElement;
  let chart: any = null;
  let echarts: any = null;

  // ── Data fetching ──────────────────────────────────────────────────────────

  async function loadDiseases() {
    const r = await fetch(`${API}/diseases`);
    diseases = await r.json();
    const d = diseases.find(x => x.disease_name === selectedDisease);
    if (d) regions = d.regions;
    if (!regions.includes(selectedRegion)) selectedRegion = regions[0] ?? '';
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
    renderChart();
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
    selectedRegion = regions[0] ?? '';
    loadTimeSeries();
  }

  function onRegionChange() {
    stopPlay();
    loadTimeSeries();
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  onMount(async () => {
    if (!browser) return;

    // Deferred import — keeps ECharts out of SSR entirely
    echarts = await import('echarts');

    chart = echarts.init(chartEl, null, { renderer: 'canvas' });

    // Resize with window
    const resize = () => chart?.resize();
    window.addEventListener('resize', resize);

    await Promise.all([loadDiseases(), loadSummary()]);
    await loadTimeSeries();

    return () => window.removeEventListener('resize', resize);
  });

  onDestroy(() => {
    stopPlay();
    chart?.dispose();
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
        <label class="field-label">Disease</label>
        <div class="disease-list">
          {#each diseases as d}
            <button
              class="disease-btn {selectedDisease === d.disease_name ? 'active' : ''}"
              style="--accent: {diseaseColor(d.disease_name)}"
              on:click={() => { selectedDisease = d.disease_name; onDiseaseChange(); }}
            >
              <span class="dot" style="background: {diseaseColor(d.disease_name)}"></span>
              {diseaseLabel(d.disease_name)}
            </button>
          {/each}
        </div>

        <label class="field-label mt">Region</label>
        <select bind:value={selectedRegion} on:change={onRegionChange} class="select">
          {#each regions as r}
            <option value={r}>{r}</option>
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

    <!-- RIGHT: chart -->
    <main class="chart-area">
      <div class="chart-header">
        <span class="chart-title">
          <span class="dot-lg" style="background: {diseaseColor(selectedDisease)}"></span>
          {diseaseLabel(selectedDisease)} — {selectedRegion}
        </span>
        <span class="chart-sub">confirmed cases &amp; deaths · use the scrubber or ▶ to play through time</span>
      </div>

      <!-- ECharts mounts here. bind:this gives us the DOM ref for echarts.init() -->
      <div bind:this={chartEl} class="echarts-container"></div>

      {#if seriesData.length === 0}
        <div class="no-data">no data for {selectedDisease} / {selectedRegion}</div>
      {/if}
    </main>
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

  /* ── Two-column layout ────────────────────────────────────────── */
  .layout {
    display: grid;
    grid-template-columns: 220px 1fr;
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
</style>
