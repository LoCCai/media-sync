<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  import '../app.css';
  import AppShell from '$lib/components/AppShell.svelte';
  import OnboardingModal from '$lib/components/OnboardingModal.svelte';
  import OperatorLogin from '$lib/components/OperatorLogin.svelte';
  import ToastViewport from '$lib/components/ToastViewport.svelte';
  import { hydrateOnboarding } from '$lib/stores/onboarding';
  import { operatorAuth, operatorReturnPath } from '$lib/stores/operator-auth';
  import { toasts } from '$lib/stores/toast';

  let returnPending = false;
  let returnPath: string | null = null;
  $: if ($operatorAuth.phase !== 'authenticated') toasts.set([]);
  $: if ($operatorAuth.phase === 'authenticated' && returnPending) {
    returnPending = false;
    void goto(returnPath ?? '/', { replaceState: true });
  }

  onMount(() => {
    returnPath = operatorReturnPath(window.location.search);
    returnPending =
      window.location.pathname === '/' && new URLSearchParams(window.location.search).has('return_to');
    hydrateOnboarding();
    void operatorAuth.checkSession();
    const recheck = (): void => {
      if (operatorAuth.snapshot.phase === 'authenticated') void operatorAuth.checkSession();
    };
    window.addEventListener('focus', recheck);
    return () => {
      window.removeEventListener('focus', recheck);
      operatorAuth.dispose();
    };
  });
</script>

{#if $operatorAuth.phase === 'authenticated'}
  {#key $operatorAuth.epoch}
    <AppShell><slot /></AppShell>
    <OnboardingModal />
    <ToastViewport />
  {/key}
{:else}
  <OperatorLogin />
{/if}
