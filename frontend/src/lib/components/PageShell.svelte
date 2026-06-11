<script lang="ts">
  import Sidebar from './Sidebar.svelte';
  import { ICONS } from '$lib/icons';

  export let section: string;
  export let title: string;
  export let alertCount = 0;
</script>

<div class="shell">
  <Sidebar {section} {alertCount} />

  <div class="main">
    <header class="topbar">
      <button class="icon-btn menu-btn" aria-label="Menu">{@html ICONS.menu}</button>
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

  .content {
    flex: 1;
    padding: var(--page-pad);
  }

  @media (max-width: 720px) {
    :global(.sidebar) { display: none; }
  }
</style>
