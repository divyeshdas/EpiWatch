<script lang="ts">
  import { onMount } from 'svelte';
  import PageShell from '$lib/components/PageShell.svelte';
  import TopTabs from '$lib/components/TopTabs.svelte';
  import { ICONS } from '$lib/icons';
  import { timeAgo } from '$lib/format';
  import { loadFactor, pct } from '$lib/hospital';
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

  let hospitals: Hospital[] = [];
  let cases: EmergencyCase[] = [];
  let loading = true;
  let loadError: string | null = null;

  $: hospitalsById = new Map(hospitals.map(h => [h.id, h]));

  $: stats = {
    hospitalsOnline: hospitals.length,
    bedsAvailable: hospitals.reduce((s, h) => s + h.available_beds, 0),
    bedsTotal: hospitals.reduce((s, h) => s + h.total_beds, 0),
    icuAvailable: hospitals.reduce((s, h) => s + h.available_icu_beds, 0),
    icuTotal: hospitals.reduce((s, h) => s + h.total_icu_beds, 0),
    avgLoadPct: hospitals.length
      ? (hospitals.reduce((s, h) => s + loadFactor(h), 0) / hospitals.length) * 100
      : 0,
    pending: cases.filter(c => c.status === 'PENDING').length,
    assigned: cases.filter(c => c.status === 'ASSIGNED').length,
    noCandidates: cases.filter(c => c.status === 'NO_CANDIDATES').length,
    total: cases.length,
  };

  $: recentAssignments = [...cases]
    .filter(c => c.status === 'ASSIGNED' && c.assigned_hospital_id !== null)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 8);

  function conditionColor(c: string): string {
    return CONDITION_COLORS[c as PatientCondition] ?? '#78716c';
  }

  function conditionLabel(c: string): string {
    return CONDITION_LABELS[c as PatientCondition] ?? c;
  }

  function hospitalName(id: number | null): string {
    if (id === null) return '—';
    return hospitalsById.get(id)?.name ?? `#${id}`;
  }

  function hospitalRegion(id: number | null): string {
    if (id === null) return '—';
    return hospitalsById.get(id)?.region ?? '—';
  }

  async function loadAll() {
    loading = true;
    loadError = null;
    try {
      const [hospitalsRes, casesRes] = await Promise.all([
        fetch(`${API}/hospitals`),
        fetch(`${API}/emergency`),
      ]);
      if (!hospitalsRes.ok || !casesRes.ok) throw new Error('failed');
      hospitals = await hospitalsRes.json();
      cases = await casesRes.json();
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

<PageShell section="Emergency Response" title="Reports">
  <div class="page">
    <TopTabs tabs={[
      { label: 'Dispatch', href: '/emergency' },
      { label: 'Hospitals', href: '/emergency/hospitals' },
      { label: 'History', href: '/emergency/history' },
      { label: 'Routes', href: '/emergency/routes' },
      { label: 'Reports', href: '/emergency/reports' },
    ]} />

    <div class="page-header">
      <h1 class="section-title">Dispatch report</h1>
      <p class="section-sub">Network-wide capacity and emergency status, rolled up.</p>
    </div>

    {#if loadError}
      <div class="error-banner">{@html ICONS.bell}{loadError}</div>
    {/if}

    {#if loading}
      <div class="empty-note">Loading…</div>
    {:else}
      <div class="stat-row">
        <div class="stat-card">
          <div class="stat-label">Hospitals online</div>
          <div class="stat-value">{stats.hospitalsOnline}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Beds available</div>
          <div class="stat-value">{stats.bedsAvailable} <span class="stat-of">/ {stats.bedsTotal}</span></div>
        </div>
        <div class="stat-card">
          <div class="stat-label">ICU beds available</div>
          <div class="stat-value">{stats.icuAvailable} <span class="stat-of">/ {stats.icuTotal}</span></div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Average hospital load</div>
          <div class="stat-value {stats.avgLoadPct >= 70 ? 'stat-down' : 'stat-up'}">{pct(stats.avgLoadPct)}</div>
        </div>
      </div>

      <div class="stat-row">
        <div class="stat-card">
          <div class="stat-label">Pending emergencies</div>
          <div class="stat-value">{stats.pending}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Assigned</div>
          <div class="stat-value">{stats.assigned}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">No candidates found</div>
          <div class="stat-value">{stats.noCandidates}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total reported</div>
          <div class="stat-value">{stats.total}</div>
        </div>
      </div>

      <section class="panel">
        <div class="panel-header"><h2>Recent assignments</h2></div>
        {#if recentAssignments.length === 0}
          <div class="empty-note">No assigned emergencies yet.</div>
        {:else}
          <div class="data-table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Reported</th>
                  <th>Condition</th>
                  <th>Assigned hospital</th>
                  <th>Region</th>
                </tr>
              </thead>
              <tbody>
                {#each recentAssignments as c (c.id)}
                  <tr>
                    <td class="time-cell">{timeAgo(c.created_at)}</td>
                    <td>
                      <span class="cond-chip" style="color: {conditionColor(c.patient_condition)}; border-color: {conditionColor(c.patient_condition)}">
                        {conditionLabel(c.patient_condition)}
                      </span>
                    </td>
                    <td>{hospitalName(c.assigned_hospital_id)}</td>
                    <td>{hospitalRegion(c.assigned_hospital_id)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
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
  .stat-of {
    font-size: 0.85rem;
    font-weight: 400;
    color: var(--text-faint);
  }
  .stat-up { color: var(--success); }
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
  }
  .data-table tbody tr:hover { background: var(--bg-hover); }

  .time-cell {
    font-family: var(--mono);
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum';
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

  @media (max-width: 900px) {
    .stat-row { grid-template-columns: repeat(2, 1fr); }
  }
</style>
