/**
 * Kameradan kare kare 478 landmark üreten döngü.
 *
 * Her yeni kamera karesi bir kez işlenir (requestVideoFrameCallback); aynı
 * kareyi iki kez işlemek hem işlemciyi boşa harcar hem de sunucuya kopya
 * örnek gönderir. Desteklemeyen tarayıcıda requestAnimationFrame ile video
 * zamanının ilerleyip ilerlemediğine bakılır.
 *
 * Her kare ``onFrame`` ile dışarı verilir; React durumu her karede değil,
 * yarım saniyede bir güncellenir (istatistikler). 30 Hz'de her kare için
 * render tetiklemek, ölçmeye çalıştığımız gecikmeyi kendimiz üretmek olur.
 */

import { useEffect, useRef, useState, type RefObject } from 'react';
import type { FaceLandmarker, NormalizedLandmark } from '@mediapipe/tasks-vision';

import { CameraError, closeCamera, openCamera } from './camera';
import { LANDMARK_COUNT, loadLandmarker, type Delegate } from './landmarker';

export interface FaceFrame {
  /** 478 nokta; MediaPipe'ın normalize koordinatları. Yüz yoksa ``null``. */
  landmarks: NormalizedLandmark[] | null;
  /** Karenin alındığı an, saniye (performance.now tabanlı, gaze ``t`` ile aynı saat). */
  t: number;
  /** detectForVideo süresi, ms. Gecikme bütçesi: < 33 ms (landmark + öznitelik). */
  processingMs: number;
  videoWidth: number;
  videoHeight: number;
}

export type TrackingStatus =
  | { state: 'idle' }
  | { state: 'loading'; step: string }
  | { state: 'running'; delegate: Delegate }
  | { state: 'error'; message: string };

export interface TrackingStats {
  fps: number;
  processingP50: number;
  processingP95: number;
  /** Son pencerede yüz bulunan karelerin oranı, 0–1. */
  faceRatio: number;
  frames: number;
}

interface Options {
  enabled: boolean;
  onFrame?: (frame: FaceFrame) => void;
}

interface Result {
  videoRef: RefObject<HTMLVideoElement>;
  status: TrackingStatus;
  stats: TrackingStats | null;
}

const STATS_WINDOW = 90; // ~3 sn
const STATS_INTERVAL_MS = 500;

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const index = Math.min(sorted.length - 1, Math.floor(p * sorted.length));
  return sorted[index] ?? 0;
}

export function useFaceTracking({ enabled, onFrame }: Options): Result {
  const videoRef = useRef<HTMLVideoElement>(null);
  const onFrameRef = useRef(onFrame);
  onFrameRef.current = onFrame;

  const [status, setStatus] = useState<TrackingStatus>({ state: 'idle' });
  const [stats, setStats] = useState<TrackingStats | null>(null);

  useEffect(() => {
    if (!enabled) {
      setStatus({ state: 'idle' });
      setStats(null);
      return;
    }

    const video = videoRef.current;
    if (!video) return;

    let cancelled = false;
    let stream: MediaStream | null = null;
    let landmarker: FaceLandmarker | null = null;
    let frameHandle = 0;
    let statsTimer = 0;
    let lastTimestampMs = -1;
    let lastVideoTime = -1;
    let frameCount = 0;

    const processing: number[] = [];
    const frameTimes: number[] = [];
    const faceFound: boolean[] = [];

    const push = <T,>(buffer: T[], value: T) => {
      buffer.push(value);
      if (buffer.length > STATS_WINDOW) buffer.shift();
    };

    const processFrame = () => {
      if (cancelled || !landmarker) return;

      // detectForVideo kesin artan zaman damgası ister; aynı ms'de iki kare
      // gelirse ikincisi hata verir.
      const now = performance.now();
      const timestampMs = now <= lastTimestampMs ? lastTimestampMs + 1 : now;
      lastTimestampMs = timestampMs;

      const started = performance.now();
      let landmarks: NormalizedLandmark[] | null = null;
      try {
        const result = landmarker.detectForVideo(video, timestampMs);
        const face = result.faceLandmarks[0];
        landmarks = face && face.length >= LANDMARK_COUNT ? face : null;
      } catch (error) {
        console.error('detectForVideo başarısız', error);
      }
      const processingMs = performance.now() - started;

      frameCount += 1;
      push(processing, processingMs);
      push(frameTimes, now);
      push(faceFound, landmarks !== null);

      onFrameRef.current?.({
        landmarks,
        t: now / 1000,
        processingMs,
        videoWidth: video.videoWidth,
        videoHeight: video.videoHeight,
      });
    };

    const useVideoFrameCallback = 'requestVideoFrameCallback' in HTMLVideoElement.prototype;

    const scheduleNext = () => {
      if (cancelled) return;
      if (useVideoFrameCallback) {
        frameHandle = video.requestVideoFrameCallback(() => {
          processFrame();
          scheduleNext();
        });
      } else {
        frameHandle = requestAnimationFrame(() => {
          if (video.currentTime !== lastVideoTime) {
            lastVideoTime = video.currentTime;
            processFrame();
          }
          scheduleNext();
        });
      }
    };

    const publishStats = () => {
      const sorted = [...processing].sort((a, b) => a - b);
      const first = frameTimes[0];
      const last = frameTimes[frameTimes.length - 1];
      const span = first !== undefined && last !== undefined ? (last - first) / 1000 : 0;
      setStats({
        fps: span > 0 ? (frameTimes.length - 1) / span : 0,
        processingP50: percentile(sorted, 0.5),
        processingP95: percentile(sorted, 0.95),
        faceRatio: faceFound.length ? faceFound.filter(Boolean).length / faceFound.length : 0,
        frames: frameCount,
      });
    };

    const start = async () => {
      try {
        setStatus({ state: 'loading', step: 'Kamera açılıyor' });
        const opened = await openCamera(video);
        if (cancelled) {
          // Temizlik bu await sürerken çalıştıysa akışı o göremedi; burada kapat.
          closeCamera(video, opened);
          return;
        }
        stream = opened;

        setStatus({ state: 'loading', step: 'Yüz modeli yükleniyor' });
        const loaded = await loadLandmarker();
        if (cancelled) {
          loaded.landmarker.close();
          return;
        }
        landmarker = loaded.landmarker;

        setStatus({ state: 'running', delegate: loaded.delegate });
        statsTimer = window.setInterval(publishStats, STATS_INTERVAL_MS);
        scheduleNext();
      } catch (error) {
        if (cancelled) return;
        const message =
          error instanceof CameraError || error instanceof Error ? error.message : String(error);
        setStatus({ state: 'error', message });
      }
    };

    void start();

    return () => {
      cancelled = true;
      if (useVideoFrameCallback) video.cancelVideoFrameCallback(frameHandle);
      else cancelAnimationFrame(frameHandle);
      window.clearInterval(statsTimer);
      landmarker?.close();
      landmarker = null;
      closeCamera(video, stream);
    };
  }, [enabled]);

  return { videoRef, status, stats };
}
