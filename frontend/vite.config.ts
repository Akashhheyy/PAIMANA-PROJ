import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// PAIMANA AI frontend - dev server pinned to port 5173 (backend CORS allows it)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    host: true,
  },
  preview: {
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
});
