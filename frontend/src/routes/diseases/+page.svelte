<script lang="ts">
  import PageShell from '$lib/components/PageShell.svelte';
  import ComingSoon from '$lib/components/ComingSoon.svelte';
  import { ICONS } from '$lib/icons';
</script>

<PageShell section="Diseases" title="Diseases">
  <ComingSoon
    title="Diseases"
    description="Per-disease profiles: history, regions, and severity patterns."
    icon={ICONS.activity}
  />
</PageShell>
