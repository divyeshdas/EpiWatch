// This page makes fetch calls to a local backend API (localhost:8000).
// SSR would try those fetches from the Node server where the backend is
// unreachable, producing a 500 before the client-side JS even loads.
// Disabling SSR lets the page render entirely in the browser.
export const ssr = false;
