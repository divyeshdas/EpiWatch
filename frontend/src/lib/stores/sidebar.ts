// Sidebar collapsed/expanded state, persisted across page loads.
import { writable } from 'svelte/store';
import { browser } from '$app/environment';

const STORAGE_KEY = 'epiwatch-sidebar-collapsed';

function initial(): boolean {
  if (!browser) return false;
  return localStorage.getItem(STORAGE_KEY) === '1';
}

export const sidebarCollapsed = writable<boolean>(initial());

if (browser) {
  sidebarCollapsed.subscribe((value) => {
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0');
  });
}

export function toggleSidebar(): void {
  sidebarCollapsed.update((v) => !v);
}
