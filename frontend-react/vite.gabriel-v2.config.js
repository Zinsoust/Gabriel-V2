import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

// Quand Vite sert uniquement React en développement, ses fallbacks SPA
// renvoient index.html pour les routes Flask inconnues. Sans proxy, un appel
// au chat devient donc du HTML ("<!doctype …") et un agent peut charger une
// deuxième instance de Gabriel dans son iframe. Ces routes restent servies
// par le backend, aussi bien pour les API que pour les pages agents intégrées.
const backendTarget = process.env.GABRIEL_BACKEND_URL || 'http://127.0.0.1:5050';
const backendRoutes = [
  '/api',
  '/orchestrator_chat',
  '/status',
  '/analyze',
  '/strategize',
  '/creator',
  '/context-chat',
  '/upload-comments-file',
  '/usage',
  '/history',
  '/strategies',
  '/business-context',
  '/strategy-session',
  '/strategy_chat',
  '/voice',
  '/feedback',
  '/credits',
  '/memory',
  '/export',
  '/dossiers',
  '/psychologue',
  '/stratege',
  '/createur',
  '/static',
  '/login',
];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(backendRoutes.map(route => [route, {
      target: backendTarget,
      changeOrigin: true,
    }])),
  },
  build: {
    outDir: resolve(import.meta.dirname, '../static/gabriel-v2'),
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve(import.meta.dirname, 'src/gabriel-v2/main.jsx'),
      output: {
        entryFileNames: 'app.js',
        assetFileNames: asset => asset.name?.endsWith('.css') ? 'app.css' : '[name][extname]',
      },
    },
  },
});
