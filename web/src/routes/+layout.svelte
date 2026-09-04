<script lang="ts">
  import { onMount } from 'svelte';

  import '../app.css';
  import AppShell from '$lib/components/AppShell.svelte';
  import OnboardingModal from '$lib/components/OnboardingModal.svelte';
  import ToastViewport from '$lib/components/ToastViewport.svelte';
  import { hydrateOnboarding } from '$lib/stores/onboarding';

  onMount(hydrateOnboarding);
</script>

<AppShell><slot /></AppShell>
<OnboardingModal />
<ToastViewport />
