/**
 * Ana uygulamanın tarayıcı içi bakış modeli (K1-a, kestirme yol).
 *
 * ?bakis sayfasındaki (GazeLive.tsx) hattın React'ten bağımsız hali:
 * irisFeatures → fitLinear/predictLinear, kırpış kapısı, baş aralığı denetimi,
 * kalibrasyon sonrası köşe düzeltmesi ve iki noktalı yeniden ortalama.
 * Sayılar ve kurallar GazeLive.tsx ile aynı tutuldu; biri değişirse diğeri de
 * gözden geçirilmeli.
 *
 * Yumuşatma burada YAPILMAZ: sunucudaki GazeSmoother (Median5 + One Euro) aynı
 * işi yapıyor; iki kez yumuşatmak imleci gereksiz geciktirir. Çıktı, ekranın
 * 0–1 aralığına kırpılmış ham tahmindir ve mevcut `gaze` mesajıyla gider.
 *
 * Kalıcı yol (K1-b) gelince model sunucudaki GazeMapper'a taşınır ve bu dosya
 * yalnızca öznitelik gönderen ince bir katmana iner.
 */

import {
  BlinkGate,
  PITCH,
  YAW,
  blinkThreshold,
  fitLinear,
  openness,
  predictLinear,
  type GazeSample,
  type LinearGazeModel,
} from './gazeLinear';

export type Point = readonly [number, number];

/** Kalibrasyonda baş sabitken bakılan 9 nokta. */
export const CALIBRATION_GRID: readonly Point[] = [0.1, 0.5, 0.9].flatMap((y) =>
  [0.1, 0.5, 0.9].map((x): Point => [x, y]),
);

/** Her baş pozunda bakılan 5 nokta. */
export const HEAD_POSE_POINTS: readonly Point[] = [
  [0.1, 0.1],
  [0.9, 0.1],
  [0.5, 0.5],
  [0.1, 0.9],
  [0.9, 0.9],
];

export const HEAD_POSES = ['sağa', 'sola', 'yukarı', 'aşağı'] as const;
export type HeadPose = (typeof HEAD_POSES)[number];

/** Yeniden ortalamada bakılan iki köşegen nokta (eksen başına kazanç + kayma). */
export const RECENTER_POINTS: readonly [Point, Point] = [
  [0.15, 0.15],
  [0.85, 0.85],
];

/** Kalibrasyonda bu kadar az örnek kalırsa model kurulmaz. */
export const MIN_SAMPLES = 12;
/** Kalibrasyonda bu güvenin altındaki kareler örneğe girmez. */
export const MIN_CONFIDENCE = 0.3;
/** Kalibrasyonda görülen baş aralığının bu oranı kadar dışına tolerans. */
const HEAD_RANGE_MARGIN = 0.3;

export type HoldReason = 'no_face' | 'blink' | 'head' | 'window';

export type GazeEstimate =
  | { kind: 'point'; x: number; y: number }
  | { kind: 'hold'; reason: HoldReason };

interface AxisCorrection {
  gainX: number;
  offsetX: number;
  gainY: number;
  offsetY: number;
}

interface Range {
  yaw: [number, number];
  pitch: [number, number];
}

