/**
 * Canlı bakış denemesi (`?bakis`).
 *
 * Geliştirici aracıdır. 9 noktayla kalibre eder, sonra baktığın yeri tam
 * ekranda imleçle ve 4x3 ızgarada vurgulanan hücreyle gösterir. Sunucu
 * gerekmez; görüntü ve landmark hiçbir yere kaydedilmez.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  BlinkGate,
  Median5,
  OneEuro,
  PITCH,
  YAW,
  blinkThreshold,
  fitLinear,
  irisFeatures,
  openness,
  predictLinear,
  type GazeSample,
  type LinearGazeModel,
} from './gazeLinear';
import { useFaceTracking, type FaceFrame } from './useFaceTracking';

const PREP_MS = 600;
const DISCARD_MS = 300;
const HOLD_MS = 1200;
const MIN_CONFIDENCE = 0.3;
const MIN_SAMPLES = 12;
const COLUMNS = 4;
const ROWS = 3;

type Point = readonly [number, number];
type Phase = 'setup' | 'calibrating' | 'recenter' | 'live';

const GRID: readonly Point[] = [0.1, 0.5, 0.9].flatMap((y) =>
  [0.1, 0.5, 0.9].map((x): Point => [x, y]),
);
const CENTER: Point = [0.5, 0.5];

// Baş pozları: model başın nereye döndüğünü ancak bunları görürse öğrenir.
const HEAD_POINTS: readonly Point[] = [
  [0.1, 0.1],
  [0.9, 0.1],
  CENTER,
  [0.1, 0.9],
  [0.9, 0.9],
];
const HEAD_POSES = ['sağa', 'sola', 'yukarı', 'aşağı'] as const;
const POSE_PROMPT_MS = 3000;

// Kalibrasyonda görülen baş aralığının bu oranı kadar dışına tolerans.
const HEAD_RANGE_MARGIN = 0.3;
// Bu kadar kare üst üste göz kapalı görünürse uyarı çıkar (~0,5 sn).
const CLOSED_WARNING_FRAMES = 15;

interface HeadRange {
  yaw: [number, number];
  pitch: [number, number];
}

function rangeOf(values: number[]): [number, number] {
  const low = Math.min(...values);
  const high = Math.max(...values);
  const margin = (high - low) * HEAD_RANGE_MARGIN;
  return [low - margin, high + margin];
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function shuffled<T>(items: readonly T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j] as T, copy[i] as T];
  }
  return copy;
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function GazeLive() {
  const [phase, setPhase] = useState<Phase>('setup');
  const [point, setPoint] = useState<Point | null>(null);
  const [collecting, setCollecting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<string | null>(null);

  const collectRef = useRef<{ target: Point; samples: GazeSample[] } | null>(null);
  const modelRef = useRef<LinearGazeModel | null>(null);
  const shiftRef = useRef<[number, number]>([0, 0]);
  const liveRef = useRef(false);
  const busyRef = useRef(false);
  const filterRef = useRef({ x: new OneEuro(), y: new OneEuro() });
  const medianRef = useRef({ x: new Median5(), y: new Median5() });
  const gateRef = useRef<BlinkGate | null>(null);
  const headRangeRef = useRef<HeadRange | null>(null);
  const closedFramesRef = useRef(0);
  const bannerRef = useRef<HTMLParagraphElement>(null);
  const cursorRef = useRef<HTMLDivElement>(null);
  const tilesRef = useRef<(HTMLDivElement | null)[]>([]);
  const activeTileRef = useRef(-1);

  // Her karede React durumu değil, doğrudan DOM güncellenir: 30 Hz render
  // imleci gecikmeli gösterirdi.
  const onFrame = useCallback((frame: FaceFrame) => {
    // İmleç durduğunda nedeni ekranda yazar; sessizce donmak en kötüsü.
    const hold = (text: string) => {
      if (cursorRef.current) cursorRef.current.style.opacity = '0.25';
      if (bannerRef.current && bannerRef.current.textContent !== text) {
        bannerRef.current.textContent = text;
      }
    };

    if (!frame.landmarks) {
      hold('Yüzün bulunamıyor: kameranın görüş alanına ve yakınına gel.');
      return;
    }
    const features = irisFeatures(frame.landmarks);
    if (features.confidence < MIN_CONFIDENCE && !liveRef.current) return;

    const collect = collectRef.current;
    if (collect) {
      collect.samples.push({
        features: features.values,
        x: collect.target[0],
        y: collect.target[1],
      });
    }

    const model = modelRef.current;
    if (!model || !liveRef.current) return;

    // Kırpışta tahmin sıçrar: o kareler atlanır, imleç yerinde kalır.
    if (!gateRef.current?.accept(openness(features.values))) {
      closedFramesRef.current += 1;
      if (closedFramesRef.current >= CLOSED_WARNING_FRAMES) hold('Gözlerin kapalı görünüyor.');
      return;
    }
    closedFramesRef.current = 0;

    // Kalibrasyonda görülmemiş baş pozunda model yalnızca uydurur.
    const range = headRangeRef.current;
    const yaw = features.values[YAW] ?? 0;
    const pitch = features.values[PITCH] ?? 0;
    if (
      range &&
      (yaw < range.yaw[0] || yaw > range.yaw[1] || pitch < range.pitch[0] || pitch > range.pitch[1])
    ) {
      hold('Başın kalibrasyondaki konumdan çok uzaklaştı: biraz geri getir.');
      return;
    }
    if (bannerRef.current && bannerRef.current.textContent !== '') {
      bannerRef.current.textContent = '';
    }

    const [rawX, rawY] = predictLinear(model, features.values);
    const [shiftX, shiftY] = shiftRef.current;
    const x = filterRef.current.x.apply(
      medianRef.current.x.apply(clamp01(rawX + shiftX)),
      frame.t,
    );
    const y = filterRef.current.y.apply(
      medianRef.current.y.apply(clamp01(rawY + shiftY)),
      frame.t,
    );

    const cursor = cursorRef.current;
    if (cursor) {
      cursor.style.opacity = '1';
      cursor.style.transform = `translate(${x * window.innerWidth}px, ${y * window.innerHeight}px)`;
    }

    const column = Math.min(COLUMNS - 1, Math.floor(x * COLUMNS));
    const row = Math.min(ROWS - 1, Math.floor(y * ROWS));
    const tile = row * COLUMNS + column;
    if (tile !== activeTileRef.current) {
      const previous = tilesRef.current[activeTileRef.current];
      if (previous) previous.style.background = 'transparent';
      const next = tilesRef.current[tile];
      if (next) next.style.background = 'var(--accent-soft)';
      activeTileRef.current = tile;
    }
  }, []);

  const { videoRef, status, stats } = useFaceTracking({ enabled: true, onFrame });

  // 10 Kasım ölçümlerinde en düşük hata 1280x720'de çıktı (tek koşu).
  useEffect(() => {
    if (status.state !== 'running') return;
    const stream = videoRef.current?.srcObject as MediaStream | null;
    stream
      ?.getVideoTracks()[0]
      ?.applyConstraints({ width: { ideal: 1280 }, height: { ideal: 720 } })
      .catch((error: unknown) => console.warn('Çözünürlük değiştirilemedi', error));
  }, [status.state, videoRef]);

  const collectAt = async (target: Point): Promise<GazeSample[]> => {
    setPoint(target);
    setCollecting(false);
    await sleep(PREP_MS + DISCARD_MS);
    const collect = { target, samples: [] as GazeSample[] };
    collectRef.current = collect;
    setCollecting(true);
    await sleep(HOLD_MS);
    collectRef.current = null;
    return collect.samples;
  };

  const goLive = () => {
    filterRef.current.x.reset();
    filterRef.current.y.reset();
    medianRef.current.x.reset();
    medianRef.current.y.reset();
    closedFramesRef.current = 0;
    // Hücreler kalibrasyon sırasında DOM'dan kalkar; eski vurgu geçersizdir.
    activeTileRef.current = -1;
    liveRef.current = true;
    setPoint(null);
    setCollecting(false);
    setPhase('live');
  };

  const calibrate = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    liveRef.current = false;
    modelRef.current = null;
    shiftRef.current = [0, 0];
    setMessage(null);
    setPhase('calibrating');
    await document.documentElement.requestFullscreen().catch(() => undefined);
    await sleep(800);

    const collected: GazeSample[] = [];
    for (const target of shuffled(GRID)) collected.push(...(await collectAt(target)));

    for (const pose of HEAD_POSES) {
      setPoint(null);
      setPrompt(`Başını hafifçe ${pose} çevir, öyle kal. Gözlerinle noktalara bakmaya devam et.`);
      await sleep(POSE_PROMPT_MS);
      setPrompt(null);
      for (const target of shuffled(HEAD_POINTS)) collected.push(...(await collectAt(target)));
    }
    busyRef.current = false;

    // Kalibrasyon sırasındaki kırpışlar modele girmesin.
    const threshold = blinkThreshold(collected);
    const samples = collected.filter((sample) => openness(sample.features) >= threshold);

    if (samples.length < MIN_SAMPLES) {
      setPoint(null);
      setMessage('Yeterli örnek toplanamadı. Yüzün kamerada görünüyor mu?');
      setPhase('setup');
      return;
    }
    modelRef.current = fitLinear(samples);
    gateRef.current = new BlinkGate(threshold);
    headRangeRef.current = {
      yaw: rangeOf(samples.map((sample) => sample.features[YAW] ?? 0)),
      pitch: rangeOf(samples.map((sample) => sample.features[PITCH] ?? 0)),
    };
    goLive();
  };

  /** Baş oynadıysa: tek noktaya bakılır, tahmin o noktaya kaydırılır. */
  const recenter = async () => {
    const model = modelRef.current;
    if (!model || busyRef.current) return;
    busyRef.current = true;
    liveRef.current = false;
    setPhase('recenter');
    const samples = await collectAt(CENTER);
    busyRef.current = false;

    if (samples.length > 0) {
      let sumX = 0;
      let sumY = 0;
      for (const sample of samples) {
        const [x, y] = predictLinear(model, sample.features);
        sumX += x;
        sumY += y;
      }
      shiftRef.current = [CENTER[0] - sumX / samples.length, CENTER[1] - sumY / samples.length];
    }
    goLive();
  };

  const recenterRef = useRef(recenter);
  recenterRef.current = recenter;
  const calibrateRef = useRef(calibrate);
  calibrateRef.current = calibrate;

  useEffect(() => {
    if (phase !== 'live') return;
    const onKey = (event: KeyboardEvent) => {
      if (event.code === 'Space') {
        event.preventDefault();
        void recenterRef.current();
      } else if (event.key.toLowerCase() === 'k') {
        void calibrateRef.current();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase]);

  const fullscreenStage = phase !== 'setup';

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
          <h1>Nereye bakıyorum?</h1>
          <p>
            Yaklaşık 75 saniye sürer. Önce başın sabitken dokuz noktaya, sonra ekrandaki yazının
            istediği gibi başını hafifçe çevirip beşer noktaya bakacaksın. Sonra imleç baktığın
            yeri gösterecek.
          </p>
          <p>
            Durum:{' '}
            {status.state === 'running'
              ? `hazır (${status.delegate}, ${stats ? stats.fps.toFixed(0) : '…'} fps, yüz %${stats ? Math.round(stats.faceRatio * 100) : '…'})`
              : status.state === 'error'
                ? status.message
                : 'yükleniyor…'}
          </p>
          {message && <p style={{ color: 'var(--warn)' }}>{message}</p>}
          <button
            type="button"
            disabled={status.state !== 'running'}
            onClick={() => void calibrate()}
          >
            Kalibrasyonu başlat
          </button>
        </>
      )}

      {fullscreenStage && (
        <div style={{ position: 'fixed', inset: 0, background: 'var(--bg)', overflow: 'hidden' }}>
          {phase === 'live' && (
            <>
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'grid',
                  gridTemplateColumns: `repeat(${COLUMNS}, 1fr)`,
                  gridTemplateRows: `repeat(${ROWS}, 1fr)`,
                }}
              >
                {Array.from({ length: COLUMNS * ROWS }, (_, index) => (
                  <div
                    key={index}
                    ref={(element) => {
                      tilesRef.current[index] = element;
                    }}
                    style={{
                      border: '1px solid var(--surface-hover)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 40,
                      color: 'var(--text-dim)',
                    }}
                  >
                    {index + 1}
                  </div>
                ))}
              </div>
              <div
                ref={cursorRef}
                style={{
                  position: 'absolute',
                  left: -16,
                  top: -16,
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  background: 'var(--warn)',
                  border: '3px solid #fff',
                  boxSizing: 'border-box',
                  pointerEvents: 'none',
                }}
              />
              <p
                ref={bannerRef}
                style={{
                  position: 'absolute',
                  top: 16,
                  width: '100%',
                  textAlign: 'center',
                  color: 'var(--warn)',
                  fontSize: 24,
                  margin: 0,
                }}
              />
              <p
                style={{
                  position: 'absolute',
                  bottom: 8,
                  width: '100%',
                  textAlign: 'center',
                  color: 'var(--text-dim)',
                  margin: 0,
                }}
              >
                Boşluk: başın oynadıysa düzelt (ortadaki noktaya bak) · K: yeniden kalibre et · Esc:
                tam ekrandan çık
              </p>
            </>
          )}

          {prompt && (
            <h2 style={{ position: 'absolute', top: '40%', width: '100%', textAlign: 'center' }}>
              {prompt}
            </h2>
          )}

          {point && (
            <div
              style={{
                position: 'absolute',
                left: `${point[0] * 100}%`,
                top: `${point[1] * 100}%`,
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
        </div>
      )}
    </div>
  );
}
