/**
 * Bakış kaynağı.
 *
 * Geliştirme sırasında fare imleci bakış gibi davranır; böylece arayüz
 * kamera ve kalibrasyon hazır olmadan uçtan uca çalışır. Kişi 3 bu sayede
 * Kişi 1'in modülünü beklemez.
 *
 * Kamera moduna geçiş tek satır: `useGazeSource('webcam')`. MediaPipe hattı
 * tarayıcıda çalıştığında bu dosya landmark'ları öznitelik vektörüne çevirip
 * sunucuya gönderir; sunucu kalibrasyon modeliyle ekran koordinatına çevirir.
 */

import { useEffect, useRef } from 'react';

export type GazeSourceKind = 'mouse' | 'webcam';

export interface RawGazeSample {
  x: number;
  y: number;
  t: number;
  confidence: number;
}

interface Options {
  kind: GazeSourceKind;
  onSample: (sample: RawGazeSample) => void;
  /** Örnekleme hızı. Backend 30 Hz varsayıyor. */
  hz?: number;
  enabled?: boolean;
}

export function useGazeSource({ kind, onSample, hz = 30, enabled = true }: Options): void {
  // Geri çağrıyı ref'te tut: her render'da efekti yeniden kurmak,
  // örnekleme zamanlayıcısını sıfırlar ve akışı kesintiye uğratır.
  const callbackRef = useRef(onSample);
  callbackRef.current = onSample;

  useEffect(() => {
    if (!enabled || kind !== 'mouse') return;

    const latest = { x: 0.5, y: 0.5 };

    const handleMove = (event: MouseEvent) => {
      latest.x = event.clientX / window.innerWidth;
      latest.y = event.clientY / window.innerHeight;
    };

    window.addEventListener('mousemove', handleMove);
    const interval = window.setInterval(() => {
      callbackRef.current({
        x: Math.min(1, Math.max(0, latest.x)),
        y: Math.min(1, Math.max(0, latest.y)),
        t: performance.now() / 1000,
        confidence: 1,
      });
    }, 1000 / hz);

    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.clearInterval(interval);
    };
  }, [kind, hz, enabled]);

  useEffect(() => {
    if (!enabled || kind !== 'webcam') return;
    // TODO(Kişi 1): MediaPipe FaceLandmarker hattını buraya bağla.
    // 1. getUserMedia ile kamera akışını al
    // 2. FaceLandmarker.detectForVideo ile 478 landmark çıkar
    // 3. Öznitelik vektörünü hesapla (backend/gaze/features.py ile aynı sıra)
    // 4. Kalibrasyon modundaysa calibration_sample, değilse gaze gönder
    console.warn('Kamera tabanlı bakış kaynağı henüz bağlanmadı.');
  }, [kind, enabled]);
}
