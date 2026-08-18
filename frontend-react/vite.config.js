import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: resolve(import.meta.dirname, '../static/strategy-studio'),
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve(import.meta.dirname, 'src/strategy-studio/main.jsx'),
      output: {
        entryFileNames: 'studio.js',
        assetFileNames: asset => asset.name?.endsWith('.css') ? 'studio.css' : '[name][extname]',
      },
    },
  },
});
