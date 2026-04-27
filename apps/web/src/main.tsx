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
