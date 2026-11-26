/**
 * Canlı bakış denemesi (`?bakis`).
 *
 * Geliştirici aracıdır. 9 noktayla kalibre eder, sonra baş pozu değişimini
 * kameradan okuyup (yeterince dönünce otomatik ilerleyen bir çubukla) dört
 * yönde ek örnek toplar, sonra baktığın yeri tam ekranda imleçle ve ızgarada
 * (varsayılan 4x3, `&izgara=3x2` gibi) vurgulanan hücreyle gösterir. Sunucu
 * gerekmez; görüntü ve landmark hiçbir yere kaydedilmez.
 *
 * D tuşu 10 denemelik dwell oturumu başlatır (dwellTrial.ts): işaretli hücreye
 * 700 ms bakılınca seçim olur, sonunda doğru sayısı gösterilir ve indirilebilir.
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
import {
  DWELL_S,
  DwellTrial,
  TRIAL_COUNT,
  parseGrid,
  pickTargets,
  type TrialResult,
} from './dwellTrial';
import { useFaceTracking, type FaceFrame } from './useFaceTracking';

const PREP_MS = 600;
const DISCARD_MS = 300;
const HOLD_MS = 1200;
const MIN_CONFIDENCE = 0.3;
const MIN_SAMPLES = 12;
// `?bakis&izgara=3x2` gibi; tuş boyutu kararı için (docs/oneri-canli-bakis-mesaji.md).
const [COLUMNS, ROWS] = parseGrid(window.location.search);

type Point = readonly [number, number];
type Phase = 'setup' | 'calibrating' | 'recenter' | 'live';

const GRID: readonly Point[] = [0.1, 0.5, 0.9].flatMap((y) =>
  [0.1, 0.5, 0.9].map((x): Point => [x, y]),
);
const CENTER: Point = [0.5, 0.5];

// Boşluk (recenter) bu iki köşegen noktaya bakılarak eksen başına
// kazanç+offset çözer. Tek nokta (eski hal) yalnızca düz kaymayı
// düzeltiyordu; model canlıda kazanç kayması yaşadığında (baş kameraya
// uzaklığı/açısı değiştiğinde) düz kayma kenarları düzeltemiyordu.
const RECENTER_POINTS: readonly [Point, Point] = [
  [0.15, 0.15],
  [0.85, 0.85],
];

interface AxisCorrection {
  gainX: number;
  offsetX: number;
  gainY: number;
  offsetY: number;
}

/** İki (ham, gerçek) çiftinden doğrusal kazanç+offset; noktalar çakışırsa kazanç 1 sayılır. */
function fitAxis(rawA: number, trueA: number, rawB: number, trueB: number): { gain: number; offset: number } {
  const span = rawB - rawA;
  if (Math.abs(span) < 1e-6) return { gain: 1, offset: trueA - rawA };
  const gain = (trueB - trueA) / span;
  return { gain, offset: trueA - gain * rawA };
}

// Baş pozları: model başın nereye döndüğünü ancak bunları görürse öğrenir.
const HEAD_POINTS: readonly Point[] = [
  [0.1, 0.1],
  [0.9, 0.1],
  CENTER,
  [0.1, 0.9],
  [0.9, 0.9],
];
const HEAD_POSES = ['sağa', 'sola', 'yukarı', 'aşağı'] as const;
// Eşikler ilk tahmin; kamerada test edilip ayarlanmalı.
const YAW_TURN_THRESHOLD = 0.04;
const PITCH_TURN_THRESHOLD = 0.035;
// ~0,6 sn üst üste eşiği geçmesi istenir; kısa tutulursa küçük bir
// kıpırdanma bile anında onaylanıp "tak diye" geçmiş gibi hissettiriyordu.
const POSE_STABLE_FRAMES = 18;
const POSE_CONFIRM_TIMEOUT_MS = 8000;
const POSE_READ_DELAY_MS = 600;
// Onaylandıktan sonra ekranda kısa bir süre "Tamam" yazısı kalsın; hemen
// sıradaki adıma atlamak geçişi ani/sarsıcı gösteriyordu.
const POSE_SETTLE_MS = 500;
const POSE_AXIS: Record<(typeof HEAD_POSES)[number], 'yaw' | 'pitch'> = {
  sağa: 'yaw',
  sola: 'yaw',
  yukarı: 'pitch',
  aşağı: 'pitch',
};