export function median(values: readonly number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? (sorted[mid] ?? 0)
    : ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2;
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function rangeOf(values: readonly number[]): [number, number] {
  const low = Math.min(...values);
  const high = Math.max(...values);
  const margin = (high - low) * HEAD_RANGE_MARGIN;
  return [low - margin, high + margin];
}

/** İki (ham, gerçek) çiftinden kazanç + kayma; noktalar çakışırsa kazanç 1 sayılır. */
export function fitAxis(
  rawA: number,
  trueA: number,
  rawB: number,
  trueB: number,
): { gain: number; offset: number } {
  const span = rawB - rawA;
  if (Math.abs(span) < 1e-6) return { gain: 1, offset: trueA - rawA };
  const gain = (trueB - trueA) / span;
  return { gain, offset: trueA - gain * rawA };
}

/** Pencere boyutu kalibrasyondakinden bu oranda farklıysa tahmin durur (K4d). */
const WINDOW_TOLERANCE = 0.02;

export interface WindowSize {
  width: number;
  height: number;
}

export class BrowserGazeModel {
  private readonly model: LinearGazeModel;
  private readonly gate: BlinkGate;
  private correction: AxisCorrection;
  private headRange: Range;
  private headBaseline: { yaw: number; pitch: number };
  /** Kalibrasyonun yapıldığı pencere; klavye de aynı boyutta olmalı. */
  readonly window: WindowSize;
  readonly sampleCount: number;

  private constructor(
    model: LinearGazeModel,
    gate: BlinkGate,
    correction: AxisCorrection,
    headRange: Range,
    headBaseline: { yaw: number; pitch: number },
    window: WindowSize,
    sampleCount: number,
  ) {
    this.model = model;
    this.gate = gate;
    this.correction = correction;
    this.headRange = headRange;
    this.headBaseline = headBaseline;
    this.window = window;
    this.sampleCount = sampleCount;
  }

  /**
   * Kalibrasyon örneklerinden model kurar; yeterli örnek yoksa `null`.
   *
   * `baseline`: baş düzken (ilk 9 nokta) ölçülen yaw/pitch medyanı.
   */
  static fit(
    collected: readonly GazeSample[],
    baseline: { yaw: number; pitch: number },
    window: WindowSize,
  ): BrowserGazeModel | null {
    // Kalibrasyon sırasındaki kırpışlar modele girmesin.
    const threshold = blinkThreshold(collected);
    const samples = collected.filter((sample) => openness(sample.features) >= threshold);
    if (samples.length < MIN_SAMPLES) return null;

    const model = fitLinear(samples);
    const headRange: Range = {
      yaw: rangeOf(samples.map((sample) => sample.features[YAW] ?? 0)),
      pitch: rangeOf(samples.map((sample) => sample.features[PITCH] ?? 0)),
    };

    // Model uç noktalarda (0,1 / 0,9) tam orada çıkmayabiliyor; kendi
    // kalibrasyon verisiyle eksen başına kazanç + kayma ile oraya çekilir.
    const groupMedian = (target: number, axis: 0 | 1) =>
      median(
        samples
          .filter((sample) => (axis === 0 ? sample.x : sample.y) === target)
          .map((sample) => predictLinear(model, sample.features)[axis]),
      );
    const fx = fitAxis(groupMedian(0.1, 0), 0.1, groupMedian(0.9, 0), 0.9);
    const fy = fitAxis(groupMedian(0.1, 1), 0.1, groupMedian(0.9, 1), 0.9);

    return new BrowserGazeModel(
      model,
      new BlinkGate(threshold),
      { gainX: fx.gain, offsetX: fx.offset, gainY: fy.gain, offsetY: fy.offset },
      headRange,
      baseline,
      window,
      samples.length,
    );
  }

  /** Kırpılmamış, düzeltilmiş tahmin (kırpış ve baş denetimi olmadan). */
  private project(features: readonly number[]): [number, number] {
    const [rawX, rawY] = predictLinear(this.model, features);
    const { gainX, offsetX, gainY, offsetY } = this.correction;
    return [rawX * gainX + offsetX, rawY * gainY + offsetY];
  }

  /** Canlı karede: ekran noktası ya da imlecin neden durduğu. */
  estimate(features: readonly number[] | null, window: WindowSize): GazeEstimate {
    if (!features) return { kind: 'hold', reason: 'no_face' };

    // Kırpışta tahmin sıçrar: o kareler atlanır, imleç yerinde kalır.
    if (!this.gate.accept(openness(features))) return { kind: 'hold', reason: 'blink' };

    // Kalibrasyonda görülmemiş baş pozunda model yalnızca uydurur.
    const yaw = features[YAW] ?? 0;
    const pitch = features[PITCH] ?? 0;
    const { yaw: yawRange, pitch: pitchRange } = this.headRange;
    if (yaw < yawRange[0] || yaw > yawRange[1] || pitch < pitchRange[0] || pitch > pitchRange[1]) {
      return { kind: 'hold', reason: 'head' };
    }

    // Model normalize koordinat öğrendi; pencere değişince aynı sayı ekranda
    // başka bir yere düşer (ör. Esc ile tam ekrandan çıkınca).
    if (!sameWindow(this.window, window)) return { kind: 'hold', reason: 'window' };

    const [x, y] = this.project(features);
    return { kind: 'point', x: clamp01(x), y: clamp01(y) };
  }

  /**
   * Baş oynadıysa: RECENTER_POINTS'e bakılarak toplanan örneklerle eksen
   * başına kazanç + kayma yeniden çözülür, izin verilen baş aralığı da ölçülen
   * kayma kadar taşınır (yoksa baş "çok uzakta" sayılmaya devam eder).
   */
  recenter(groups: ReadonlyArray<{ target: Point; samples: readonly GazeSample[] }>): boolean {
    const means: Array<{ target: Point; x: number; y: number }> = [];
    const yaws: number[] = [];
    const pitches: number[] = [];
    for (const { target, samples } of groups) {
      if (samples.length === 0) continue;
      let sumX = 0;
      let sumY = 0;
      for (const sample of samples) {
        const [x, y] = predictLinear(this.model, sample.features);
        sumX += x;
        sumY += y;
        yaws.push(sample.features[YAW] ?? 0);
        pitches.push(sample.features[PITCH] ?? 0);
      }
      means.push({ target, x: sumX / samples.length, y: sumY / samples.length });
    }

    const [a, b] = means;
    if (!a || !b) return false;
    const fx = fitAxis(a.x, a.target[0], b.x, b.target[0]);
    const fy = fitAxis(a.y, a.target[1], b.y, b.target[1]);
    this.correction = { gainX: fx.gain, offsetX: fx.offset, gainY: fy.gain, offsetY: fy.offset };

    const yaw = yaws.reduce((sum, v) => sum + v, 0) / yaws.length;
    const pitch = pitches.reduce((sum, v) => sum + v, 0) / pitches.length;
    const deltaYaw = yaw - this.headBaseline.yaw;
    const deltaPitch = pitch - this.headBaseline.pitch;
    this.headRange = {
      yaw: [this.headRange.yaw[0] + deltaYaw, this.headRange.yaw[1] + deltaYaw],
      pitch: [this.headRange.pitch[0] + deltaPitch, this.headRange.pitch[1] + deltaPitch],
    };
    this.headBaseline = { yaw, pitch };
    return true;
  }
}

export function sameWindow(a: WindowSize, b: WindowSize): boolean {
  return (
    Math.abs(a.width - b.width) <= a.width * WINDOW_TOLERANCE &&
    Math.abs(a.height - b.height) <= a.height * WINDOW_TOLERANCE
  );
}

// --- Baş pozu onayı --------------------------------------------------------

/** GazeLive.tsx ile aynı eşikler (ilk tahmin; kamerada ayarlanabilir). */
const YAW_TURN_THRESHOLD = 0.04;
const PITCH_TURN_THRESHOLD = 0.035;
/** ~0,6 sn üst üste eşiği geçmesi istenir. */
const POSE_STABLE_FRAMES = 18;

export const POSE_AXIS: Record<HeadPose, 'yaw' | 'pitch'> = {
  sağa: 'yaw',
  sola: 'yaw',
  yukarı: 'pitch',
  aşağı: 'pitch',
};

export interface PoseUpdate {
  /** 0–1; ters yöne dönülüyorsa 0. */
  progress: number;
  wrongWay: boolean;
  ready: boolean;
}

/**
 * Başın gerçekten istenen yöne döndüğünü kameradan okur.
 *
 * Çiftin ilki (sağa/yukarı) hangi yönden gelirse kabul edilir; ikincisi
 * (sola/aşağı) onun tersini ister. Yoksa baş geri getirilmeden ikinci poz da
 * anında onaylanmış görünür.
 */
export class PoseWatcher {
  readonly axis: 'yaw' | 'pitch';
  private readonly baseline: number;
  private readonly threshold: number;
  private readonly requireSign: number | null;
  private stable = 0;
  private lastSign = 0;
  private done = false;

  constructor(axis: 'yaw' | 'pitch', baseline: number, requireSign: number | null) {
    this.axis = axis;
    this.baseline = baseline;
    this.threshold = axis === 'yaw' ? YAW_TURN_THRESHOLD : PITCH_TURN_THRESHOLD;
    this.requireSign = requireSign;
  }

  update(features: readonly number[]): PoseUpdate {
    const value = (this.axis === 'yaw' ? features[YAW] : features[PITCH]) ?? 0;
    const delta = value - this.baseline;
    const sign = Math.sign(delta);
    const matchesSign = this.requireSign === null || sign === this.requireSign;
    const progress = matchesSign ? clamp01(Math.abs(delta) / this.threshold) : 0;
    if (progress >= 1) {
      this.stable += 1;
      this.lastSign = sign;
    } else {
      this.stable = 0;
    }
    if (this.stable >= POSE_STABLE_FRAMES) this.done = true;
    return { progress, wrongWay: !matchesSign, ready: this.done };
  }

  get ready(): boolean {
    return this.done;
  }

  /** Onaylanan dönüş yönü; çiftin ikinci pozu bunun tersini ister. */
  get sign(): number {
    return this.lastSign;
  }
}
