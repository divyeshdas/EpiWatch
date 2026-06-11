// Light/dark theme store for the surveillance dashboard.
//
// Default: if the user hasn't made an explicit choice yet, follow the local
// clock — light during the day (06:00–18:00), dark in the evening/night.
// The manual toggle always overrides this and is persisted to localStorage,
// so once a user picks a theme it sticks regardless of time of day.
//
// Persistence: an explicit choice is written to localStorage and mirrored
// onto `<html data-theme="...">`, where the page's CSS custom properties
// branch on it. A small inline script in app.html applies the same logic
// before hydration so there's no flash of the wrong theme on reload.
import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'epiwatch-theme';

function timeBasedTheme(): Theme {
  const hour = new Date().getHours();
  return hour >= 6 && hour < 18 ? 'light' : 'dark';
}

function initialTheme(): Theme {
  if (!browser) return 'dark';
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark') return stored;
  return timeBasedTheme();
}

export const theme = writable<Theme>(initialTheme());

if (browser) {
  theme.subscribe((value) => {
    document.documentElement.dataset.theme = value;
  });
}

export function toggleTheme(): void {
  theme.update((t) => {
    const next: Theme = t === 'light' ? 'dark' : 'light';
    localStorage.setItem(STORAGE_KEY, next);
    return next;
  });
}
