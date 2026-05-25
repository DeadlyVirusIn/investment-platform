import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import './index.css';
import { bootstrapTheme } from '@/lib/ui/theme';
// Phase 11L — guardrails toggle context (UI-only)
import { GuardrailsToggleProvider } from '@/lib/options/guardrailsToggle';

// Apply theme attribute before first render to avoid flash.
bootstrapTheme();

// Service-worker eviction (self-healing).
//
// Earlier builds shipped a service worker; the current build ships
// none. A leftover SW intercepts fetches and serves a stale cached
// bundle, hiding new code — e.g. an old dark rail painted over a fresh
// light shell. The previous approach registered a self-destruct
// /sw.js, which silently fails if /sw.js is unreachable, leaving the
// stale SW in place. Instead, evict directly and unconditionally:
// unregister every SW and delete every Cache Storage entry, then
// reload ONCE so this page is served fresh from the network.
//
// localStorage / IndexedDB are NOT touched. Self-terminating: after
// the reload getRegistrations() is empty, so the branch is a no-op and
// there is no reload loop.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    if (regs.length === 0) return;
    Promise.all(regs.map((r) => r.unregister()))
      .then(() =>
        'caches' in window
          ? caches.keys().then((keys) =>
              Promise.all(keys.map((k) => caches.delete(k))))
          : undefined,
      )
      .then(() => {
        window.location.reload();
      })
      .catch(() => {
        // best-effort — user can still hard-refresh
      });
  }).catch(() => {
    // best-effort
  });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <GuardrailsToggleProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </GuardrailsToggleProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
