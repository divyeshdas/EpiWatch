<script lang="ts">
  import { onMount } from 'svelte';
  import PageShell from '$lib/components/PageShell.svelte';
  import TopTabs from '$lib/components/TopTabs.svelte';
  import { ICONS } from '$lib/icons';
  import { timeAgo } from '$lib/format';
  import { downloadCsv } from '$lib/csv';
  import type { Hospital, EmergencyCase } from '$lib/types';

  const API = 'http://localhost:8000';

  type PatientCondition = 'STABLE' | 'SERIOUS' | 'CRITICAL' | 'CARDIAC';

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

  const STATUS_LABELS: Record<string, string> = {
    PENDING: 'Pending',
    ASSIGNED: 'Assigned',
    NO_CANDIDATES: 'No candidates',
  };

  const STATUS_COLORS: Record<string, string> = {
    PENDING: '#a8893f',
    ASSIGNED: '#5f806b',
    NO_CANDIDATES: '#c94a45',
  };

  let cases: EmergencyCase[] = [];
  let hospitals: Hospital[] = [];
  let loading = true;
  let loadError: string | null = null;

  $: hospitalsById = new Map(hospitals.map(h => [h.id, h]));

  $: sortedCases = [...cases].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  function conditionColor(c: string): string {
    return CONDITION_COLORS[c as PatientCondition] ?? '#78716c';
  }

  function conditionLabel(c: string): string {
    return CONDITION_LABELS[c as PatientCondition] ?? c;
  }

  function statusColor(s: string): string {
    return STATUS_COLORS[s] ?? '#78716c';
  }

  function statusLabel(s: string): string {
    return STATUS_LABELS[s] ?? s;
  }

  function hospitalName(id: number | null): string {
    if (id === null) return '—';
    return hospitalsById.get(id)?.name ?? `#${id}`;
  }

  function fmtCoord(n: number): string {
    return n.toFixed(4);
  }

  function downloadCurrentView() {
    const rows = sortedCases.map(c => [
      c.created_at,
      c.latitude,
      c.longitude,
      conditionLabel(c.patient_condition),
      hospitalName(c.assigned_hospital_id),
      statusLabel(c.status),
    ]);
    downloadCsv('emergency_history.csv', ['Reported At', 'Latitude', 'Longitude', 'Condition', 'Assigned Hospital', 'Status'], rows);
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
    } catch {
      loadError = 'Could not reach the dispatch API.';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    loadAll();
  });
</script>

<PageShell section="Emergency Response" title="History">
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
      <h1 class="section-title">Emergency history</h1>
      <p class="section-sub">All reported emergencies, newest first — {cases.length} total.</p>
    </div>

    {#if loadError}
      <div class="error-banner">{@html ICONS.bell}{loadError}</div>
    {/if}

    <section class="panel">
      {#if loading}
        <div class="empty-note">Loading…</div>
      {:else if sortedCases.length === 0}
        <div class="empty-note">No emergencies have been reported yet.</div>
      {:else}
        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Reported</th>
                <th>Location</th>
                <th>Condition</th>
                <th>Assigned hospital</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {#each sortedCases as c (c.id)}
                <tr>
                  <td class="time-cell">{timeAgo(c.created_at)}</td>
                  <td class="coord-cell">{fmtCoord(c.latitude)}, {fmtCoord(c.longitude)}</td>
                  <td>
                    <span class="cond-chip" style="color: {conditionColor(c.patient_condition)}; border-color: {conditionColor(c.patient_condition)}">
                      {conditionLabel(c.patient_condition)}
                    </span>
                  </td>
                  <td>{hospitalName(c.assigned_hospital_id)}</td>
                  <td>
                    <span class="status-chip" style="color: {statusColor(c.status)}">
                      <span class="status-dot" style="background: {statusColor(c.status)}"></span>
                      {statusLabel(c.status)}
                    </span>
                  </td>
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
  }
  .data-table tbody tr:hover { background: var(--bg-hover); }

  .time-cell {
    font-family: var(--mono);
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum';
    white-space: nowrap;
  }
  .coord-cell {
    font-family: var(--mono);
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum';
    color: var(--text-muted);
    white-space: nowrap;
  }

  .cond-chip {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 500;
    border: 1px solid;
    border-radius: 8px;
    padding: 1px 8px;
    white-space: nowrap;
  }

  .status-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.83rem;
    font-weight: 500;
    white-space: nowrap;
  }
  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }
</style>
