<script lang="ts">
  import PageShell from '$lib/components/PageShell.svelte';
  import ComingSoon from '$lib/components/ComingSoon.svelte';
  import { ICONS } from '$lib/icons';
</script>

<PageShell section="Global Map" title="Global Map">
  <ComingSoon
    title="Global Map"
    description="A worldwide outbreak choropleth across all tracked diseases."
    icon={ICONS.globe}
  />
</PageShell>
