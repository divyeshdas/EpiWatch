<script lang="ts">
  import { page } from '$app/stores';
  import { theme, toggleTheme } from '$lib/stores/theme';
  import { sidebarCollapsed } from '$lib/stores/sidebar';
  import { ICONS } from '$lib/icons';

  // Brand subtitle under "EpiWatch" — varies per section (Surveillance,
  // Emergency, Alerts, ...).
  export let section: string;

  // Badge count shown next to "Alerts" — pages that don't track alerts
  // simply leave this at 0 and the badge stays hidden.
  export let alertCount = 0;

  $: path = $page.url.pathname;
</script>

<aside class="sidebar {$sidebarCollapsed ? 'collapsed' : ''}">
  <div class="sidebar-brand">
    <span class="brand-mark">{@html ICONS.brand}</span>
    <div class="brand-text">
      <div class="brand-name">EpiWatch</div>
      <div class="brand-section">{section}</div>
    </div>
  </div>

  <nav class="sidebar-nav">
    <a href="/surveillance" class="nav-item {path === '/surveillance' || path.startsWith('/surveillance/') ? 'active' : ''}">{@html ICONS.surveillance}<span>Overview</span></a>
    <a href="/emergency" class="nav-item {path === '/emergency' || path.startsWith('/emergency/') ? 'active' : ''}">{@html ICONS.truck}<span>Emergency Response</span></a>
    <a href="/alerts" class="nav-item {path === '/alerts' ? 'active' : ''}">
      {@html ICONS.bell}<span>Alerts</span>
      {#if alertCount}<span class="nav-badge">{alertCount}</span>{/if}
    </a>
    <a href="/data-explorer" class="nav-item {path === '/data-explorer' ? 'active' : ''}">{@html ICONS.database}<span>Data Explorer</span></a>
    <a href="/global-map" class="nav-item {path === '/global-map' ? 'active' : ''}">
      {@html ICONS.globe}<span>Global Map</span>
      <span class="soon-badge">Soon</span>
    </a>
    <a href="/trends" class="nav-item {path === '/trends' ? 'active' : ''}">
      {@html ICONS.trend}<span>Trends</span>
      <span class="soon-badge">Soon</span>
    </a>
    <a href="/diseases" class="nav-item {path === '/diseases' ? 'active' : ''}">
      {@html ICONS.activity}<span>Diseases</span>
      <span class="soon-badge">Soon</span>
    </a>
    <a href="/reports" class="nav-item {path === '/reports' ? 'active' : ''}">
      {@html ICONS.file}<span>Reports</span>
      <span class="soon-badge">Soon</span>
    </a>
    <a href="/resources" class="nav-item {path === '/resources' ? 'active' : ''}">
      {@html ICONS.book}<span>Resources</span>
      <span class="soon-badge">Soon</span>
    </a>
  </nav>

  <div class="sidebar-bottom">
    <span class="nav-item inert">{@html ICONS.settings}<span>Settings</span></span>
    <button class="nav-item theme-item" on:click={toggleTheme}>
      {@html $theme === 'light' ? ICONS.moon : ICONS.sun}
      <span>{$theme === 'light' ? 'Dark mode' : 'Light mode'}</span>
    </button>
    <span class="nav-item inert">{@html ICONS.help}<span>Help</span></span>
  </div>
</aside>

<style>
  .sidebar {
    width: var(--sidebar-w);
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 16px 12px;
    background: var(--bg-panel);
    border-right: 1px solid var(--border);
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-x: hidden;
    overflow-y: auto;
    transition: width var(--ease-drawer, 220ms ease);
  }
  .sidebar::-webkit-scrollbar { width: 6px; }
  .sidebar::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .sidebar.collapsed { width: 64px; padding-left: 10px; padding-right: 10px; }
  .sidebar.collapsed .brand-text,
  .sidebar.collapsed .nav-item span,
  .sidebar.collapsed .nav-badge,
  .sidebar.collapsed .soon-badge {
    display: none;
  }
  .sidebar.collapsed .sidebar-brand { justify-content: center; padding-left: 0; padding-right: 0; }
  .sidebar.collapsed .nav-item { justify-content: center; gap: 0; }

  .sidebar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 10px 16px;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--border-soft);
  }
  .brand-mark {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 7px;
    background: var(--accent-soft);
    color: var(--accent);
    flex-shrink: 0;
  }
  .brand-mark :global(svg) { width: 18px; height: 18px; }
  .brand-name { font-weight: 600; font-size: 0.92rem; color: var(--text); }
  .brand-section {
    font-size: 0.66rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 2px;
  }

  .sidebar-nav { display: flex; flex-direction: column; gap: 1px; flex: 1; }
  .sidebar-bottom {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding-top: 8px;
    margin-top: 8px;
    border-top: 1px solid var(--border-soft);
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 0.83rem;
    font-family: var(--sans);
    color: var(--text-muted);
    text-decoration: none;
    background: transparent;
    border: none;
    width: 100%;
    text-align: left;
    cursor: pointer;
    position: relative;
  }
  .nav-item :global(svg) { width: 17px; height: 17px; flex-shrink: 0; }
  a.nav-item:hover,
  .theme-item:hover { background: var(--bg-hover); color: var(--text); }
  .nav-item.active {
    color: var(--text);
    background: var(--accent-soft);
    font-weight: 500;
  }
  .nav-item.active::before {
    content: '';
    position: absolute;
    left: -12px;
    top: 8px;
    bottom: 8px;
    width: 3px;
    border-radius: 0 2px 2px 0;
    background: var(--accent);
  }
  .nav-item.inert { cursor: default; opacity: 0.5; }
  .nav-badge {
    margin-left: auto;
    font-family: var(--sans);
    font-variant-numeric: tabular-nums;
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--danger);
    background: rgba(220, 79, 69, 0.14);
    border-radius: 8px;
    padding: 1px 6px;
  }
  .soon-badge {
    margin-left: auto;
    font-size: 0.6rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-faint);
    background: var(--bg-sunken);
    border: 1px solid var(--border-soft);
    border-radius: 8px;
    padding: 1px 6px;
  }

  @media (max-width: 720px) {
    .sidebar { display: none; }
  }
</style>
