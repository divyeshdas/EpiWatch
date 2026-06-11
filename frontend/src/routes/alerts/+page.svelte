<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import PageShell from '$lib/components/PageShell.svelte';
  import { ICONS } from '$lib/icons';
  import { DISEASE_LABELS, SEVERITY_COLORS, type AlertRow, type Severity } from '$lib/constants';
  import { timeAgo, formatZ, diseaseLabel } from '$lib/format';
  import { downloadCsv } from '$lib/csv';
  import { API_BASE, WS_BASE } from '$lib/api';

  const SEVERITIES: Severity[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

  let alerts: AlertRow[] = [];
  let loading = true;
  let loadError: string | null = null;
  let newAlertIds = new Set<number>();
  let ws: WebSocket | null = null;
  let wsConnected = false;

  let severityFilter: 'all' | Severity = 'all';
  let typeFilter: 'all' | string = 'all';
  let diseaseFilter: 'all' | string = 'all';

  async function loadAlerts() {
    loading = true;
    loadError = null;
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (severityFilter !== 'all') params.set('severity', severityFilter);
      if (typeFilter !== 'all') params.set('type', typeFilter);
      const r = await fetch(`${API_BASE}/alerts?${params}`);
      if (!r.ok) throw new Error('request failed');
      alerts = await r.json();
    } catch {
      loadError = 'Could not reach the alerts API.';
    } finally {
      loading = false;
    }
  }

  function addAlert(a: AlertRow) {
    if (alerts.find(x => x.id === a.id)) return;
    alerts = [a, ...alerts];
    newAlertIds.add(a.id);
    newAlertIds = newAlertIds;
    setTimeout(() => {
      newAlertIds.delete(a.id);
      newAlertIds = newAlertIds;
    }, 2200);
  }

  function connectWs() {
    ws = new WebSocket(`${WS_BASE}/ws`);
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

  onMount(() => {
    loadAlerts();
    connectWs();
  });

  onDestroy(() => {
    ws?.close();
  });

  $: diseaseOptions = Array.from(new Set(alerts.map(a => a.disease_name).filter((d): d is string => !!d)));

  $: visibleAlerts = diseaseFilter === 'all'
    ? alerts
    : alerts.filter(a => a.disease_name === diseaseFilter);

  function downloadCurrentView() {
    const rows = visibleAlerts.map(a => [
      a.severity,
      diseaseLabel(a.disease_name),
      a.region ?? '',
      a.message,
      a.event_date ?? '',
      formatZ(a.z_score),
      a.created_at,
    ]);
    downloadCsv('alerts.csv', ['Severity', 'Disease', 'Region', 'Message', 'Event Date', 'Z-Score', 'Created At'], rows);
  }
</script>

<PageShell section="Alerts" title="Alerts" alertCount={alerts.length}>
  <svelte:fragment slot="topbar-right">
    <button class="topbar-btn" on:click={downloadCurrentView}>{@html ICONS.download}<span>Download</span></button>
  </svelte:fragment>
  <div class="alerts-page">
    <div class="page-header">
      <h1 class="section-title">Alerts</h1>
      <p class="section-sub">
        Outbreak-spike alerts raised by the surveillance detector, newest first.
        <span class="ws-indicator">
          <span class="ws-dot {wsConnected ? 'connected' : ''}"></span>
          {wsConnected ? 'Live' : 'Reconnecting…'}
        </span>
      </p>
    </div>

    <div class="filter-bar">
      <label class="filter">
        <span>Severity</span>
        <select class="quiet-select" bind:value={severityFilter} on:change={loadAlerts}>
          <option value="all">All severities</option>
          {#each SEVERITIES as s}
            <option value={s}>{s}</option>
          {/each}
        </select>
      </label>

      <label class="filter">
        <span>Type</span>
        <select class="quiet-select" bind:value={typeFilter} on:change={loadAlerts}>
          <option value="all">All types</option>
          <option value="OUTBREAK_SPIKE">Outbreak spike</option>
        </select>
      </label>

      <label class="filter">
        <span>Disease</span>
        <select class="quiet-select" bind:value={diseaseFilter}>
          <option value="all">All diseases</option>
          {#each diseaseOptions as d}
            <option value={d}>{diseaseLabel(d)}</option>
          {/each}
        </select>
      </label>
    </div>

    {#if loadError}
      <div class="error-banner">{@html ICONS.bell}{loadError}</div>
    {/if}

    {#if loading && alerts.length === 0}
      <div class="empty-note">Loading alerts…</div>
    {:else if visibleAlerts.length === 0}
      <div class="empty-note">No alerts match the current filters.</div>
    {:else}
      <div class="alert-list">
        {#each visibleAlerts as a (a.id)}
          <div
            class="alert-card {newAlertIds.has(a.id) ? (a.severity === 'HIGH' || a.severity === 'CRITICAL' ? 'alert-pulse' : 'alert-fade') : ''}"
            style="--sev: {SEVERITY_COLORS[a.severity]}"
          >
            <div class="alert-top">
              <span class="alert-sev" style="color: {SEVERITY_COLORS[a.severity]}">{a.severity}</span>
              <span class="alert-disease">{diseaseLabel(a.disease_name)}</span>
              {#if a.region}<span class="alert-region">{a.region}</span>{/if}
              <span class="alert-time">{timeAgo(a.created_at)}</span>
            </div>
            <div class="alert-msg">{a.message}</div>
            <div class="alert-meta">
              {#if a.event_date}<span>Event date {a.event_date}</span>{/if}
              {#if a.z_score !== null}<span>z-score {formatZ(a.z_score)}</span>{/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</PageShell>

<style>
  .alerts-page {
    max-width: 760px;
    margin: 0 auto;
    width: 100%;
  }

  .page-header { margin-bottom: 20px; }
  .section-title {
    font-family: var(--serif);
    font-size: 1.6rem;
    font-weight: 600;
    margin: 0 0 8px;
    color: var(--text);
  }
  .section-sub {
    display: flex;
    align-items: center;
    gap: 14px;
    font-size: 0.85rem;
    color: var(--text-muted);
    margin: 0;
  }
  .ws-indicator { display: flex; align-items: center; gap: 6px; font-size: 0.75rem; }
  .ws-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-faint);
    flex-shrink: 0;
  }
  .ws-dot.connected {
    background: var(--success);
    animation: breathe 2.4s ease-in-out infinite;
  }
  @keyframes breathe {
    0%, 100% { box-shadow: 0 0 0 0 rgba(111, 163, 127, 0.5); }
    50% { box-shadow: 0 0 0 4px rgba(111, 163, 127, 0); }
  }

  .filter-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 20px;
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
    padding: 6px 10px;
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
    padding: 10px 14px;
    margin-bottom: 16px;
  }
  .error-banner :global(svg) { width: 15px; height: 15px; flex-shrink: 0; }

  .empty-note {
    font-size: 0.85rem;
    color: var(--text-faint);
    padding: 32px 8px;
    text-align: center;
    border: 1px dashed var(--border);
    border-radius: var(--radius);
  }

  .alert-list { display: flex; flex-direction: column; gap: 8px; }
  .alert-card {
    background: var(--card);
    border: 1px solid var(--border-soft);
    border-left: 3px solid var(--sev, var(--border));
    border-radius: var(--radius-sm);
    padding: 12px 14px;
  }
  .alert-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .alert-sev { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
  .alert-disease { font-size: 0.8rem; font-weight: 500; color: var(--text); }
  .alert-region { font-size: 0.78rem; color: var(--text-muted); }
  .alert-time {
    margin-left: auto;
    font-size: 0.7rem;
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
  }
  .alert-msg { font-size: 0.85rem; color: var(--text); margin-top: 6px; line-height: 1.5; }
  .alert-meta {
    display: flex;
    gap: 14px;
    margin-top: 6px;
    font-size: 0.74rem;
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
  }

  .alert-fade { animation: alertFade 0.4s ease-out; }
  .alert-pulse { animation: alertFade 0.4s ease-out, alertPulse 0.7s ease-out 2; }
  @keyframes alertFade {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes alertPulse {
    0% { box-shadow: 0 0 0 0 var(--sev); }
    70% { box-shadow: 0 0 0 6px transparent; }
    100% { box-shadow: 0 0 0 0 transparent; }
  }
</style>
