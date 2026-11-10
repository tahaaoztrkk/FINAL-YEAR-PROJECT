import { defineConfig, loadEnv, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { createReadStream, existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, URL } from 'node:url';

/**
 * MediaPipe wasm dosyalarını npm paketinin kendisinden `/mediapipe/wasm/`
 * altında sunar (geliştirmede ara katman, derlemede kopya). CDN kullanılsaydı
 * paketteki JS ile wasm'ın sürümü ayrışabilir, internetsiz deney
 * bilgisayarında da hiç yüklenmezdi.
 */
function mediapipeWasm(): Plugin {
  const source = fileURLToPath(
    new URL('./node_modules/@mediapipe/tasks-vision/wasm', import.meta.url),
  );
  const prefix = '/mediapipe/wasm/';
  const types: Record<string, string> = { '.js': 'text/javascript', '.wasm': 'application/wasm' };

  return {
    name: 'mediapipe-wasm',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = req.url?.split('?')[0] ?? '';
        if (!path.startsWith(prefix)) return next();
        const name = path.slice(prefix.length);
        const file = join(source, name);
        if (name.includes('/') || name.includes('..') || !existsSync(file)) return next();
        const ext = name.slice(name.lastIndexOf('.'));
        res.setHeader('Content-Type', types[ext] ?? 'application/octet-stream');
        createReadStream(file).pipe(res);
      });
    },
    generateBundle() {
      for (const name of readdirSync(source)) {
        this.emitFile({
          type: 'asset',
          fileName: `mediapipe/wasm/${name}`,
          source: readFileSync(join(source, name)),
        });
      }
    },
  };
}

export default defineConfig(({ mode }) => {
  // Backend portu .env dosyasından okunur. Windows'ta 8000 sık sık Hyper-V
  // veya WSL tarafından rezerve edilir (WinError 10013); o durumda tek
  // yapılacak şey frontend/.env içinde BACKEND_PORT değerini değiştirmek.
  const env = loadEnv(mode, process.cwd(), '');
  const backendPort = env.BACKEND_PORT ?? '8010';
  const frontendPort = Number(env.FRONTEND_PORT ?? '5173');

  return {
    plugins: [react(), mediapipeWasm()],
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
