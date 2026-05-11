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
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, '/api'),
      },
    },
  },
});
