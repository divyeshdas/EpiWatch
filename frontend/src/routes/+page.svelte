<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  type LiveEvent = {
    type: string;
    payload: Record<string, unknown>;
    timestamp: number;
    received_at: string;
  };

  let events: LiveEvent[] = [];
  let ws: WebSocket | null = null;
  let connected = false;

  function connect() {
    ws = new WebSocket('ws://localhost:8000/ws');

    ws.onopen = () => { connected = true; };

    ws.onclose = () => {
      connected = false;
      setTimeout(connect, 2000);
    };

    ws.onmessage = (msg: MessageEvent) => {
      const e = JSON.parse(msg.data) as LiveEvent;
      e.received_at = new Date().toISOString();
      events = [e, ...events].slice(0, 100);
    };

    ws.onerror = () => ws?.close();
  }

  async function ping() {
    await fetch('http://localhost:8000/demo/ping', { method: 'POST' });
  }

  onMount(connect);
  onDestroy(() => ws?.close());
</script>

<main>
  <h1>EpiWatch — real-time spine demo</h1>
  <p>WebSocket: <strong>{connected ? 'connected' : 'connecting…'}</strong></p>
  <button on:click={ping} disabled={!connected}>POST /demo/ping</button>

  <h2>Event log ({events.length})</h2>

  {#if events.length === 0}
    <p>No events yet. Click the button above — the event should appear here instantly.</p>
  {:else}
    <table>
      <thead>
        <tr>
          <th>received</th>
          <th>type</th>
          <th>payload</th>
        </tr>
      </thead>
      <tbody>
        {#each events as e}
          <tr>
            <td><code>{e.received_at}</code></td>
            <td><strong>{e.type}</strong></td>
            <td><code>{JSON.stringify(e.payload)}</code></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</main>

<style>
  main { font-family: monospace; padding: 2rem; max-width: 900px; }
  h1 { font-size: 1.2rem; margin-bottom: 0.5rem; }
  h2 { font-size: 1rem; margin-top: 1.5rem; }
  button { padding: 0.4rem 1rem; cursor: pointer; }
  table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.85rem; }
  th, td { text-align: left; padding: 0.3rem 0.6rem; border-bottom: 1px solid #ccc; }
  th { font-weight: bold; }
</style>
