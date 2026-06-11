<script lang="ts">
  import Sidebar from './Sidebar.svelte';
  import { ICONS } from '$lib/icons';
  import { toggleSidebar } from '$lib/stores/sidebar';

  export let section: string;
  export let title: string;
  export let alertCount = 0;
</script>

<div class="shell">
  <Sidebar {section} {alertCount} />

  <div class="main">
    <header class="topbar">
      <button class="icon-btn menu-btn" aria-label="Toggle sidebar" on:click={toggleSidebar}>{@html ICONS.menu}</button>
      <h1 class="page-title">{title}</h1>
      <div class="topbar-right">
        <slot name="topbar-right" />
      </div>
    </header>

    <div class="content">
      <slot />
    </div>
  </div>
</div>

<style>
  .shell {
    display: flex;
    min-height: 100vh;
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.5;
    color: var(--text);
  }

  .main { flex: 1; min-width: 0; display: flex; flex-direction: column; }

  .topbar {
    display: flex;
    align-items: center;
    gap: 14px;
    height: var(--topbar-h);
    padding: 0 24px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-panel);
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .page-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--text);
  }

  .icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    flex-shrink: 0;
  }
  .icon-btn:hover { background: var(--bg-hover); color: var(--text); }
  .icon-btn :global(svg) { width: 16px; height: 16px; }

  .topbar-right { display: flex; align-items: center; gap: 10px; margin-left: auto; }

  /* :global so this styles the Download/etc. buttons tab pages pass into
     the topbar-right slot — slotted content is scoped to the parent, not
     to PageShell. */
  :global(.topbar-btn) {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
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
  :global(.topbar-btn svg) { width: 14px; height: 14px; }

  @media (max-width: 720px) {
    :global(.topbar-btn span) { display: none; }
  }

  .content {
    flex: 1;
    padding: var(--page-pad);
  }

  @media (max-width: 720px) {
    :global(.sidebar) { display: none; }
  }
</style>
