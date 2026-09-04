<script lang="ts">
  import type { Platform } from '$lib/types/api';
  import { PLATFORM_META } from '$lib/utils/format';

  export let platform: Platform;
</script>

<span class="platform-mark {platform}" title={PLATFORM_META[platform].name}
  >{PLATFORM_META[platform].short}</span
>
