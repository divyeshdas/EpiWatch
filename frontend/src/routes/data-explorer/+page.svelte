<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { browser } from '$app/environment';
  import { theme } from '$lib/stores/theme';
  import PageShell from '$lib/components/PageShell.svelte';
  import { ICONS } from '$lib/icons';
  import { DISEASE_COLORS } from '$lib/constants';
  import { diseaseLabel, fmt, monthYear } from '$lib/format';
  import { API_BASE } from '$lib/api';

  const API = `${API_BASE}/surveillance`;

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

  let diseases: DiseaseInfo[] = [];
  let selectedDisease = '';
  let selectedRegion = '';
  let series: OutbreakPoint[] = [];
  let loadingDiseases = true;
  let loadingSeries = false;
  let loadError: string | null = null;

  let echarts: any = null;
  let chartEl: HTMLDivElement;
  let chart: any = null;

  async function loadDiseases() {
    loadingDiseases = true;
    loadError = null;
    try {
      const r = await fetch(`${API}/diseases`);
      if (!r.ok) throw new Error('failed');
      diseases = await r.json();
      if (diseases.length) {
        selectedDisease = diseases[0].disease_name;
        selectedRegion = diseases[0].regions[0] ?? '';
      }
    } catch {
      loadError = 'Could not reach the surveillance API.';
    } finally {
      loadingDiseases = false;
    }
  }

  async function loadSeries() {
    if (!selectedDisease || !selectedRegion) return;
    loadingSeries = true;
    try {
      const r = await fetch(`${API}/timeseries?disease=${encodeURIComponent(selectedDisease)}&region=${encodeURIComponent(selectedRegion)}`);
      series = r.ok ? await r.json() : [];
    } catch {
      series = [];
    } finally {
      loadingSeries = false;
    }
  }

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

  function renderChart() {
    if (!chart || !echarts) return;
    const pal = chartPalette();
    const color = DISEASE_COLORS[selectedDisease] ?? '#14b8a6';

    chart.setOption({
      backgroundColor: 'transparent',
      animationDurationUpdate: 500,
      grid: { top: 24, right: 16, bottom: 32, left: 56, containLabel: false },
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
      series: [
        {
          name: 'Cases', type: 'line', data: series.map(p => [p.date, p.case_count]),
          smooth: 0.4, symbol: 'none', lineStyle: { color, width: 2 },
        },
        {
          name: 'Deaths', type: 'line', data: series.map(p => [p.date, p.deaths]),
          smooth: 0.4, symbol: 'none', lineStyle: { color: pal.muted, width: 2, type: 'dashed' },
        },
      ],
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

  // Reload the series whenever the picker changes (after initial mount).
  let firstRun = true;
  $: if (selectedDisease && selectedRegion) {
    if (firstRun) {
      firstRun = false;
    } else {
      loadSeries().then(() => { if (chart) renderChart(); });
    }
  }
  $: if (chart && echarts && series) renderChart();

  // Keep the region valid when the disease changes.
  $: regionsForDisease = diseases.find(d => d.disease_name === selectedDisease)?.regions ?? [];
  $: if (selectedDisease && regionsForDisease.length && !regionsForDisease.includes(selectedRegion)) {
    selectedRegion = regionsForDisease[0];
  }

  $: totals = series.reduce(
    (acc, p) => ({ cases: acc.cases + p.case_count, deaths: acc.deaths + p.deaths }),
    { cases: 0, deaths: 0 }
  );
  $: peak = series.reduce((max, p) => (p.case_count > (max?.case_count ?? -1) ? p : max), null as OutbreakPoint | null);
</script>

<PageShell title="Data Explorer">
  <div class="explorer-page">
    <div class="page-header">
      <h1 class="section-title">Data Explorer</h1>
      <p class="section-sub">Pick a disease and region to dig into the underlying time series.</p>
    </div>

    <div class="filter-bar">
      <label class="filter">
        <span>Disease</span>
        <select class="quiet-select" bind:value={selectedDisease} disabled={loadingDiseases}>
          {#each diseases as d}
            <option value={d.disease_name}>{diseaseLabel(d.disease_name)}</option>
          {/each}
        </select>
      </label>

      <label class="filter">
        <span>Region</span>
        <select class="quiet-select" bind:value={selectedRegion} disabled={loadingDiseases}>
          {#each regionsForDisease as r}
            <option value={r}>{r}</option>
          {/each}
        </select>
      </label>
    </div>

    {#if loadError}
      <div class="error-banner">{@html ICONS.bell}{loadError}</div>
    {/if}

    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">Total cases</div>
        <div class="stat-value">{fmt(totals.cases)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total deaths</div>
        <div class="stat-value">{fmt(totals.deaths)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Records</div>
        <div class="stat-value">{series.length}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Peak day</div>
        <div class="stat-value">{peak ? fmt(peak.case_count) : '—'}</div>
        <div class="stat-sub">{peak ? monthYear(peak.date) : '—'}</div>
      </div>
    </div>

    <section class="panel">
      <div class="panel-header"><h2>{diseaseLabel(selectedDisease)} — {selectedRegion}</h2></div>
      <div class="chart-wrap">
        <div bind:this={chartEl} class="echarts-container"></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header"><h2>Time series data</h2></div>
      {#if loadingSeries}
        <div class="empty-note">Loading…</div>
      {:else if series.length === 0}
        <div class="empty-note">No data for this disease/region combination.</div>
      {:else}
        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>Date</th><th>Cases</th><th>Deaths</th></tr>
            </thead>
            <tbody>
              {#each series as p}
                <tr>
                  <td>{monthYear(p.date)}</td>
                  <td class="num">{p.case_count.toLocaleString()}</td>
                  <td class="num">{p.deaths.toLocaleString()}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </section>
  </div>
</PageShell>

<style>
  .explorer-page { max-width: 920px; margin: 0 auto; width: 100%; }

  .page-header { margin-bottom: var(--space-4); }
  .section-title {
    font-family: var(--serif);
    font-size: 1.6rem;
    font-weight: 600;
    margin: 0 0 8px;
    color: var(--text);
  }
  .section-sub { font-size: 0.85rem; color: var(--text-muted); margin: 0; }

  .filter-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: var(--space-4);
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border-soft);
  }
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
    padding: var(--space-2) var(--space-3);
    cursor: pointer;
  }

  .error-banner {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.83rem;
    color: var(--danger);
    background: var(--accent-soft);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm);
    padding: var(--space-3) var(--space-4);
    margin-bottom: 16px;
  }
  .error-banner :global(svg) { width: 16px; height: 16px; flex-shrink: 0; }

  .stat-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: var(--space-4);
  }
  .stat-card {
    background: var(--card);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm);
    padding: 12px 14px;
  }
  .stat-label {
    font-size: 0.68rem;
    color: var(--text-faint);
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

  .panel {
    background: var(--card);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 16px;
  }
  .panel-header h2 { font-size: 0.95rem; font-weight: 600; margin: 0 0 12px; color: var(--text); }

  .chart-wrap { height: 280px; }
  .echarts-container { width: 100%; height: 100%; }

  .empty-note {
    font-size: 0.85rem;
    color: var(--text-faint);
    padding: 24px 8px;
    text-align: center;
  }

  .data-table-wrap { max-height: 360px; overflow-y: auto; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 0.83rem; }
  .data-table th {
    position: sticky;
    top: 0;
    background: var(--card);
    text-align: left;
    font-size: 0.68rem;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border-soft);
  }
  .data-table td {
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border-soft);
    color: var(--text);
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum';
  }
  .data-table td.num, .data-table th:not(:first-child) { text-align: right; }
  .data-table tbody tr:hover { background: var(--bg-hover); }

  @media (max-width: 900px) {
    .stat-row { grid-template-columns: repeat(2, 1fr); }
  }
</style>
