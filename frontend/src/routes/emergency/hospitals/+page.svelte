<script lang="ts">
  import { onMount } from 'svelte';
  import PageShell from '$lib/components/PageShell.svelte';
  import TopTabs from '$lib/components/TopTabs.svelte';
  import { ICONS } from '$lib/icons';
  import type { Hospital } from '$lib/types';
  import { loadFactor, loadColor, occupancyColor, availabilityPct, pct } from '$lib/hospital';
  import { downloadCsv } from '$lib/csv';
  import { API_BASE } from '$lib/api';

  const API = API_BASE;

  let hospitals: Hospital[] = [];
  let loading = true;
  let loadError: string | null = null;

  type SortKey = 'name' | 'region' | 'beds' | 'icu' | 'load';
  let sortKey: SortKey = 'load';
  let sortDir: 1 | -1 = -1;

  function sortBy(key: SortKey) {
    if (sortKey === key) {
      sortDir = sortDir === 1 ? -1 : 1;
    } else {
      sortKey = key;
      sortDir = 1;
    }
  }

  function sortValue(h: Hospital, key: SortKey): number | string {
    switch (key) {
      case 'name': return h.name.toLowerCase();
      case 'region': return (h.region ?? '').toLowerCase();
      case 'beds': return h.available_beds;
      case 'icu': return h.available_icu_beds;
      case 'load': return loadFactor(h);
    }
  }

  $: sortedHospitals = [...hospitals].sort((a, b) => {
    const va = sortValue(a, sortKey);
    const vb = sortValue(b, sortKey);
    if (va < vb) return -1 * sortDir;
    if (va > vb) return 1 * sortDir;
    return 0;
  });

  function downloadCurrentView() {
    const rows = sortedHospitals.map(h => [
      h.name,
      h.region ?? '',
      h.available_beds,
      h.total_beds,
      h.available_icu_beds,
      h.total_icu_beds,
      Math.round(loadFactor(h) * 100),
      h.specializations.join('; '),
    ]);
    downloadCsv('hospitals.csv', [
      'Hospital', 'Region', 'Beds Available', 'Beds Total', 'ICU Available', 'ICU Total', 'Load %', 'Specializations',
    ], rows);
  }

  async function loadHospitals() {
    loading = true;
    loadError = null;
    try {
      const r = await fetch(`${API}/hospitals`);
      if (!r.ok) throw new Error('failed');
      hospitals = await r.json();
    } catch {
      loadError = 'Could not reach the dispatch API.';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    loadHospitals();
  });
</script>

<PageShell section="Emergency Response" title="Hospitals">
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
      <h1 class="section-title">Hospitals</h1>
      <p class="section-sub">Network-wide bed, ICU and load status across {hospitals.length} hospitals.</p>
    </div>

    {#if loadError}
      <div class="error-banner">{@html ICONS.bell}{loadError}</div>
    {/if}

    <section class="panel">
      {#if loading}
        <div class="empty-note">Loading…</div>
      {:else if sortedHospitals.length === 0}
        <div class="empty-note">No hospitals found.</div>
      {:else}
        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th class="sortable" on:click={() => sortBy('name')}>
                  Hospital{sortKey === 'name' ? (sortDir === 1 ? ' ▲' : ' ▼') : ''}
                </th>
                <th class="sortable" on:click={() => sortBy('region')}>
                  Region{sortKey === 'region' ? (sortDir === 1 ? ' ▲' : ' ▼') : ''}
                </th>
                <th class="num sortable" on:click={() => sortBy('beds')}>
                  Beds{sortKey === 'beds' ? (sortDir === 1 ? ' ▲' : ' ▼') : ''}
                </th>
                <th class="num sortable" on:click={() => sortBy('icu')}>
                  ICU{sortKey === 'icu' ? (sortDir === 1 ? ' ▲' : ' ▼') : ''}
                </th>
                <th class="load-col sortable" on:click={() => sortBy('load')}>
                  Load{sortKey === 'load' ? (sortDir === 1 ? ' ▲' : ' ▼') : ''}
                </th>
                <th>Specializations</th>
              </tr>
            </thead>
            <tbody>
              {#each sortedHospitals as h (h.id)}
                <tr>
                  <td class="hospital-name">{h.name}</td>
                  <td>{h.region ?? '—'}</td>
                  <td class="num">
                    <span style="color: {occupancyColor(h.available_beds, h.total_beds)}">
                      {h.available_beds}
                    </span> / {h.total_beds}
                  </td>
                  <td class="num">
                    <span style="color: {occupancyColor(h.available_icu_beds, h.total_icu_beds)}">
                      {h.available_icu_beds}
                    </span> / {h.total_icu_beds}
                  </td>
                  <td class="load-col">
                    <div class="load-cell">
                      <div class="load-bar">
                        <div class="load-bar-fill" style="width: {Math.min(100, loadFactor(h) * 100)}%; background: {loadColor(h)}"></div>
                      </div>
                      <span class="load-pct" style="color: {loadColor(h)}">{pct(loadFactor(h) * 100)}</span>
                    </div>
                  </td>
                  <td>
                    {#if h.specializations.length}
                      <div class="spec-list">
                        {#each h.specializations as s}
                          <span class="spec-chip">{s}</span>
                        {/each}
                      </div>
                    {:else}
                      <span class="empty-cell">—</span>
                    {/if}
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
  .page { display: flex; flex-direction: column; gap: 16px; max-width: 1200px; margin: 0 auto; width: 100%; }

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
  .data-table th.sortable { cursor: pointer; user-select: none; }
  .data-table th.sortable:hover { color: var(--text-muted); }
  .data-table td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border-soft);
    color: var(--text);
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum';
    vertical-align: middle;
  }
  .data-table td.num, .data-table th.num { text-align: right; }
  .data-table tbody tr:hover { background: var(--bg-hover); }

  .hospital-name { font-weight: 500; }

  .load-col { width: 160px; }
  .load-cell { display: flex; align-items: center; gap: 8px; }
  .load-bar {
    flex: 1;
    height: 6px;
    border-radius: 3px;
    background: var(--bg-sunken);
    overflow: hidden;
  }
  .load-bar-fill { height: 100%; border-radius: 3px; }
  .load-pct {
    font-family: var(--sans);
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum';
    font-size: 0.78rem;
    font-weight: 600;
    width: 40px;
    text-align: right;
  }

  .spec-list { display: flex; flex-wrap: wrap; gap: 4px; }
  .spec-chip {
    font-size: 0.7rem;
    color: var(--text-muted);
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    border-radius: 8px;
    padding: 1px 8px;
    white-space: nowrap;
  }
  .empty-cell { color: var(--text-faint); }
</style>
