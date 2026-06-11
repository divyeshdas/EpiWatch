<script lang="ts">
  import { onMount } from 'svelte';
  import PageShell from '$lib/components/PageShell.svelte';
  import TopTabs from '$lib/components/TopTabs.svelte';
  import { ICONS } from '$lib/icons';
  import { fmt, monthYear } from '$lib/format';
  import { downloadCsv } from '$lib/csv';

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

  type OutbreakSummary = {
    disease_name: string;
    total_cases: number;
    total_deaths: number;
    peak_cases: number;
    peak_date: string | null;
    record_count: number;
  };

  type DiseaseProfile = DiseaseInfo & Partial<OutbreakSummary>;

  let profiles: DiseaseProfile[] = [];
  let loading = true;
  let loadError: string | null = null;

  async function loadAll() {
    loading = true;
    loadError = null;
    try {
      const [diseasesRes, summaryRes] = await Promise.all([
        fetch(`${API}/diseases`),
        fetch(`${API}/summary`),
      ]);
      if (!diseasesRes.ok || !summaryRes.ok) throw new Error('failed');
      const diseases: DiseaseInfo[] = await diseasesRes.json();
      const summaries: OutbreakSummary[] = await summaryRes.json();
      const summaryByName = new Map(summaries.map(s => [s.disease_name, s]));
      profiles = diseases.map(d => ({ ...d, ...summaryByName.get(d.disease_name) }));
    } catch {
      loadError = 'Could not reach the surveillance API.';
    } finally {
      loading = false;
    }
  }

  function downloadCurrentView() {
    const rows = profiles.map(p => [
      diseaseLabel(p.disease_name),
      p.regions.join('; '),
      p.date_from,
      p.date_to,
      p.total_cases ?? '',
      p.total_deaths ?? '',
      p.peak_cases ?? '',
      p.peak_date ?? '',
      p.total_records,
    ]);
    downloadCsv('disease_profiles.csv', ['Disease', 'Regions', 'From', 'To', 'Total Cases', 'Total Deaths', 'Peak Cases', 'Peak Date', 'Total Records'], rows);
  }

  onMount(() => {
    loadAll();
  });
</script>

<PageShell section="Surveillance" title="Diseases">
  <svelte:fragment slot="topbar-right">
    <button class="topbar-btn" on:click={downloadCurrentView}>{@html ICONS.download}<span>Download</span></button>
  </svelte:fragment>
  <div class="page">
    <TopTabs tabs={[
      { label: 'Overview', href: '/surveillance' },
      { label: 'Trends', href: '/surveillance/trends' },
      { label: 'Diseases', href: '/surveillance/diseases' },
      { label: 'Alerts', href: '/alerts' },
      { label: 'Reports', href: '/surveillance/reports' },
    ]} />

    <div class="page-header">
      <h1 class="section-title">Disease profiles</h1>
      <p class="section-sub">Tracked diseases, their coverage, and historical totals.</p>
    </div>

    {#if loadError}
      <div class="error-banner">{@html ICONS.bell}{loadError}</div>
    {/if}

    {#if loading}
      <div class="empty-note">Loading…</div>
    {:else if profiles.length === 0}
      <div class="empty-note">No disease data available.</div>
    {:else}
      <div class="profile-grid">
        {#each profiles as p (p.disease_name)}
          <a class="profile-card" href="/surveillance?disease={encodeURIComponent(p.disease_name)}">
            <div class="profile-header">
              <span class="dot" style="background: {diseaseColor(p.disease_name)}"></span>
              <h2>{diseaseLabel(p.disease_name)}</h2>
              {@html ICONS.arrowRight}
            </div>
            <div class="profile-meta">
              {p.regions.length} region{p.regions.length === 1 ? '' : 's'} · {monthYear(p.date_from)} – {monthYear(p.date_to)}
            </div>
            <div class="profile-stats">
              <div class="profile-stat">
                <div class="stat-label">Total cases</div>
                <div class="stat-value">{p.total_cases !== undefined ? fmt(p.total_cases) : '—'}</div>
              </div>
              <div class="profile-stat">
                <div class="stat-label">Total deaths</div>
                <div class="stat-value">{p.total_deaths !== undefined ? fmt(p.total_deaths) : '—'}</div>
              </div>
              <div class="profile-stat">
                <div class="stat-label">Peak cases</div>
                <div class="stat-value">{p.peak_cases !== undefined ? fmt(p.peak_cases) : '—'}</div>
                <div class="stat-sub">{p.peak_date ? monthYear(p.peak_date) : '—'}</div>
              </div>
            </div>
            <div class="profile-regions">
              {#each p.regions as r}
                <span class="region-chip">{r}</span>
              {/each}
            </div>
          </a>
        {/each}
      </div>
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

  .profile-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }

  .profile-card {
    display: flex;
    flex-direction: column;
    gap: 10px;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    text-decoration: none;
    color: inherit;
    transition: background 180ms ease;
  }
  .profile-card:hover { background: var(--bg-hover); }

  .profile-header {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .profile-header h2 {
    font-family: var(--serif);
    font-size: 1.1rem;
    font-weight: 600;
    margin: 0;
    color: var(--text);
    flex: 1;
  }
  .profile-header :global(svg) { width: 15px; height: 15px; color: var(--text-faint); flex-shrink: 0; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

  .profile-meta { font-size: 0.78rem; color: var(--text-muted); }

  .profile-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    padding: 10px 0;
    border-top: 1px solid var(--border-soft);
    border-bottom: 1px solid var(--border-soft);
  }
  .profile-stat { display: flex; flex-direction: column; }
  .stat-label {
    font-size: 0.66rem;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .stat-value {
    font-family: var(--sans);
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum';
    font-size: 1.15rem;
    font-weight: 600;
    margin-top: 2px;
    color: var(--text);
  }
  .stat-sub { font-size: 0.7rem; color: var(--text-faint); margin-top: 2px; }

  .profile-regions { display: flex; flex-wrap: wrap; gap: 4px; }
  .region-chip {
    font-size: 0.7rem;
    color: var(--text-muted);
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    border-radius: 8px;
    padding: 1px 8px;
    white-space: nowrap;
  }

  @media (max-width: 760px) {
    .profile-grid { grid-template-columns: 1fr; }
    .profile-stats { grid-template-columns: repeat(3, 1fr); }
  }
</style>
