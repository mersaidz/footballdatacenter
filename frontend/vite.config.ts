import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Built into frontend/dist and served by Django under /static/ (see config/urls.py).
// `npm run dev` proxies the API to a running `python manage.py runserver`.
export default defineConfig({
  plugins: [react()],
  base: '/static/',
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 800 },
});