// Kalibrasyonda görülen baş aralığının bu oranı kadar dışına tolerans.
const HEAD_RANGE_MARGIN = 0.3;
// Bu kadar kare üst üste göz kapalı görünürse uyarı çıkar (~0,5 sn).
const CLOSED_WARNING_FRAMES = 15;

interface HeadRange {
  yaw: [number, number];
  pitch: [number, number];
}

interface PoseTarget {
  axis: 'yaw' | 'pitch';
  baseline: number;
  threshold: number;
  /** null: ilk yön, hangisi gelirse kabul edilir. Belirliyse yalnız o yön sayılır. */
  requireSign: number | null;
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

interface TrialSummary {
  results: TrialResult[];
  correct: number;
  medianMs: number;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? (sorted[mid] ?? 0) : ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2;
}

interface TileStat {
  tile: number;
  attempts: number;
  correct: number;
}

/** Hangi hücre kaç kez hedef oldu, kaçında doğru seçildi — tek tek rapor etmek yerine. */
function tileBreakdown(results: readonly TrialResult[]): TileStat[] {
  const byTile = new Map<number, { attempts: number; correct: number }>();
  for (const result of results) {
    const entry = byTile.get(result.target) ?? { attempts: 0, correct: 0 };
    entry.attempts += 1;
    if (result.correct) entry.correct += 1;
    byTile.set(result.target, entry);
  }
  return [...byTile.entries()]
    .sort(([a], [b]) => a - b)
    .map(([tile, stats]) => ({ tile, ...stats }));
}

function download(name: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 1)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
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
  const [trialSummary, setTrialSummary] = useState<TrialSummary | null>(null);
  const [posing, setPosing] = useState(false);

  const collectRef = useRef<{ target: Point; samples: GazeSample[] } | null>(null);
  const poseTargetRef = useRef<PoseTarget | null>(null);
  const poseStableRef = useRef(0);
  const poseReadyRef = useRef(false);
  const poseLastSignRef = useRef(0);
  const axisSignRef = useRef<{ yaw: number | null; pitch: number | null }>({ yaw: null, pitch: null });
  const poseMeterRef = useRef<HTMLDivElement>(null);
  const poseInfoRef = useRef<HTMLParagraphElement>(null);
  // TEŞHİS AMAÇLI: dikey tahminin gerçekte ne kadar genişlediğini görmek için.
  // Teşhis bitince kaldırılacak.
  const debugRef = useRef<HTMLParagraphElement>(null);
  const rawRangeRef = useRef({ minY: Infinity, maxY: -Infinity });
  const modelRef = useRef<LinearGazeModel | null>(null);
  const correctionRef = useRef<AxisCorrection>({ gainX: 1, offsetX: 0, gainY: 1, offsetY: 0 });
  const liveRef = useRef(false);
  const busyRef = useRef(false);
  const filterRef = useRef({ x: new OneEuro(), y: new OneEuro() });
  const medianRef = useRef({ x: new Median5(), y: new Median5() });
  const gateRef = useRef<BlinkGate | null>(null);
  const headRangeRef = useRef<HeadRange | null>(null);
  // recenter() baş pozu kaymasını da takip edebilsin diye son bilinen taban.
  const headBaselineRef = useRef<{ yaw: number; pitch: number } | null>(null);
  const closedFramesRef = useRef(0);
  const bannerRef = useRef<HTMLParagraphElement>(null);
  const cursorRef = useRef<HTMLDivElement>(null);
  const tilesRef = useRef<(HTMLDivElement | null)[]>([]);
  const activeTileRef = useRef(-1);
  const trialRef = useRef<DwellTrial | null>(null);
  const trialInfoRef = useRef<HTMLParagraphElement>(null);
  const dwellBarRef = useRef<HTMLDivElement>(null);

  // Dwell denemesi de DOM'a doğrudan yazar (her karede render olmasın).
  const markTarget = (target: number | null) => {
    tilesRef.current.forEach((element, index) => {
      if (!element) return;
      element.style.outline = index === target ? '8px solid var(--ok)' : 'none';
      element.style.outlineOffset = '-8px';
    });
  };
  const setTrialInfo = (text: string) => {
    if (trialInfoRef.current) trialInfoRef.current.textContent = text;
  };
  const showDwell = (tile: number, progress: number) => {
    const bar = dwellBarRef.current;
    if (!bar) return;
    const column = tile % COLUMNS;
    const row = Math.floor(tile / COLUMNS);
    bar.style.left = `${(column / COLUMNS) * 100}%`;
    bar.style.top = `${((row + 1) / ROWS) * 100}%`;
    bar.style.width = `${(progress / COLUMNS) * 100}%`;
  };

