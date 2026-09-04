import { writable } from 'svelte/store';

export interface ToastMessage {
  id: number;
  message: string;
  tone: 'success' | 'danger' | 'info';
}

export const toasts = writable<ToastMessage[]>([]);
let nextId = 1;

export function toast(message: string, tone: ToastMessage['tone'] = 'success'): void {
  const id = nextId++;
  toasts.update((items) => [...items, { id, message, tone }]);
  window.setTimeout(() => dismissToast(id), 4200);
}

export function dismissToast(id: number): void {
  toasts.update((items) => items.filter((item) => item.id !== id));
}
