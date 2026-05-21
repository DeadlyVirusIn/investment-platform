import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import './index.css';
// Options AI Copilot — Phase A primitives. Loads alongside index.css
// so all `.opt-*` classes resolve regardless of route.
import './styles/options_copilot.css';
import { bootstrapTheme } from '@/lib/ui/theme';
// Phase 11L — guardrails toggle context (UI-only)
import { GuardrailsToggleProvider } from '@/lib/options/guardrailsToggle';

// Apply theme attribute before first render to avoid flash.
bootstrapTheme();

// Self-destruct service worker bootstrap.
//
// The current build ships no SW, but earlier builds did, and some
// browsers still carry a stale registration that intercepts fetches
// and hides new code. We register /sw.js (which immediately
// unregisters itself + clears caches + reloads the page) ONLY when
// a stale registration is detected. Once cleaned, getRegistrations()
// returns empty and we never register again.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    if (regs.length > 0) {
      navigator.serviceWorker.register('/sw.js').catch(() => {
        // best-effort — failure is silent; user can still hard-refresh
      });
    }
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
