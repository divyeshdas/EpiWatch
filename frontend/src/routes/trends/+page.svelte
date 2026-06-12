<script lang="ts">
  import PageShell from '$lib/components/PageShell.svelte';
  import ComingSoon from '$lib/components/ComingSoon.svelte';
  import { ICONS } from '$lib/icons';
</script>

<PageShell title="Trends">
  <ComingSoon
    title="Trends"
    description="Cross-disease trend comparison and growth-rate analysis."
    icon={ICONS.trend}
  />
</PageShell>
