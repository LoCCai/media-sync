<script lang="ts">
  import { Inbox } from '@lucide/svelte';

  export let title: string;
  export let description: string;
</script>

<div class="empty-state">
  <div>
    <span class="empty-state-icon"><Inbox size={21} strokeWidth={1.7} /></span>
    <h3>{title}</h3>
    <p>{description}</p>
    {#if $$slots.default}<div class="button-row" style="justify-content:center;margin-top:14px">
        <slot />
      </div>{/if}
  </div>
</div>
