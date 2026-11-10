/**
 * Bakış ölçüm sayfası (`?olcum`).
 *
 * Geliştirici aracıdır, katılımcı görmez. Bilinen ekran noktalarına bakılırken
 * landmark kaydeder: 9 noktalı kalibrasyon, ızgaraya denk gelmeyen 8 doğrulama
 * noktası, sonra baş oynatılmış halde aynı 8 nokta. Model eğitimi ve hata
 * hesabı çevrimdışı, Python'daki GazeMapper ile yapılır; böylece aynı kayıtla
 * farklı öznitelikler denenebilir.
 *
 * Kayda görüntü girmez, yalnızca landmark koordinatları ve hedefler.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { useFaceTracking, type FaceFrame } from './useFaceTracking';

// config.py: calibration_discard_ms ve calibration_hold_ms. Önceki süre, gözün
// yeni noktaya varması için.
const PREP_MS = 600;
const DISCARD_MS = 300;
const HOLD_MS = 1200;

type Point = readonly [number, number];
type BlockName = 'calibration' | 'validation' | 'head_moved';

const GRID: readonly Point[] = [0.1, 0.5, 0.9].flatMap((y) =>
  [0.1, 0.5, 0.9].map((x): Point => [x, y]),
);

const VALIDATION: readonly Point[] = [
  [0.3, 0.3],
  [0.7, 0.3],
  [0.3, 0.7],
  [0.7, 0.7],
  [0.2, 0.5],
  [0.8, 0.5],
  [0.5, 0.2],
  [0.5, 0.8],
];

interface RecordedFrame {
  block: BlockName;
  target: Point;
  t: number;
  landmarks: number[][];
}

type Phase = 'setup' | 'running' | 'head_pause' | 'done';
type Glasses = 'gozluksuz' | 'gozluklu';
type Resolution = '640' | '1280';

const SIZES: Record<Resolution, { width: number; height: number }> = {
  '640': { width: 640, height: 480 },
  '1280': { width: 1280, height: 720 },
};

function round5(value: number): number {
  return Math.round(value * 1e5) / 1e5;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

/** Noktaların sırası her koşuda karışır: göz sırayı öğrenip önden gitmesin. */
function shuffled<T>(items: readonly T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j] as T, copy[i] as T];
  }
  return copy;
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

