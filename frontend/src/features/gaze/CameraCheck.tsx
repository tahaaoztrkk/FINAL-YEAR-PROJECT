/**
 * Kamera kontrol sayfası (`?kamera`).
 *
 * Geliştirici aracıdır, katılımcı görmez. Üç işe yarar:
 *  1. MediaPipe'ın bu bilgisayarda, bu tarayıcıda çalıştığını göstermek.
 *  2. Kare işleme süresini gecikme bütçesine (< 33 ms) karşı ölçmek.
 *  3. Landmark kaydı indirmek: aynı kareler Python'daki features.py'den de
 *     geçirilip TypeScript öznitelikleriyle karşılaştırılır.
 *
 * Kayda görüntü girmez, yalnızca landmark koordinatları ve zaman damgaları.
 */

import { useCallback, useRef, useState } from 'react';
import type { NormalizedLandmark } from '@mediapipe/tasks-vision';

import { useFaceTracking, type FaceFrame } from './useFaceTracking';

const BUDGET_MS = 33;
const RECORD_SECONDS = 5;

// features.py içinde kullanılan noktalar. Çizimde ayrıca vurgulanır ki
// öznitelik hesabının dayandığı noktalar gözle denetlenebilsin.
const IRIS = [468, 469, 470, 471, 472, 473, 474, 475, 476, 477];
const FEATURE_POINTS = [133, 33, 159, 145, 362, 263, 386, 374, 234, 454, 1, 152, 10];

interface RecordedFrame {
  t: number;
  landmarks: number[][];
}

function round6(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

function drawFrame(canvas: HTMLCanvasElement, frame: FaceFrame): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  if (canvas.width !== frame.videoWidth || canvas.height !== frame.videoHeight) {
    canvas.width = frame.videoWidth;
    canvas.height = frame.videoHeight;
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!frame.landmarks) return;

  const w = canvas.width;
  const h = canvas.height;
  const dot = (point: NormalizedLandmark | undefined, radius: number) => {
    if (!point) return;
    ctx.beginPath();
    ctx.arc(point.x * w, point.y * h, radius, 0, Math.PI * 2);
    ctx.fill();
  };

  ctx.fillStyle = 'rgba(154, 164, 184, 0.55)';
  for (const point of frame.landmarks) dot(point, 1);

  ctx.fillStyle = '#ffb547';
  for (const index of FEATURE_POINTS) dot(frame.landmarks[index], 3);

  ctx.fillStyle = '#3ecf8e';
  for (const index of IRIS) dot(frame.landmarks[index], 2.5);
}

function download(name: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export function CameraCheck() {
  const [enabled, setEnabled] = useState(true);
  const [recording, setRecording] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const recordRef = useRef<{ until: number; frames: RecordedFrame[] } | null>(null);
  const finishRef = useRef<() => void>(() => {});

  const onFrame = useCallback((frame: FaceFrame) => {
    if (canvasRef.current) drawFrame(canvasRef.current, frame);

    const record = recordRef.current;
    if (!record) return;
    if (frame.landmarks) {
      record.frames.push({
        t: round6(frame.t),
        landmarks: frame.landmarks.map((p) => [round6(p.x), round6(p.y), round6(p.z)]),
      });
    }
    if (frame.t >= record.until) finishRef.current();
  }, []);

  const { videoRef, status, stats } = useFaceTracking({ enabled, onFrame });

  finishRef.current = () => {
    const record = recordRef.current;
    recordRef.current = null;
    setRecording(false);
    if (!record) return;
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    download(`landmarks-${stamp}.json`, {
      format: 'gaze-aac/landmarks@1',
      created: new Date().toISOString(),
      user_agent: navigator.userAgent,
      delegate: status.state === 'running' ? status.delegate : null,
      video: { width: videoRef.current?.videoWidth, height: videoRef.current?.videoHeight },
      frames: record.frames,
    });
  };

  const startRecording = () => {
    recordRef.current = { until: performance.now() / 1000 + RECORD_SECONDS, frames: [] };
    setRecording(true);
  };

  const withinBudget = stats ? stats.processingP95 < BUDGET_MS : null;

  return (
    <div className="camera-check">
      <header className="camera-check__header">
        <h1>Kamera kontrolü</h1>
        <p>
          Geliştirici sayfası. Görüntü bu bilgisayardan çıkmaz; yalnızca yüz noktaları işlenir.
          Turuncu noktalar öznitelik hesabının kullandığı noktalar, yeşiller iris.
        </p>
      </header>

      <div className="camera-check__body">
        <div className="camera-check__stage">
          <video ref={videoRef} className="camera-check__video" muted playsInline />
          <canvas ref={canvasRef} className="camera-check__overlay" />
          {status.state !== 'running' && (
            <div className="camera-check__veil">
              {status.state === 'loading' && `${status.step}…`}
              {status.state === 'idle' && 'Kamera kapalı'}
              {status.state === 'error' && status.message}
            </div>
          )}
        </div>

        <aside className="camera-check__panel">
          <dl>
            <dt>Durum</dt>
            <dd>
              {status.state === 'running'
                ? 'Çalışıyor'
                : status.state === 'loading'
                  ? 'Yükleniyor'
                  : status.state === 'error'
                    ? 'Hata'
                    : 'Kapalı'}
            </dd>

            <dt>Hızlandırıcı</dt>
            <dd>{status.state === 'running' ? status.delegate : '—'}</dd>

            <dt>Kare hızı</dt>
            <dd>{stats ? `${stats.fps.toFixed(1)} fps` : '—'}</dd>

            <dt>İşleme süresi (p50 / p95)</dt>
            <dd>
              {stats
                ? `${stats.processingP50.toFixed(1)} / ${stats.processingP95.toFixed(1)} ms`
                : '—'}
            </dd>

            <dt>Bütçe ({BUDGET_MS} ms)</dt>
            <dd className={withinBudget === false ? 'is-bad' : withinBudget ? 'is-good' : ''}>
              {withinBudget === null ? '—' : withinBudget ? 'İçinde' : 'Aşıyor'}
            </dd>

            <dt>Yüz bulunan kare</dt>
            <dd>{stats ? `%${Math.round(stats.faceRatio * 100)}` : '—'}</dd>

            <dt>Video</dt>
            <dd>
              {videoRef.current?.videoWidth
                ? `${videoRef.current.videoWidth}×${videoRef.current.videoHeight}`
                : '—'}
            </dd>
          </dl>

          <div className="camera-check__actions">
            <button
              type="button"
              onClick={startRecording}
              disabled={status.state !== 'running' || recording}
            >
              {recording ? 'Kaydediliyor…' : `${RECORD_SECONDS} sn landmark kaydı indir`}
            </button>
            <button type="button" onClick={() => setEnabled((value) => !value)}>
              {enabled ? 'Kamerayı kapat' : 'Kamerayı aç'}
            </button>
            <a href="/">Arayüze dön</a>
          </div>
        </aside>
      </div>
    </div>
  );
}
