<script lang="ts">
  import { page } from '$app/stores';

  // In-page navigation tabs shown below each main page's topbar. Each entry
  // links to a real route — no dead/"Soon" tabs. The active tab is derived
  // from the current path so it stays correct across client-side navigation.
  export let tabs: { label: string; href: string }[];

  $: path = $page.url.pathname;
</script>

<div class="tabs">
  {#each tabs as t (t.href)}
    <a class="tab {path === t.href ? 'active' : ''}" href={t.href}>{t.label}</a>
  {/each}
</div>

<style>
  .tabs {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    border-bottom: 1px solid var(--border);
  }
  .tab {
    padding: 8px 14px;
    font-size: 0.83rem;
    font-family: var(--sans);
    color: var(--text-muted);
    text-decoration: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--text); border-bottom-color: var(--accent); font-weight: 500; }
</style>
