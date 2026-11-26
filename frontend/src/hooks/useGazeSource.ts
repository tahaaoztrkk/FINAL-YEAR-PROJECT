/**
 * Bakış kaynağı.
 *
 * İki kaynak aynı çıktıyı verir: ekranın 0–1 aralığında normalize bir nokta
 * (`onSample`). App bunu `gaze` mesajıyla sunucuya yollar; sunucudaki
 * yumuşatma ve dwell kaynaktan habersiz çalışır.
 *
 * - `mouse`: fare imleci bakış gibi davranır (geliştirme, kamera olmadan).
 * - `webcam`: kamera + tarayıcı içi kalibrasyon modeli (features/gaze/useWebcamGaze).
 *   Bu kestirme yoldur (K1-a, docs/oneri-canli-bakis-mesaji.md): model
 *   tarayıcıda, protokol değişmez. Kalıcı yolda (K1-b) tarayıcı `gaze_features`
 *   gönderecek, eşleme sunucudaki GazeMapper'a geçecek.
 *
 * Hangi kaynağın kullanılacağına sunucu karar verir (`ready.gaze_source`,
 * backend/.env içindeki GAZE_SOURCE; K5).
 */

import { useEffect, useRef } from 'react';

import {
  useWebcamGaze,
  type RawGazeSample,
  type WebcamGaze,
} from '@/features/gaze/useWebcamGaze';

export type { RawGazeSample };

export type GazeSourceKind = 'mouse' | 'webcam';

interface Options {
  kind: GazeSourceKind;
  onSample: (sample: RawGazeSample) => void;
  /** Fare örnekleme hızı. Backend 30 Hz varsayıyor; kamera kare başına bir örnek verir. */
  hz?: number;
  /** Örnek gönderilsin mi (ör. bağlantı açıkken). Kamera bundan bağımsız açık kalır. */
  enabled?: boolean;
}

/** Fare modunda da döner; kamera kapalıyken `phase === 'off'`. */
export function useGazeSource({ kind, onSample, hz = 30, enabled = true }: Options): WebcamGaze {
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

  // Kamera, bağlantı koptuğunda kapanmaz: kalibrasyon tarayıcıda olduğu için
  // yeniden bağlanınca kaldığı yerden devam eder. Yalnızca gönderim durur.
  return useWebcamGaze({
    enabled: kind === 'webcam',
    sending: enabled,
    onSample: (sample) => callbackRef.current(sample),
  });
}
