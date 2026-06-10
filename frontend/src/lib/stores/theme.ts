// Light/dark theme store for the surveillance dashboard. Defaults to dark —
// this is a command-center view, not a document, so dark is the "normal"
// state rather than a toggle-on.
//
// Persistence: the chosen theme is written to localStorage and mirrored onto
// `<html data-theme="...">`, where the page's CSS custom properties branch on
// it. A small inline script in app.html applies the stored value before
// hydration so there's no flash of the wrong theme on reload.
import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'epiwatch-theme';

function initialTheme(): Theme {
  if (!browser) return 'dark';
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === 'light' ? 'light' : 'dark';
}

export const theme = writable<Theme>(initialTheme());

if (browser) {
  theme.subscribe((value) => {
    localStorage.setItem(STORAGE_KEY, value);
    document.documentElement.dataset.theme = value;
  });
}

export function toggleTheme(): void {
  theme.update((t) => (t === 'light' ? 'dark' : 'light'));
}
