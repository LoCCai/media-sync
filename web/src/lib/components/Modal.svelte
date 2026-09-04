<script lang="ts">
  import { X } from '@lucide/svelte';

  export let open = false;
  export let title: string;
  export let description: string | null = null;
  export let wide = false;
  export let dismissible = true;

  function close(): void {
    if (dismissible) open = false;
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') close();
  }
</script>

<svelte:window on:keydown={onKeydown} />

{#if open}
  <div
    class="modal-backdrop"
    role="presentation"
    on:mousedown={(event) => event.currentTarget === event.target && close()}
  >
    <div class:wide class="modal" role="dialog" aria-modal="true" aria-label={title}>
      <header class="modal-header">
        <div>
          <h2>{title}</h2>
          {#if description}<p>{description}</p>{/if}
        </div>
        {#if dismissible}
          <button class="icon-close" type="button" aria-label="关闭" on:click={close}>
            <X size={18} strokeWidth={1.8} />
          </button>
        {/if}
      </header>
      <div class="modal-body"><slot /></div>
      {#if $$slots.footer}<footer class="modal-footer"><slot name="footer" /></footer>{/if}
    </div>
  </div>
{/if}