  const startTrial = () => {
    const trial = new DwellTrial(pickTargets(TRIAL_COUNT, COLUMNS * ROWS));
    trialRef.current = trial;
    setTrialSummary(null);
    markTarget(trial.target);
    setTrialInfo(`Deneme 1/${trial.targets.length} · yeşil çerçeveli hücreye bak`);
  };

  const cancelTrial = () => {
    trialRef.current = null;
    markTarget(null);
    setTrialInfo('');
  };

  const downloadTrial = (summary: TrialSummary) => {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    download(`bakis-deneme-${stamp}.json`, {
      format: 'gaze-aac/dwell-trial@1',
      created: new Date().toISOString(),
      user_agent: navigator.userAgent,
      screen: { width: window.innerWidth, height: window.innerHeight },
      grid: { columns: COLUMNS, rows: ROWS },
      dwell_ms: DWELL_S * 1000,
      correct: summary.correct,
      trials: summary.results,
    });
  };

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

    // Baş pozu onayı: kör süre yerine gerçek dönüş miktarı ve yönü kameradan okunur.
    const poseTarget = poseTargetRef.current;
    if (poseTarget) {
      const value =
        poseTarget.axis === 'yaw' ? (features.values[YAW] ?? 0) : (features.values[PITCH] ?? 0);
      const delta = value - poseTarget.baseline;
      const sign = Math.sign(delta);
      const matchesSign = poseTarget.requireSign === null || sign === poseTarget.requireSign;
      const magnitude = clamp01(Math.abs(delta) / poseTarget.threshold);
      const progress = matchesSign ? magnitude : 0;
      if (poseMeterRef.current) poseMeterRef.current.style.width = `${progress * 100}%`;
      if (progress >= 1) {
        poseStableRef.current += 1;
        poseLastSignRef.current = sign;
      } else {
        poseStableRef.current = 0;
      }
      if (poseStableRef.current >= POSE_STABLE_FRAMES) {
        poseReadyRef.current = true;
        if (poseInfoRef.current) poseInfoRef.current.textContent = 'Tamam, böyle kal…';
      } else if (poseInfoRef.current) {
        poseInfoRef.current.textContent = matchesSign
          ? `Dönüş: %${Math.round(magnitude * 100)}`
          : 'Ters yöne döndün, diğer tarafa çevir.';
      }
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
    const rawRange = rawRangeRef.current;
    if (rawY < rawRange.minY) rawRange.minY = rawY;
    if (rawY > rawRange.maxY) rawRange.maxY = rawY;
    if (debugRef.current) {
      debugRef.current.textContent =
        `ham y: ${rawY.toFixed(2)} (görülen aralık ${rawRange.minY.toFixed(2)}–${rawRange.maxY.toFixed(2)}) · ` +
        `ham x: ${rawX.toFixed(2)}`;
    }
    const { gainX, offsetX, gainY, offsetY } = correctionRef.current;
    const x = filterRef.current.x.apply(
      medianRef.current.x.apply(clamp01(rawX * gainX + offsetX)),
      frame.t,
    );
    const y = filterRef.current.y.apply(
      medianRef.current.y.apply(clamp01(rawY * gainY + offsetY)),
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

    const trial = trialRef.current;
    if (trial) {
      const update = trial.update(tile, frame.t);
      showDwell(tile, update.progress);
      if (update.selected) {
        markTarget(null);
        setTrialInfo(
          `${update.selected.correct ? '✓ doğru' : `✗ yanlış (${update.selected.selected + 1})`} · ` +
            `${trial.correctCount}/${trial.results.length}`,
        );
      }
      if (update.newTarget) {
        markTarget(trial.target);
        setTrialInfo(`Deneme ${trial.trialNumber}/${trial.targets.length} · ${trial.correctCount} doğru`);
      }
      if (update.done) {
        trialRef.current = null;
        showDwell(tile, 0);
        setTrialSummary({
          results: [...trial.results],
          correct: trial.correctCount,
          medianMs: median(trial.results.map((r) => r.timeMs)),
        });
      }
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

  const waitForPoseReady = (timeoutMs: number): Promise<void> =>
    new Promise((resolve) => {
      const start = performance.now();
      const check = () => {
        if (poseReadyRef.current || performance.now() - start > timeoutMs) {
          resolve();
          return;
        }
        window.requestAnimationFrame(check);
      };
      check();
    });

  const goLive = () => {
    filterRef.current.x.reset();
    filterRef.current.y.reset();
    medianRef.current.x.reset();
    medianRef.current.y.reset();
    closedFramesRef.current = 0;
    rawRangeRef.current = { minY: Infinity, maxY: -Infinity };
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
    trialRef.current = null;
    setTrialSummary(null);
    correctionRef.current = { gainX: 1, offsetX: 0, gainY: 1, offsetY: 0 };
    axisSignRef.current = { yaw: null, pitch: null };
    setMessage(null);
    setPhase('calibrating');
    await document.documentElement.requestFullscreen().catch(() => undefined);
    await sleep(800);

    const collected: GazeSample[] = [];
    for (const target of shuffled(GRID)) collected.push(...(await collectAt(target)));

    // Baş düz tutulduğunda ölçülen yaw/pitch, pozların kıyaslanacağı taban.
    const baselineYaw = median(collected.map((sample) => sample.features[YAW] ?? 0));
    const basePitch = median(collected.map((sample) => sample.features[PITCH] ?? 0));

    for (const pose of HEAD_POSES) {
      setPoint(null);
      setPosing(true);
      setPrompt(
        `Başını hafifçe ${pose} çevir. Yeterince dönünce çubuk dolar ve otomatik devam eder; ` +
          'gözlerinle noktalara bakmaya devam et.',
      );
      poseStableRef.current = 0;
      poseReadyRef.current = false;
      const axis = POSE_AXIS[pose];
      // Çiftin ilk pozu (sağa/yukarı) hangi yönden gelirse kabul eder ve o yönü
      // kaydeder; ikincisi (sola/aşağı) tam tersini ister. Yoksa baş geri
      // getirilmeden bile ikincisi anında "onaylanmış" görünüyordu.
      const isPairLeader = pose === 'sağa' || pose === 'yukarı';
      const recordedSign = axisSignRef.current[axis];
      const requireSign = isPairLeader ? null : recordedSign !== null ? -recordedSign : null;
      poseTargetRef.current = {
        axis,
        baseline: axis === 'yaw' ? baselineYaw : basePitch,
        threshold: axis === 'yaw' ? YAW_TURN_THRESHOLD : PITCH_TURN_THRESHOLD,
        requireSign,
      };
      await sleep(POSE_READ_DELAY_MS);
      await waitForPoseReady(POSE_CONFIRM_TIMEOUT_MS);
      if (isPairLeader) axisSignRef.current[axis] = poseLastSignRef.current || null;
      await sleep(POSE_SETTLE_MS);
      poseTargetRef.current = null;
      setPosing(false);
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
    const model = fitLinear(samples);
    modelRef.current = model;
    gateRef.current = new BlinkGate(threshold);
    headRangeRef.current = {
      yaw: rangeOf(samples.map((sample) => sample.features[YAW] ?? 0)),
      pitch: rangeOf(samples.map((sample) => sample.features[PITCH] ?? 0)),
    };
    headBaselineRef.current = { yaw: baselineYaw, pitch: basePitch };

    // GRID/HEAD_POINTS'in uç değerleri (0.1/0.9) hep aynı; model bu
    // noktalarda tam orada çıkmayabiliyor (köşelerde en gürültülü bölge).
    // Kendi kalibrasyon verisiyle "orada ne tahmin etti" ölçülüp eksen
    // başına kazanç+offset ile tam 0.1/0.9'a çekiliyor — recenter()'ın el
    // ile yaptığını kalibrasyon bitince otomatik yapmış oluyoruz.
    const groupMedian = (target: number, axis: 0 | 1) =>
      median(
        samples
          .filter((sample) => (axis === 0 ? sample.x : sample.y) === target)
          .map((sample) => predictLinear(model, sample.features)[axis]),
      );
    const fx = fitAxis(groupMedian(0.1, 0), 0.1, groupMedian(0.9, 0), 0.9);
    const fy = fitAxis(groupMedian(0.1, 1), 0.1, groupMedian(0.9, 1), 0.9);
    correctionRef.current = { gainX: fx.gain, offsetX: fx.offset, gainY: fy.gain, offsetY: fy.offset };

    goLive();
  };

  /**
   * Baş oynadıysa veya model kazanç kaymışsa: iki köşegen noktaya bakılır,
   * her eksen için ayrı kazanç+offset çözülür (yalnızca düz kaymak yerine).
   *
   * Baş, kalibrasyondaki aralığın dışına çıktıysa canlı moddaki kontrol
   * (headRangeRef) imleci zaten dondurur ve o uyarı correctionRef'ten önce
   * devreye girer — yani kazanç/offset ne olursa olsun imleç donuk kalır.
   * Bu yüzden recenter sırasında ölçülen yaw/pitch de okunup izin verilen
   * aralık aynı miktarda kaydırılıyor; yoksa baş kalıcı olarak "çok uzakta"
   * sayılır ve Boşluk hiçbir şeyi düzeltmiyormuş gibi görünür.
   */
  const recenter = async () => {
    const model = modelRef.current;
    if (!model || busyRef.current) return;
    busyRef.current = true;
    liveRef.current = false;
    setPhase('recenter');

    const means: Array<[number, number] | null> = [];
    let yawSum = 0;
    let pitchSum = 0;
    let poseCount = 0;
    for (const target of RECENTER_POINTS) {
      const samples = await collectAt(target);
      if (samples.length === 0) {
        means.push(null);
        continue;
      }
      let sumX = 0;
      let sumY = 0;
      for (const sample of samples) {
        const [x, y] = predictLinear(model, sample.features);
        sumX += x;
        sumY += y;
        yawSum += sample.features[YAW] ?? 0;
        pitchSum += sample.features[PITCH] ?? 0;
        poseCount += 1;
      }
      means.push([sumX / samples.length, sumY / samples.length]);
    }
    busyRef.current = false;

    const [a, b] = means;
    if (a && b) {
      const [rawXa, rawYa] = a;
      const [rawXb, rawYb] = b;
      const [trueXa, trueYa] = RECENTER_POINTS[0];
      const [trueXb, trueYb] = RECENTER_POINTS[1];
      const fx = fitAxis(rawXa, trueXa, rawXb, trueXb);
      const fy = fitAxis(rawYa, trueYa, rawYb, trueYb);
      correctionRef.current = { gainX: fx.gain, offsetX: fx.offset, gainY: fy.gain, offsetY: fy.offset };
    }

    const baseline = headBaselineRef.current;
    const range = headRangeRef.current;
    if (poseCount > 0 && baseline && range) {
      const yaw = yawSum / poseCount;
      const pitch = pitchSum / poseCount;
      const deltaYaw = yaw - baseline.yaw;
      const deltaPitch = pitch - baseline.pitch;
      headRangeRef.current = {
        yaw: [range.yaw[0] + deltaYaw, range.yaw[1] + deltaYaw],
        pitch: [range.pitch[0] + deltaPitch, range.pitch[1] + deltaPitch],
      };
      headBaselineRef.current = { yaw, pitch };
    }
    goLive();
  };

  const recenterRef = useRef(recenter);
  recenterRef.current = recenter;
  const calibrateRef = useRef(calibrate);
  calibrateRef.current = calibrate;
  const startTrialRef = useRef(startTrial);
  startTrialRef.current = startTrial;

  // Yeniden ortalama (Boşluk) sırasında ızgara DOM'dan kalkar; canlıya
  // dönünce süren denemenin hedefi ve yazısı yeniden çizilir.
  useEffect(() => {
    const trial = trialRef.current;
    if (phase !== 'live' || !trial || trial.done) return;
    markTarget(trial.target);
    setTrialInfo(`Deneme ${trial.trialNumber}/${trial.targets.length} · ${trial.correctCount} doğru`);
    // markTarget ve setTrialInfo yalnızca ref'lere yazıyor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  useEffect(() => {
    if (phase !== 'live') return;
    const onKey = (event: KeyboardEvent) => {
      if (event.code === 'Space') {
        event.preventDefault();
        void recenterRef.current();
      } else if (event.key.toLowerCase() === 'k') {
        void calibrateRef.current();
      } else if (event.key.toLowerCase() === 'd') {
        startTrialRef.current();
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
          posing
            ? {
                position: 'fixed',
                top: 140,
                left: '50%',
                width: 360,
                height: 202,
                transform: 'translateX(-50%) scaleX(-1)',
                borderRadius: 12,
                background: '#000',
                objectFit: 'cover',
                zIndex: 2,
              }
            : fullscreenStage
              ? { position: 'fixed', width: 1, height: 1, opacity: 0 }
              : { width: 320, borderRadius: 10, transform: 'scaleX(-1)', background: '#000' }
        }
      />

      {posing && (
        <div
          style={{
            position: 'fixed',
            top: 140 + 202 + 16,
            left: '50%',
            transform: 'translateX(-50%)',
            width: 360,
            textAlign: 'center',
            zIndex: 2,
          }}
        >
          <div
            style={{ height: 10, borderRadius: 6, background: 'var(--surface-hover)', overflow: 'hidden' }}
          >
            <div ref={poseMeterRef} style={{ height: '100%', width: 0, background: 'var(--accent)' }} />
          </div>
          <p ref={poseInfoRef} style={{ margin: '8px 0 0', fontSize: 20, color: 'var(--text)' }} />
        </div>
      )}

      {phase === 'setup' && (
        <>
          <h1>Nereye bakıyorum?</h1>
          <p>
            Yaklaşık 75 saniye sürer. Önce başın sabitken dokuz noktaya, sonra ekrandaki yazının
            istediği gibi başını hafifçe çevirip beşer noktaya bakacaksın. Sonra imleç baktığın
            yeri gösterecek. Izgara: {COLUMNS}×{ROWS} (değiştirmek için adrese{' '}
            <code>&amp;izgara=3x2</code> ekle).
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
              <div
                ref={dwellBarRef}
                style={{
                  position: 'absolute',
                  height: 10,
                  marginTop: -10,
                  width: 0,
                  background: 'var(--accent)',
                  pointerEvents: 'none',
                }}
              />
              <p
                ref={trialInfoRef}
                style={{
                  position: 'absolute',
                  top: 16,
                  left: 16,
                  margin: 0,
                  fontSize: 24,
                  color: 'var(--text)',
                }}
              />
              {trialSummary && (
                <div
                  style={{
                    position: 'absolute',
                    top: '30%',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    background: 'var(--surface)',
                    borderRadius: 16,
                    padding: 24,
                    textAlign: 'center',
                    fontSize: 24,
                  }}
                >
                  <p style={{ fontSize: 40, margin: '0 0 8px' }}>
                    {trialSummary.correct}/{trialSummary.results.length} doğru
                  </p>
                  <p style={{ margin: '0 0 16px', color: 'var(--text-dim)' }}>
                    Ölçüt: en az 8 · medyan seçim süresi{' '}
                    {(trialSummary.medianMs / 1000).toFixed(1).replace('.', ',')} sn
                  </p>
                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: 6,
                      justifyContent: 'center',
                      margin: '0 0 16px',
                      fontSize: 16,
                    }}
                  >
                    {tileBreakdown(trialSummary.results).map(({ tile, attempts, correct }) => (
                      <span
                        key={tile}
                        style={{
                          padding: '2px 10px',
                          borderRadius: 8,
                          background: 'var(--surface-hover)',
                          color: correct === attempts ? 'var(--text-dim)' : 'var(--warn)',
                        }}
                      >
                        {tile + 1}: {correct}/{attempts}
                      </span>
                    ))}
                  </div>
                  <button type="button" onClick={() => downloadTrial(trialSummary)}>
                    Sonucu indir
                  </button>{' '}
                  <button
                    type="button"
                    onClick={() => {
                      setTrialSummary(null);
                      cancelTrial();
                    }}
                  >
                    Kapat
                  </button>
                </div>
              )}
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
              {/* TEŞHİS AMAÇLI: dikey tahmin sorununu incelemek için eklendi, sonra kaldırılacak. */}
              <p
                ref={debugRef}
                style={{
                  position: 'absolute',
                  bottom: 40,
                  right: 16,
                  margin: 0,
                  fontSize: 14,
                  fontFamily: 'monospace',
                  color: 'var(--text-dim)',
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
                D: 10 dwell denemesi · Boşluk: başın oynadıysa düzelt (ortadaki noktaya bak) · K:
                yeniden kalibre et · Esc: tam ekrandan çık
              </p>
            </>
          )}

          {prompt && (
            <h2 style={{ position: 'absolute', top: 40, width: '100%', textAlign: 'center' }}>{prompt}</h2>
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
