import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
// `vitest/config` re-exports Vite's defineConfig with the `test` key typed.
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // `@/` maps to `src/`, keeping imports stable as the feature tree deepens
    // in later parts. Mirrored in tsconfig.app.json `paths`.
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxying in development makes the browser treat the API as same-origin,
      // so the httpOnly refresh cookie is sent without any SameSite exemption.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2022',
    // 'hidden' emits the maps but omits the `//# sourceMappingURL` comment, so
    // they are available for release debugging and error tracking without
    // advertising themselves to every visitor. nginx 404s `.map` on top.
    sourcemap: 'hidden',
    // The largest chunk is React Flow, which is only reached on the simulator
    // and lab routes and is already split by the lazy route imports. Raise the
    // warning threshold so it does not cry wolf on every build.
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        // Split the heavy, rarely-changing libraries into their own chunk so a
        // routine app deploy does not invalidate the whole vendor bundle.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          motion: ['motion'],
          query: ['@tanstack/react-query'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
