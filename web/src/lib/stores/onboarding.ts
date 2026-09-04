import { browser } from '$app/environment';
import { get, writable } from 'svelte/store';

const STORAGE_KEY = 'media-sync.onboarding.v1';
const ACK_VERSION = 1;

export const onboardingAccepted = writable(false);
export const onboardingHydrated = writable(false);

export function hydrateOnboarding(): void {
  if (!browser) return;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const payload = raw ? (JSON.parse(raw) as Record<string, unknown>) : null;
    onboardingAccepted.set(payload?.version === ACK_VERSION && typeof payload.accepted_at === 'string');
  } catch {
    onboardingAccepted.set(false);
  } finally {
    onboardingHydrated.set(true);
  }
}

export function acceptOnboarding(): void {
  if (!browser) return;
  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      version: ACK_VERSION,
      license: 'NON-COMMERCIAL LEARNING LICENSE 1.1',
      accepted_at: new Date().toISOString()
    })
  );
  onboardingAccepted.set(true);
  onboardingHydrated.set(true);
  window.dispatchEvent(new CustomEvent('media-sync:onboarding-accepted'));
}

export function resetOnboarding(): void {
  if (!browser) return;
  window.localStorage.removeItem(STORAGE_KEY);
  onboardingAccepted.set(false);
}

export function mediaCrawlerGate(): {
  enable_mediacrawler: true;
  accept_mediacrawler_license: true;
} {
  if (!get(onboardingAccepted)) throw new Error('请先完成首次使用确认。');
  return { enable_mediacrawler: true, accept_mediacrawler_license: true };
}
