<script context="module" lang="ts">
  const modalStack: HTMLElement[] = [];
  const inertOwners = new Map<HTMLElement, { count: number; originallyInert: boolean }>();

  function topModal(): HTMLElement | undefined {
    return modalStack[modalStack.length - 1];
  }

  function retainInert(element: HTMLElement): void {
    const ownership = inertOwners.get(element);
    if (ownership) {
      ownership.count += 1;
      return;
    }
    inertOwners.set(element, { count: 1, originallyInert: element.inert });
    element.inert = true;
  }

  function releaseInert(element: HTMLElement): void {
    const ownership = inertOwners.get(element);
    if (!ownership) return;
    if (ownership.count > 1) {
      ownership.count -= 1;
      return;
    }
    element.inert = ownership.originallyInert;
    inertOwners.delete(element);
  }

  function elementsOutside(node: HTMLElement): HTMLElement[] {
    const outside = new Set<HTMLElement>();
    let branch: HTMLElement = node;
    let parent = branch.parentElement;
    while (parent) {
      for (const sibling of parent.children) {
        if (sibling !== branch && sibling instanceof HTMLElement) outside.add(sibling);
      }
      if (parent === document.body) break;
      branch = parent;
      parent = parent.parentElement;
    }
    return [...outside];
  }
</script>

<script lang="ts">
  import { tick } from 'svelte';
  import { X } from '@lucide/svelte';

  import { trappedFocusTarget } from '$lib/utils/focus';

  export let open = false;
  export let title: string;
  export let description: string | null = null;
  export let wide = false;
  export let dismissible = true;

  const focusableSelector = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])'
  ].join(',');

  let dialog: HTMLElement | null = null;
  let previousFocus: HTMLElement | null = null;
  let inertedElements: HTMLElement[] = [];

  function focusableElements(node: HTMLElement): HTMLElement[] {
    return [...node.querySelectorAll<HTMLElement>(focusableSelector)].filter(
      (element) =>
        element.getAttribute('aria-hidden') !== 'true' &&
        element.closest('[inert]') === null &&
        element.getClientRects().length > 0
    );
  }

  function focusModal(node: HTMLElement): void {
    if (!node.isConnected || topModal() !== node) return;
    const preferred =
      node.querySelector<HTMLElement>('[data-modal-initial-focus], [autofocus]') ??
      node.querySelector<HTMLElement>('.icon-close');
    const target = preferred ?? focusableElements(node)[0] ?? node;
    target.focus({ preventScroll: true });
  }

  function canRestoreFocus(element: HTMLElement | null): element is HTMLElement {
    return element !== null && element.isConnected && element.closest('[inert]') === null;
  }

  function activateModal(node: HTMLElement): { destroy(): void } {
    dialog = node;
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    inertedElements = elementsOutside(node);
    for (const element of inertedElements) retainInert(element);
    modalStack.push(node);
    void tick().then(() => focusModal(node));

    return {
      destroy(): void {
        const wasTop = topModal() === node;
        const stackIndex = modalStack.lastIndexOf(node);
        if (stackIndex >= 0) modalStack.splice(stackIndex, 1);
        for (const element of inertedElements) releaseInert(element);
        inertedElements = [];
        const restoreTarget = previousFocus;
        previousFocus = null;
        dialog = null;
        void tick().then(() => {
          if (!wasTop) return;
          if (canRestoreFocus(restoreTarget)) {
            restoreTarget.focus({ preventScroll: true });
            return;
          }
          const nextModal = topModal();
          if (nextModal) focusModal(nextModal);
        });
      }
    };
  }

  function close(): void {
    if (dismissible) open = false;
  }

  function onKeydown(event: KeyboardEvent): void {
    const currentDialog = dialog;
    if (!open || currentDialog === null || topModal() !== currentDialog) return;
    if (event.key === 'Escape') {
      if (dismissible) {
        event.preventDefault();
        close();
      }
      return;
    }
    if (event.key !== 'Tab') return;

    const focusable = focusableElements(currentDialog);
    if (focusable.length === 0) {
      event.preventDefault();
      currentDialog.focus({ preventScroll: true });
      return;
    }
    const currentIndex = focusable.indexOf(document.activeElement as HTMLElement);
    const targetIndex = trappedFocusTarget(currentIndex, focusable.length, event.shiftKey);
    if (targetIndex !== null) {
      event.preventDefault();
      focusable[targetIndex].focus({ preventScroll: true });
    }
  }
</script>

<svelte:window on:keydown={onKeydown} />

{#if open}
  <div
    class="modal-backdrop"
    role="presentation"
    on:mousedown={(event) => event.currentTarget === event.target && close()}
  >
    <div
      use:activateModal
      bind:this={dialog}
      class:wide
      class="modal"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      tabindex="-1"
    >
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
