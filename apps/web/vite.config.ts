import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Phase 14 mobile preview — allow Cloudflare-tunneled hostname so
    // Vite's DNS-rebinding protection doesn't block phone access.
    // Local-only dev (localhost / 192.168.x.x) is always allowed.
    allowedHosts: [
      'mobile-preview.packhunter.xyz',
    ],
    // Phase 16 v1.3 fix — Windows + Git Bash + chokidar misses
    // filesystem events intermittently, leaving Vite serving stale
    // modules even after file edits land. Polling mode costs slight
    // CPU but eliminates the silent stale-cache bug that bit twice
    // this session (hooks.ts useMarketTape miss + holdings tape miss).
    watch: {
      usePolling: true,
      interval: 500,
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, '/api'),
      },
    },
  },
});
