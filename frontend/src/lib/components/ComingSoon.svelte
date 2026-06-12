<script lang="ts">
  export let title: string;
  export let description: string;
  export let icon: string;
</script>

<div class="coming-soon">
  <div class="cs-icon">{@html icon}</div>
  <span class="cs-eyebrow">On the roadmap</span>
  <h1 class="cs-title">{title}</h1>
  <p class="cs-desc">{description}</p>
  <a href="/surveillance" class="cs-back">Back to Overview</a>
</div>

<style>
  .coming-soon {
    max-width: 480px;
    margin: 10vh auto 0;
    padding: var(--space-12) var(--space-8);
    text-align: center;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .cs-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    border-radius: 10px;
    background: var(--accent-soft);
    color: var(--accent);
    margin-bottom: var(--space-4);
  }
  .cs-icon :global(svg) { width: 20px; height: 20px; }
  .cs-eyebrow {
    display: block;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-faint);
    margin-bottom: var(--space-3);
  }
  .cs-title {
    font-family: var(--serif);
    font-size: 1.6rem;
    font-weight: 600;
    color: var(--text);
    margin: 0 0 12px;
  }
  .cs-desc {
    font-size: 0.9rem;
    line-height: 1.6;
    color: var(--text-muted);
    margin: 0 0 22px;
  }
  .cs-back {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    font-size: 0.83rem;
    color: var(--accent);
    text-decoration: none;
  }
  .cs-back:hover { text-decoration: underline; }
</style>
