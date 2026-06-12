<script lang="ts">
  import PageShell from '$lib/components/PageShell.svelte';
  import ComingSoon from '$lib/components/ComingSoon.svelte';
  import { ICONS } from '$lib/icons';
</script>

<PageShell title="Reports">
  <ComingSoon
    title="Reports"
    description="Exportable situation reports for a selected disease and period."
    icon={ICONS.file}
  />
</PageShell>
