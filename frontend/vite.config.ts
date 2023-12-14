import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    allowedHosts: ['.e2b.app', 'localhost', '127.0.0.1'],
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true },
});
