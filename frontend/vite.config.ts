import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Built into frontend/dist and served by Django under /static/ (see config/urls.py).
// `npm run dev` proxies the API to a running `python manage.py runserver`.
// `vite build --mode demo` makes a server-less demo in dist-demo/ (see src/demo.ts).
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === 'demo' ? './' : '/static/',
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { outDir: mode === 'demo' ? 'dist-demo' : 'dist', emptyOutDir: true, chunkSizeWarningLimit: 800 },
}));
