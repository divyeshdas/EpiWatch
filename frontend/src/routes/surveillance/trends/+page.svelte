<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { browser } from '$app/environment';
  import { theme } from '$lib/stores/theme';
  import PageShell from '$lib/components/PageShell.svelte';
  import TopTabs from '$lib/components/TopTabs.svelte';
  import { ICONS } from '$lib/icons';
  import { fmt } from '$lib/format';

  const API = 'http://localhost:8000/surveillance';

  // Restrained, fixed per-disease colors — kept consistent with the
  // Surveillance overview (trend lines, disease table, hotspot bars).
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

  function diseaseLabel(slug: string): string {
    return DISEASE_LABELS[slug] ?? slug;
  }

  function diseaseColor(slug: string): string {
    return DISEASE_COLORS[slug] ?? '#94a3b8';
  }

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

  type DiseaseSeries = { disease: string; series: OutbreakPoint[]; total: number };

  let diseases: DiseaseInfo[] = [];
  let regions: string[] = [];
  let selectedRegion = '';
  let seriesByDisease: DiseaseSeries[] = [];
  let loadingDiseases = true;
  let loadingSeries = false;
  let loadError: string | null = null;

  let echarts: any = null;
  let chartEl: HTMLDivElement;
  let chart: any = null;

  function chartPalette() {
    const dark = $theme !== 'light';
    return {
      muted:         dark ? '#a8a29e' : '#6b645d',
      grid:          dark ? '#3a332e' : '#e2dcd4',
      axis:          dark ? '#51483f' : '#cfc6bb',
      tooltipBg:     dark ? '#26221f' : '#faf7f3',
      tooltipBorder: dark ? '#3a332e' : '#e2dcd4',
    };
  }

  async function loadDiseases() {
    loadingDiseases = true;
    loadError = null;
    try {
      const r = await fetch(`${API}/diseases`);
      if (!r.ok) throw new Error('failed');
      diseases = await r.json();
      const all = new Set<string>();
      for (const d of diseases) for (const r of d.regions) all.add(r);
      regions = [...all].sort();
      if (regions.length) selectedRegion = regions[0];
    } catch {
      loadError = 'Could not reach the surveillance API.';
    } finally {
      loadingDiseases = false;
    }
  }

  async function loadSeries() {
    if (!selectedRegion) return;
    loadingSeries = true;
    try {
      const relevant = diseases.filter(d => d.regions.includes(selectedRegion));
      const results = await Promise.all(relevant.map(async (d): Promise<DiseaseSeries> => {
        const r = await fetch(`${API}/timeseries?disease=${encodeURIComponent(d.disease_name)}&region=${encodeURIComponent(selectedRegion)}`);
        const series: OutbreakPoint[] = r.ok ? await r.json() : [];
        return { disease: d.disease_name, series, total: series.reduce((s, p) => s + p.case_count, 0) };
      }));
      seriesByDisease = results.filter(d => d.series.length > 0);
    } catch {
      seriesByDisease = [];
    } finally {
      loadingSeries = false;
    }
  }

  function renderChart() {
    if (!chart || !echarts) return;
    const pal = chartPalette();

    chart.setOption({
      backgroundColor: 'transparent',
      animationDurationUpdate: 500,
      grid: { top: 36, right: 16, bottom: 32, left: 56, containLabel: false },
      tooltip: {
        trigger: 'axis',
        backgroundColor: pal.tooltipBg,
        borderColor: pal.tooltipBorder,
        textStyle: { color: pal.muted, fontSize: 12, fontFamily: 'var(--sans)' },
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
          formatter: (v: number) => fmt(v),
        },
      },
      series: seriesByDisease.map(d => ({
        name: diseaseLabel(d.disease),
        type: 'line',
        data: d.series.map(p => [p.date, p.case_count]),
        smooth: 0.4,
        symbol: 'none',
        lineStyle: { color: diseaseColor(d.disease), width: 2 },
      })),
    }, true);
  }

  onMount(() => {
    (async () => {
      await loadDiseases();
      await loadSeries();
      if (browser) {
        echarts = await import('echarts');
        chart = echarts.init(chartEl, null, { renderer: 'canvas' });
        await tick();
        renderChart();
      }
    })();

    const resize = () => chart?.resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  });

  let firstRun = true;
  $: if (selectedRegion) {
    if (firstRun) {
      firstRun = false;
    } else {
      loadSeries().then(() => { if (chart) renderChart(); });
    }
  }
  $: if (chart && echarts && seriesByDisease) renderChart();
</script>

<PageShell section="Surveillance" title="Trends">
  <div class="page">
    <TopTabs tabs={[
      { label: 'Overview', href: '/surveillance' },
      { label: 'Trends', href: '/surveillance/trends' },
      { label: 'Diseases', href: '/surveillance/diseases' },
      { label: 'Alerts', href: '/alerts' },
      { label: 'Reports', href: '/surveillance/reports' },
    ]} />

    <div class="page-header">
      <div>
        <h1 class="section-title">Disease trends</h1>
        <p class="section-sub">Compare reported case counts across diseases for a region.</p>
      </div>
      <label class="filter">
        <span>Region</span>
        <select class="quiet-select" bind:value={selectedRegion} disabled={loadingDiseases}>
          {#each regions as r}
            <option value={r}>{r}</option>
          {/each}
        </select>
      </label>
    </div>

    {#if loadError}
      <div class="error-banner">{@html ICONS.bell}{loadError}</div>
    {/if}

    <section class="panel">
      <div class="panel-header"><h2>Cases over time — {selectedRegion || '—'}</h2></div>
      <div class="chart-wrap">
        <div bind:this={chartEl} class="echarts-container"></div>
        {#if loadingSeries}
          <div class="chart-overlay">Loading…</div>
        {:else if seriesByDisease.length === 0}
          <div class="chart-overlay">No time series data for this region.</div>
        {/if}
      </div>
    </section>

    {#if seriesByDisease.length > 0}
      <div class="stat-row">
        {#each seriesByDisease as d (d.disease)}
          <div class="stat-card">
            <div class="stat-label">
              <span class="dot" style="background: {diseaseColor(d.disease)}"></span>
              {diseaseLabel(d.disease)}
            </div>
            <div class="stat-value">{fmt(d.total)}</div>
            <div class="stat-sub">total cases, {selectedRegion}</div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</PageShell>

<style>
  .page { display: flex; flex-direction: column; gap: 16px; max-width: 1100px; margin: 0 auto; width: 100%; }

  .page-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .section-title {
    font-family: var(--serif);
    font-size: 1.6rem;
    font-weight: 600;
    margin: 0;
    color: var(--text);
  }
  .section-sub { font-size: 0.85rem; color: var(--text-muted); margin: 4px 0 0; }

  .filter {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.7rem;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .quiet-select {
    font-family: var(--sans);
    font-size: 0.83rem;
    text-transform: none;
    letter-spacing: normal;
    color: var(--text);
    background: var(--bg-sunken);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    cursor: pointer;
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

  .panel {
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px;
  }
  .panel-header h2 { font-size: 0.95rem; font-weight: 600; margin: 0 0 12px; color: var(--text); }

  .chart-wrap { position: relative; height: 320px; }
  .echarts-container { width: 100%; height: 100%; }
  .chart-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    color: var(--text-faint);
    background: var(--bg-panel);
  }

  .stat-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
  }
  .stat-card {
    background: var(--card);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm);
    padding: 12px 14px;
  }
  .stat-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.68rem;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
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

  @media (max-width: 900px) {
    .stat-row { grid-template-columns: repeat(2, 1fr); }
  }
</style>
