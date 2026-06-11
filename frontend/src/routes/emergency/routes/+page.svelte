<script lang="ts">
  import { onMount } from 'svelte';
  import PageShell from '$lib/components/PageShell.svelte';
  import TopTabs from '$lib/components/TopTabs.svelte';
  import { ICONS } from '$lib/icons';
  import { timeAgo } from '$lib/format';
  import { fmtKm, fmtMin } from '$lib/hospital';
  import { downloadCsv } from '$lib/csv';
  import type { Hospital, EmergencyCase, RouteResponse } from '$lib/types';

  const API = 'http://localhost:8000';

  // Most recent assigned emergencies to compute routes for — keeps the
  // number of /route calls bounded.
  const ROW_LIMIT = 15;

  type Algo = 'astar' | 'dijkstra';

  type RouteRow = {
    case: EmergencyCase;
    hospital: Hospital | null;
    distance_m: number | null;
    travel_time_s: number | null;
    node_count: number | null;
    reason: string | null;
  };

  let cases: EmergencyCase[] = [];
  let hospitals: Hospital[] = [];
  let rows: RouteRow[] = [];
  let algo: Algo = 'astar';
  let loading = true;
  let computing = false;
  let loadError: string | null = null;

  $: hospitalsById = new Map(hospitals.map(h => [h.id, h]));

  function fmtCoord(n: number): string {
    return n.toFixed(4);
  }

  async function computeRoutes() {
    computing = true;
    const assigned = [...cases]
      .filter(c => c.status === 'ASSIGNED' && c.assigned_hospital_id !== null)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, ROW_LIMIT);

    rows = await Promise.all(assigned.map(async (c): Promise<RouteRow> => {
      const hospital = hospitalsById.get(c.assigned_hospital_id as number) ?? null;
      try {
        const r = await fetch(`${API}/route?algo=${algo}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            latitude: c.latitude,
            longitude: c.longitude,
            hospital_id: c.assigned_hospital_id,
          }),
        });
        if (!r.ok) throw new Error('failed');
        const data: RouteResponse = await r.json();
        if (!data.route) {
          return { case: c, hospital, distance_m: null, travel_time_s: null, node_count: null, reason: data.reason ?? 'No route found' };
        }
        return {
          case: c,
          hospital,
          distance_m: data.route.total_distance_m,
          travel_time_s: data.route.total_travel_time_s,
          node_count: data.route.node_count,
          reason: null,
        };
      } catch {
        return { case: c, hospital, distance_m: null, travel_time_s: null, node_count: null, reason: 'Route computation failed' };
      }
    }));
    computing = false;
  }

  function downloadCurrentView() {
    const data = rows.map(r => [
      r.case.created_at,
      r.case.latitude,
      r.case.longitude,
      r.hospital?.name ?? `#${r.case.assigned_hospital_id}`,
      r.distance_m !== null ? (r.distance_m / 1000).toFixed(2) : '',
      r.travel_time_s !== null ? (r.travel_time_s / 60).toFixed(1) : '',
      r.node_count ?? '',
      algo,
      r.reason ?? '',
    ]);
    downloadCsv(`routes_${algo}.csv`, ['Reported At', 'Origin Lat', 'Origin Lon', 'Hospital', 'Distance (km)', 'ETA (min)', 'Nodes', 'Algorithm', 'Reason'], data);
  }

  async function loadAll() {
    loading = true;
    loadError = null;
    try {
      const [casesRes, hospitalsRes] = await Promise.all([
        fetch(`${API}/emergency`),
        fetch(`${API}/hospitals`),
      ]);
      if (!casesRes.ok || !hospitalsRes.ok) throw new Error('failed');
      cases = await casesRes.json();
      hospitals = await hospitalsRes.json();
      await computeRoutes();
    } catch {
      loadError = 'Could not reach the dispatch API.';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    loadAll();
  });

  // Recompute routes whenever the algorithm picker changes (after initial load).
  let firstRun = true;
  $: if (algo) {
    if (firstRun) {
      firstRun = false;
    } else if (!loading) {
      computeRoutes();
    }
  }
</script>

<PageShell section="Emergency Response" title="Routes">
  <svelte:fragment slot="topbar-right">
    <button class="topbar-btn" on:click={downloadCurrentView}>{@html ICONS.download}<span>Download</span></button>
  </svelte:fragment>
  <div class="page">
    <TopTabs tabs={[
      { label: 'Dispatch', href: '/emergency' },
      { label: 'Hospitals', href: '/emergency/hospitals' },
      { label: 'History', href: '/emergency/history' },
      { label: 'Routes', href: '/emergency/routes' },
      { label: 'Reports', href: '/emergency/reports' },
    ]} />

    <div class="page-header">
      <div>
        <h1 class="section-title">Computed routes</h1>
        <p class="section-sub">Most recent assigned dispatches, routed over the road graph.</p>
      </div>
      <label class="filter">
        <span>Algorithm</span>
        <select class="quiet-select" bind:value={algo} disabled={loading || computing}>
          <option value="astar">A*</option>
          <option value="dijkstra">Dijkstra</option>
        </select>
      </label>
    </div>

    {#if loadError}
      <div class="error-banner">{@html ICONS.bell}{loadError}</div>
    {/if}

    <section class="panel">
      {#if loading}
        <div class="empty-note">Loading…</div>
      {:else if rows.length === 0}
        <div class="empty-note">No assigned emergencies to route yet.</div>
      {:else}
        <div class="data-table-wrap" class:dimmed={computing}>
          <table class="data-table">
            <thead>
              <tr>
                <th>Reported</th>
                <th>Origin</th>
                <th>Hospital</th>
                <th class="num">Distance</th>
                <th class="num">ETA</th>
                <th class="num">Nodes</th>
                <th>Algorithm</th>
              </tr>
            </thead>
            <tbody>
              {#each rows as row (row.case.id)}
                <tr>
                  <td class="time-cell">{timeAgo(row.case.created_at)}</td>
                  <td class="coord-cell">{fmtCoord(row.case.latitude)}, {fmtCoord(row.case.longitude)}</td>
                  <td>{row.hospital?.name ?? `#${row.case.assigned_hospital_id}`}</td>
                  {#if row.reason}
                    <td class="num" colspan="3"><span class="empty-cell">{row.reason}</span></td>
                  {:else}
                    <td class="num">{fmtKm(row.distance_m ?? 0)}</td>
                    <td class="num">{fmtMin(row.travel_time_s ?? 0)}</td>
                    <td class="num">{row.node_count}</td>
                  {/if}
                  <td><span class="algo-chip">{algo === 'astar' ? 'A*' : 'Dijkstra'}</span></td>
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

  .empty-note {
    font-size: 0.85rem;
    color: var(--text-faint);
    padding: 24px 8px;
    text-align: center;
  }

  .data-table-wrap { overflow-x: auto; transition: opacity 180ms ease; }
  .data-table-wrap.dimmed { opacity: 0.5; }
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

  .time-cell { font-family: var(--mono); white-space: nowrap; }
  .coord-cell { font-family: var(--mono); color: var(--text-muted); white-space: nowrap; }

  .algo-chip {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--accent);
    background: var(--accent-soft);
    border-radius: 8px;
    padding: 1px 8px;
    white-space: nowrap;
  }

  .empty-cell { color: var(--text-faint); font-variant-numeric: normal; }
</style>
