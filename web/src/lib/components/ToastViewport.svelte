<script lang="ts">
  import { AlertCircle, CheckCircle2, Info, X } from '@lucide/svelte';

  import { dismissToast, toasts } from '$lib/stores/toast';
</script>

<div class="toast-viewport" aria-live="polite">
  {#each $toasts as item (item.id)}
    <div class="toast-card {item.tone}">
      {#if item.tone === 'success'}
        <CheckCircle2 size={17} />
      {:else if item.tone === 'danger'}
        <AlertCircle size={17} />
      {:else}
        <Info size={17} />
      {/if}
      <span>{item.message}</span>
      <button type="button" aria-label="关闭消息" on:click={() => dismissToast(item.id)}
        ><X size={14} /></button
      >
    </div>
  {/each}
</div>

<style>
  .toast-viewport {
    position: fixed;
    z-index: 100;
    right: 18px;
    bottom: 18px;
    display: grid;
    width: min(390px, calc(100vw - 32px));
    gap: 9px;
    pointer-events: none;
  }

  .toast-card {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 10px;
    border: 1px solid #dbe4f0;
    border-radius: 9px;
    padding: 11px 12px;
    background: #fff;
    color: #344158;
    box-shadow: 0 12px 34px rgba(15, 23, 42, 0.16);
    font-size: 12px;
    pointer-events: auto;
    animation: toast-in 180ms ease-out;
  }

  .toast-card.success > :global(svg:first-child) {
    color: #16a34a;
  }

  .toast-card.danger > :global(svg:first-child) {
    color: #dc3545;
  }

  .toast-card.info > :global(svg:first-child) {
    color: #2563eb;
  }

  .toast-card button {
    display: inline-flex;
    width: 25px;
    height: 25px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 5px;
    background: transparent;
    color: #94a3b8;
    cursor: pointer;
  }

  .toast-card button:hover {
    background: #f1f5f9;
    color: #475569;
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translateY(5px);
    }
  }

  @media (max-width: 720px) {
    .toast-viewport {
      right: 16px;
      bottom: 16px;
      left: 16px;
      width: auto;
    }
  }
</style>
