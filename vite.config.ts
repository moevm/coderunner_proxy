import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { defineConfig } from 'vite';

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      // HMR is disabled via DISABLE_HMR env var.
      hmr: process.env.DISABLE_HMR !== 'true',
    },
    build: {
      // Увеличиваем лимит предупреждения до 1000 кБ
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          // Ручное распределение библиотек по чанкам
          manualChunks(id) {
            if (id.includes('node_modules')) {
              // MUI — самая тяжелая часть, выносим отдельно
              if (id.includes('@mui')) {
                return 'vendor-mui';
              }
              // Motion (framer-motion) тоже стоит отделить
              if (id.includes('motion') || id.includes('framer-motion')) {
                return 'vendor-motion';
              }
              // Все остальные зависимости
              return 'vendor';
            }
          },
        },
      },
    },
  };
});