export function GazeMeasure() {
  const [phase, setPhase] = useState<Phase>('setup');
  const [point, setPoint] = useState<Point | null>(null);
  const [collecting, setCollecting] = useState(false);
  const [glasses, setGlasses] = useState<Glasses>('gozluksuz');
  const [resolution, setResolution] = useState<Resolution>('640');
  const [frameCount, setFrameCount] = useState(0);

  const collectRef = useRef<{ block: BlockName; target: Point } | null>(null);
  const framesRef = useRef<RecordedFrame[]>([]);
  const resumeRef = useRef<() => void>(() => {});

  const onFrame = useCallback((frame: FaceFrame) => {
    const collect = collectRef.current;
    if (!collect || !frame.landmarks) return;
    framesRef.current.push({
      block: collect.block,
      target: collect.target,
      t: round5(frame.t),
      landmarks: frame.landmarks.map((p) => [round5(p.x), round5(p.y), round5(p.z)]),
    });
  }, []);

  const { videoRef, status, stats } = useFaceTracking({ enabled: true, onFrame });

  // Çözünürlük akış açıkken değiştirilir; kamera kodu tek ayarla kalır.
  useEffect(() => {
    if (status.state !== 'running') return;
    const stream = videoRef.current?.srcObject as MediaStream | null;
    const track = stream?.getVideoTracks()[0];
    if (!track) return;
    const size = SIZES[resolution];
    track
      .applyConstraints({ width: { ideal: size.width }, height: { ideal: size.height } })
      .catch((error: unknown) => console.warn('Çözünürlük değiştirilemedi', error));
  }, [resolution, status.state, videoRef]);

  const runBlock = async (block: BlockName, points: readonly Point[]) => {
    for (const target of shuffled(points)) {
      setPoint(target);
      setCollecting(false);
      await sleep(PREP_MS + DISCARD_MS);
      collectRef.current = { block, target };
      setCollecting(true);
      await sleep(HOLD_MS);
      collectRef.current = null;
    }
    setPoint(null);
    setCollecting(false);
  };

  const start = async () => {
    framesRef.current = [];
    setPhase('running');
    await document.documentElement.requestFullscreen().catch(() => undefined);
    // Tam ekrana geçiş bitsin, ilk nokta yerinde görünsün.
    await sleep(800);

    await runBlock('calibration', GRID);
    await runBlock('validation', VALIDATION);

    setPhase('head_pause');
    await new Promise<void>((resolve) => {
      resumeRef.current = resolve;
    });
    setPhase('running');
    await sleep(800);
    await runBlock('head_moved', VALIDATION);

    const video = videoRef.current;
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const size = `${video?.videoWidth ?? 0}x${video?.videoHeight ?? 0}`;
    download(`olcum-${glasses}-${size}-${stamp}.json`, {
      format: 'gaze-aac/gaze-measure@1',
      created: new Date().toISOString(),
      user_agent: navigator.userAgent,
      glasses,
      video: { width: video?.videoWidth, height: video?.videoHeight },
      screen: { width: window.innerWidth, height: window.innerHeight },
      frames: framesRef.current,
    });
    setFrameCount(framesRef.current.length);
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => undefined);
    setPhase('done');
  };

  const fullscreenStage = phase === 'running' || phase === 'head_pause';

  return (
    <div style={{ padding: 24, color: 'var(--text)', maxWidth: 720, margin: '0 auto' }}>
      <video
        ref={videoRef}
        muted
        playsInline
        style={
          fullscreenStage
            ? { position: 'fixed', width: 1, height: 1, opacity: 0 }
            : { width: 320, borderRadius: 10, transform: 'scaleX(-1)', background: '#000' }
        }
      />

      {phase === 'setup' && (
        <>
          <h1>Bakış ölçümü</h1>
          <p>
            Noktalara yalnızca gözlerinle bak, ölçüm boyunca başını sabit tut. Yaklaşık bir dakika
            sürer. Sonunda bir dosya iner; içinde görüntü yok, yalnızca yüz noktaları var.
          </p>
          <p>
            Durum:{' '}
            {status.state === 'running'
              ? `hazır (${status.delegate}, ${stats ? stats.fps.toFixed(0) : '…'} fps, yüz %${stats ? Math.round(stats.faceRatio * 100) : '…'})`
              : status.state === 'error'
                ? status.message
                : 'yükleniyor…'}
          </p>
          <p>
            <label>
              Gözlük{' '}
              <select value={glasses} onChange={(e) => setGlasses(e.target.value as Glasses)}>
                <option value="gozluksuz">gözlüksüz</option>
                <option value="gozluklu">gözlüklü</option>
              </select>
            </label>{' '}
            <label>
              Çözünürlük{' '}
              <select
                value={resolution}
                onChange={(e) => setResolution(e.target.value as Resolution)}
              >
                <option value="640">640×480</option>
                <option value="1280">1280×720</option>
              </select>
            </label>
          </p>
          <button type="button" disabled={status.state !== 'running'} onClick={() => void start()}>
            Ölçümü başlat
          </button>
        </>
      )}

      {phase === 'done' && (
        <>
          <h1>Ölçüm bitti</h1>
          <p>{frameCount} kare kaydedildi. İnen dosyayı konuşmaya ekle.</p>
          <button type="button" onClick={() => setPhase('setup')}>
            Yeni ölçüm
          </button>
        </>
      )}

      {fullscreenStage && (
        <div style={{ position: 'fixed', inset: 0, background: 'var(--bg)' }}>
          {point && (
            <div
              style={{
                position: 'fixed',
                left: `${point[0] * 100}vw`,
                top: `${point[1] * 100}vh`,
                width: 28,
                height: 28,
                marginLeft: -14,
                marginTop: -14,
                borderRadius: '50%',
                background: collecting ? 'var(--ok)' : 'var(--accent)',
                border: '8px solid #fff',
                boxSizing: 'border-box',
              }}
            />
          )}
          {phase === 'head_pause' && (
            <div style={{ position: 'fixed', top: '35%', width: '100%', textAlign: 'center' }}>
              <h2>Başını birkaç santim yana kaydır ve hafifçe eğ, öyle kal.</h2>
              <p>Sonra yine yalnızca gözlerinle noktalara bak.</p>
              <button type="button" onClick={() => resumeRef.current()}>
                Devam
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
