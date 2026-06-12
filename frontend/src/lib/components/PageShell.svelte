<script lang="ts">
  import Ticker from './Ticker.svelte';
  import TopNav from './TopNav.svelte';

  export let title: string;
  export let alertCount = 0;
</script>

<svelte:head>
  <title>EpiWatch — {title}</title>
</svelte:head>

<div class="shell">
  <Ticker />
  <TopNav {alertCount}>
    <slot name="topbar-right" />
  </TopNav>

  <div class="content">
    <slot />
  </div>
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.5;
    color: var(--text);
  }

  .content {
    flex: 1;
    padding: var(--page-pad);
  }

  /* :global so this styles the Download/etc. buttons pages pass into the
     TopNav controls slot — slotted content is scoped to the parent, not
     to PageShell. */
  :global(.topbar-btn) {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border-radius: 6px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-muted);
    font-family: var(--sans);
    font-size: 0.8rem;
    cursor: pointer;
    white-space: nowrap;
  }
  :global(.topbar-btn:hover) { background: var(--bg-hover); color: var(--text); }
  :global(.topbar-btn svg) { width: 16px; height: 16px; }

  @media (max-width: 900px) {
    :global(.topbar-btn span) { display: none; }
  }
</style>
