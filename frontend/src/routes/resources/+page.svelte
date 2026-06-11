<script lang="ts">
  import PageShell from '$lib/components/PageShell.svelte';
  import ComingSoon from '$lib/components/ComingSoon.svelte';
  import { ICONS } from '$lib/icons';
</script>

<PageShell section="Resources" title="Resources">
  <ComingSoon
    title="Resources"
    description="Methodology, data sources, and references."
    icon={ICONS.book}
  />
</PageShell>
