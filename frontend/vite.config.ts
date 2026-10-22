import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig(({ mode }) => {
  // Backend portu .env dosyasından okunur. Windows'ta 8000 sık sık Hyper-V
  // veya WSL tarafından rezerve edilir (WinError 10013); o durumda tek
  // yapılacak şey frontend/.env içinde BACKEND_PORT değerini değiştirmek.
  const env = loadEnv(mode, process.cwd(), '');
  const backendPort = env.BACKEND_PORT ?? '8000';
  const frontendPort = Number(env.FRONTEND_PORT ?? '5173');

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      port: frontendPort,
      // Backend'e vekil: arayüz tek kökenden çalışır, CORS sorunu çıkmaz.
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/ws': {
          target: `ws://127.0.0.1:${backendPort}`,
          ws: true,
        },
      },
    },
  };
});
