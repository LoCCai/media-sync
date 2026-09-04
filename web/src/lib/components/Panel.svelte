<script lang="ts">
  export let title: string | null = null;
  export let description: string | null = null;
  export let flush = false;
  export let className = '';
</script>

<section class="panel {className}">
  {#if title || $$slots.header || $$slots.actions}
    <header class="panel-header">
      {#if $$slots.header}
        <slot name="header" />
      {:else}
        <div>
          {#if title}<h2 class="panel-title">{title}</h2>{/if}
          {#if description}<p class="panel-description">{description}</p>{/if}
        </div>
      {/if}
      {#if $$slots.actions}<div class="toolbar"><slot name="actions" /></div>{/if}
    </header>
  {/if}
  <div class:flush class="panel-body">
    <slot />
  </div>
</section>
