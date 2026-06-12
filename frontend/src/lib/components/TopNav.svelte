<script lang="ts">
  import { page } from '$app/stores';
  import { theme, toggleTheme } from '$lib/stores/theme';
  import { ICONS } from '$lib/icons';

  // Badge count shown on "Alerts" — pages that don't track alerts simply
  // leave this at 0 and the badge stays hidden.
  export let alertCount = 0;

  $: path = $page.url.pathname;

  const primaryItems = [
    { href: '/surveillance', label: 'Overview', icon: ICONS.surveillance, match: (p: string) => p === '/surveillance' || p.startsWith('/surveillance/') },
    { href: '/emergency', label: 'Emergency Response', icon: ICONS.truck, match: (p: string) => p === '/emergency' || p.startsWith('/emergency/') },
    { href: '/alerts', label: 'Alerts', icon: ICONS.bell, match: (p: string) => p === '/alerts' },
    { href: '/data-explorer', label: 'Data Explorer', icon: ICONS.database, match: (p: string) => p === '/data-explorer' },
  ];

  const roadmapItems = [
    { href: '/global-map', label: 'Global Map', icon: ICONS.globe },
    { href: '/trends', label: 'Trends', icon: ICONS.trend },
    { href: '/diseases', label: 'Diseases', icon: ICONS.activity },
    { href: '/reports', label: 'Reports', icon: ICONS.file },
    { href: '/resources', label: 'Resources', icon: ICONS.book },
  ];
</script>

<nav class="topnav">
  <a href="/surveillance" class="topnav-brand">
    <span class="brand-mark">{@html ICONS.brand}</span>
    <span class="brand-name">EpiWatch</span>
  </a>

  <div class="topnav-links">
    {#each primaryItems as item (item.href)}
      <a href={item.href} class="nav-item {item.match(path) ? 'active' : ''}" title={item.label}>
        {@html item.icon}<span>{item.label}</span>
        {#if item.href === '/alerts' && alertCount}<span class="nav-badge">{alertCount}</span>{/if}
      </a>
    {/each}

    <span class="nav-sep" aria-hidden="true"></span>

    {#each roadmapItems as item (item.href)}
      <a href={item.href} class="nav-item soon {path === item.href ? 'active' : ''}" title="{item.label} — coming soon">
        {@html item.icon}
        <span class="soon-badge">Soon</span>
      </a>
    {/each}
  </div>

  <div class="topnav-controls">
    <slot />
    <button class="icon-btn theme-btn" aria-label="Toggle theme" on:click={toggleTheme}>
      {@html $theme === 'light' ? ICONS.moon : ICONS.sun}
    </button>
  </div>
</nav>

<style>
  .topnav {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    height: var(--topbar-h);
    padding: 0 var(--page-pad);
    border-bottom: 1px solid var(--border);
    background: var(--bg-panel);
  }

  .topnav-brand {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex-shrink: 0;
    text-decoration: none;
    color: var(--text);
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
  .brand-name { font-weight: 600; font-size: 0.92rem; }

  .topnav-links {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: 1;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .topnav-links::-webkit-scrollbar { display: none; }

  .nav-sep {
    width: 1px;
    height: 20px;
    background: var(--border);
    margin: 0 4px;
    flex-shrink: 0;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 0.83rem;
    font-family: var(--sans);
    color: var(--text-muted);
    text-decoration: none;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .nav-item :global(svg) { width: 20px; height: 20px; flex-shrink: 0; }
  .nav-item:hover { background: var(--bg-hover); color: var(--text); }
  .nav-item.active {
    color: var(--text);
    background: var(--accent-soft);
    font-weight: 500;
  }

  .nav-badge {
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

  .topnav-controls {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
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

  @media (max-width: 1300px) {
    .nav-item span:not(.soon-badge) { display: none; }
    .nav-item { padding: 8px 10px; }
    .nav-item.active span:not(.soon-badge) { display: inline; }
  }
</style>
