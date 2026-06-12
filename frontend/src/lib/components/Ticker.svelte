<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { AlertRow } from '$lib/constants';
  import { diseaseLabel, formatZ, monthYear } from '$lib/format';
  import { API_BASE, WS_BASE } from '$lib/api';

  // Ticker-specific severity dots — distinct from the SEVERITY_COLORS used
  // for alert badges elsewhere, per the visual-polish spec.
  const TICKER_SEVERITY_COLORS: Record<string, string> = {
    LOW: '#1D9E75',
    MEDIUM: '#BA7517',
    HIGH: '#E24B4A',
    CRITICAL: '#E24B4A',
  };

  let alerts: AlertRow[] = [];
  let ws: WebSocket | null = null;

  async function load() {
    try {
      const r = await fetch(`${API_BASE}/alerts?limit=12`);
      if (r.ok) alerts = await r.json();
    } catch {
      // Network/API unavailable — ticker falls back to the calm empty state.
    }
  }

  function addAlert(a: AlertRow) {
    if (alerts.find((x) => x.id === a.id)) return;
    alerts = [a, ...alerts].slice(0, 12);
  }

  function connectWs() {
    ws = new WebSocket(`${WS_BASE}/ws`);
    ws.onclose = () => setTimeout(connectWs, 2000);
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

  function detail(a: AlertRow): string {
    const parts: string[] = [];
    parts.push(a.z_score !== null ? `${formatZ(a.z_score)} ${a.severity.toLowerCase()}` : a.severity.toLowerCase());
    if (a.event_date) parts.push(monthYear(a.event_date));
    return parts.join(' · ');
  }

  onMount(() => {
    load();
    connectWs();
  });

  onDestroy(() => {
    ws?.close();
  });
</script>

<div class="ticker">
  <div class="ticker-live">
    <span class="live-mark" aria-hidden="true">
      <span class="live-dot"></span>
    </span>
    <span>Live</span>
  </div>
  <div class="ticker-track">
    {#if alerts.length === 0}
      <div class="ticker-content calm">
        <span class="ticker-item">
          <span class="ticker-dot" style="background: var(--text-faint)"></span>
          <span class="ticker-main">No active outbreak alerts</span>
        </span>
      </div>
    {:else}
      <div class="ticker-content">
        {#each [...alerts, ...alerts] as a, i (i)}
          <span class="ticker-item">
            <span class="ticker-dot" style="background: {TICKER_SEVERITY_COLORS[a.severity]}"></span>
            <span class="ticker-main">{diseaseLabel(a.disease_name)}{a.region ? ` · ${a.region}` : ''}</span>
            <span class="ticker-detail">{detail(a)}</span>
          </span>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .ticker {
    display: flex;
    align-items: stretch;
    height: 38px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--border);
    background: var(--bg-panel);
    font-size: 0.78rem;
    color: var(--text-muted);
  }

  .ticker-live {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: 0 var(--space-4);
    flex-shrink: 0;
    font-weight: 700;
    font-size: 0.66rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--accent);
    border-right: 1px solid var(--border);
    white-space: nowrap;
  }
  .live-mark { display: flex; align-items: center; }
  .live-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--danger);
    animation: live-pulse 2s ease-in-out infinite;
  }
  @keyframes live-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.82); }
  }

  .ticker-track {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    display: flex;
    align-items: center;
  }

  .ticker-content {
    display: flex;
    align-items: center;
    gap: var(--space-12);
    flex-shrink: 0;
    white-space: nowrap;
    padding-left: var(--space-6);
    animation: ticker-scroll 48s linear infinite;
  }
  .ticker-content.calm { animation: none; padding-left: var(--space-4); }
  .ticker-track:hover .ticker-content { animation-play-state: paused; }

  .ticker-item { display: flex; align-items: center; gap: var(--space-2); }
  .ticker-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
  .ticker-main { color: var(--text); font-weight: 500; }
  .ticker-detail { color: var(--text-faint); }

  @keyframes ticker-scroll {
    from { transform: translateX(0); }
    to { transform: translateX(-50%); }
  }
</style>
