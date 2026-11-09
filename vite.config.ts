import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const target = 'http://localhost:3000';

export default defineConfig({
  root: 'web',
  plugins: [react()],
  build: { outDir: '../dist', emptyOutDir: true, chunkSizeWarningLimit: 1200 },
  server: {
    host: true,
    port: 5173,
    fs: { allow: ['..'] },
    proxy: {
      '/api': target,
      '/uploads': target,
      '/ws': { target: 'ws://localhost:3000', ws: true },
    },
  },
  test: { root: '.', include: ['tests/**/*.test.ts'] },
});
