<script lang="ts">
  import { onMount } from 'svelte';
  import PageShell from '$lib/components/PageShell.svelte';
  import TopTabs from '$lib/components/TopTabs.svelte';
  import { ICONS } from '$lib/icons';
  import { fmt, monthYear, timeAgo } from '$lib/format';

  const API = 'http://localhost:8000/surveillance';

  type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

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

  const SEVERITY_COLORS: Record<Severity, string> = {
    LOW: '#5f806b',
    MEDIUM: '#a8893f',
    HIGH: '#b96532',
    CRITICAL: '#c94a45',
  };

  function diseaseLabel(slug: string | null): string {
    if (!slug) return '—';
    return DISEASE_LABELS[slug] ?? slug;
  }

  function diseaseColor(slug: string): string {
    return DISEASE_COLORS[slug] ?? '#94a3b8';
  }

  type OutbreakSummary = {
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

  let summaries: OutbreakSummary[] = [];
  let hotspots: HotspotCluster[] = [];
  let alerts: AlertRow[] = [];
  let loading = true;
  let loadError: string | null = null;

  $: totals = summaries.reduce(
    (acc, s) => ({ cases: acc.cases + s.total_cases, deaths: acc.deaths + s.total_deaths }),
    { cases: 0, deaths: 0 }
  );

  $: topHotspots = [...hotspots]
    .sort((a, b) => b.total_cases - a.total_cases)
    .slice(0, 6);

  $: criticalHighAlerts = alerts
    .filter(a => a.severity === 'CRITICAL' || a.severity === 'HIGH')
    .slice(0, 8);

  function fmtCoord(n: number): string {
    return n.toFixed(2);
  }

  async function loadAll() {
    loading = true;
    loadError = null;
    try {
      const [summaryRes, hotspotsRes, alertsRes] = await Promise.all([
        fetch(`${API}/summary`),
        fetch(`${API}/hotspots`),
        fetch(`http://localhost:8000/alerts?limit=100`),
      ]);
      if (!summaryRes.ok || !hotspotsRes.ok || !alertsRes.ok) throw new Error('failed');
      summaries = await summaryRes.json();
      const hotspotData: HotspotResponse = await hotspotsRes.json();
      hotspots = hotspotData.clusters;
      alerts = await alertsRes.json();
    } catch {
      loadError = 'Could not reach the surveillance API.';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    loadAll();
  });
</script>

<PageShell section="Surveillance" title="Reports">
  <div class="page">
    <TopTabs tabs={[
      { label: 'Overview', href: '/surveillance' },
      { label: 'Trends', href: '/surveillance/trends' },
      { label: 'Diseases', href: '/surveillance/diseases' },
      { label: 'Alerts', href: '/alerts' },
      { label: 'Reports', href: '/surveillance/reports' },
    ]} />

    <div class="page-header">
      <h1 class="section-title">Situation report</h1>
      <p class="section-sub">Cross-disease totals, current hotspots, and recent high-severity alerts.</p>
    </div>

    {#if loadError}
      <div class="error-banner">{@html ICONS.bell}{loadError}</div>
    {/if}

    {#if loading}
      <div class="empty-note">Loading…</div>
    {:else}
      <div class="stat-row">
        <div class="stat-card">
          <div class="stat-label">Total cases (all diseases)</div>
          <div class="stat-value">{fmt(totals.cases)}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total deaths (all diseases)</div>
          <div class="stat-value">{fmt(totals.deaths)}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Active hotspot clusters</div>
          <div class="stat-value">{hotspots.length}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Critical / high alerts</div>
          <div class="stat-value {criticalHighAlerts.length ? 'stat-down' : ''}">{criticalHighAlerts.length}</div>
        </div>
      </div>

      <section class="panel">
        <div class="panel-header"><h2>Disease summary</h2></div>
        {#if summaries.length === 0}
          <div class="empty-note">No surveillance data available.</div>
        {:else}
          <div class="data-table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Disease</th>
                  <th class="num">Total cases</th>
                  <th class="num">Total deaths</th>
                  <th class="num">Peak cases</th>
                  <th>Peak month</th>
                </tr>
              </thead>
              <tbody>
                {#each summaries as s (s.disease_name)}
                  <tr>
                    <td>
                      <span class="disease-name">
                        <span class="dot" style="background: {diseaseColor(s.disease_name)}"></span>
                        {diseaseLabel(s.disease_name)}
                      </span>
                    </td>
                    <td class="num">{fmt(s.total_cases)}</td>
                    <td class="num">{fmt(s.total_deaths)}</td>
                    <td class="num">{fmt(s.peak_cases)}</td>
                    <td>{s.peak_date ? monthYear(s.peak_date) : '—'}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </section>

      <section class="panel">
        <div class="panel-header"><h2>Top hotspots</h2></div>
        {#if topHotspots.length === 0}
          <div class="empty-note">No hotspot clusters detected.</div>
        {:else}
          <div class="data-table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Cluster</th>
                  <th>Centroid</th>
                  <th class="num">Total cases</th>
                  <th class="num">Reports</th>
                  <th class="num">Radius</th>
                </tr>
              </thead>
              <tbody>
                {#each topHotspots as h (h.cluster_id)}
                  <tr>
                    <td>#{h.cluster_id}</td>
                    <td class="coord-cell">{fmtCoord(h.centroid_lat)}, {fmtCoord(h.centroid_lon)}</td>
                    <td class="num">{fmt(h.total_cases)}</td>
                    <td class="num">{h.report_count}</td>
                    <td class="num">{h.radius_km.toFixed(1)} km</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </section>

      <section class="panel">
        <div class="panel-header"><h2>Recent critical &amp; high alerts</h2></div>
        {#if criticalHighAlerts.length === 0}
          <div class="empty-note">No critical or high-severity alerts.</div>
        {:else}
          <div class="alert-list">
            {#each criticalHighAlerts as a (a.id)}
              <div class="alert-row">
                <span class="severity-dot" style="background: {SEVERITY_COLORS[a.severity]}"></span>
                <div class="alert-body">
                  <div class="alert-message">{a.message}</div>
                  <div class="alert-meta">
                    {diseaseLabel(a.disease_name)}{a.region ? ` · ${a.region}` : ''} · {timeAgo(a.created_at)}
                  </div>
                </div>
                <span class="severity-chip" style="color: {SEVERITY_COLORS[a.severity]}">{a.severity}</span>
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}
  </div>
</PageShell>

<style>
  .page { display: flex; flex-direction: column; gap: 16px; max-width: 1100px; margin: 0 auto; width: 100%; }

  .page-header { display: flex; flex-direction: column; gap: 4px; }
  .section-title {
    font-family: var(--serif);
    font-size: 1.6rem;
    font-weight: 600;
    margin: 0;
    color: var(--text);
  }
  .section-sub { font-size: 0.85rem; color: var(--text-muted); margin: 0; }

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

  .empty-note {
    font-size: 0.85rem;
    color: var(--text-faint);
    padding: 24px 8px;
    text-align: center;
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
  .stat-down { color: var(--danger); }

  .panel {
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px;
  }
  .panel-header h2 { font-size: 0.95rem; font-weight: 600; margin: 0 0 12px; color: var(--text); }

  .data-table-wrap { overflow-x: auto; }
  .data-table { width: 100%; border-collapse: collapse; font-size: 0.83rem; }
  .data-table th {
    text-align: left;
    font-size: 0.68rem;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border-soft);
    white-space: nowrap;
  }
  .data-table td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border-soft);
    color: var(--text);
    vertical-align: middle;
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum';
  }
  .data-table td.num, .data-table th.num { text-align: right; }
  .data-table tbody tr:hover { background: var(--bg-hover); }

  .disease-name { display: flex; align-items: center; gap: 6px; font-variant-numeric: normal; }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

  .coord-cell { font-family: var(--mono); color: var(--text-muted); white-space: nowrap; }

  .alert-list { display: flex; flex-direction: column; gap: 1px; }
  .alert-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 4px;
    border-bottom: 1px solid var(--border-soft);
  }
  .alert-row:last-child { border-bottom: none; }
  .severity-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-top: 5px;
    flex-shrink: 0;
  }
  .alert-body { flex: 1; min-width: 0; }
  .alert-message { font-size: 0.85rem; color: var(--text); }
  .alert-meta { font-size: 0.75rem; color: var(--text-faint); margin-top: 2px; }
  .severity-chip {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    flex-shrink: 0;
    white-space: nowrap;
  }

  @media (max-width: 900px) {
    .stat-row { grid-template-columns: repeat(2, 1fr); }
  }
</style>
