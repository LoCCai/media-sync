<script lang="ts">
  import { statusLabel, statusTone } from '$lib/utils/format';

  export let status: string | null | undefined;
  export let label: string | null = null;
</script>

<span class="status-badge {statusTone(status)}">{label ?? statusLabel(status)}</span>
