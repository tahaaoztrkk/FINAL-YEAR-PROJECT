/**
 * Tarayıcıda çalışan canlı bakış tahmini (`?bakis` sayfası için).
 *
 * features.py'deki iris ve göz açıklığı hesabının aynısı, üstüne
 * StandardScaler + Ridge(alpha=1) ile doğrusal eşleme. 10 Kasım ölçümlerinde
 * 1. derece model en iyi sonucu verdi. Baş öznitelikleri ancak kalibrasyonda
 * baş farklı pozlarda tutulursa işe yarıyor: baş sabitken öğrenilen model
 * küçük bir baş hareketinde tahmini ekran dışına fırlatıyor.
 *
 * Yalnızca denemelik: asıl eşleme sunucudaki GazeMapper'da kalır.
 */

import type { NormalizedLandmark } from '@mediapipe/tasks-vision';

const LEFT_IRIS = [468, 469, 470, 471, 472];
const RIGHT_IRIS = [473, 474, 475, 476, 477];
const LEFT = { inner: 133, outer: 33, top: 159, bottom: 145 };
const RIGHT = { inner: 362, outer: 263, top: 386, bottom: 374 };

interface Eye {
  inner: number;
  outer: number;
  top: number;
  bottom: number;
}

type Landmarks = readonly NormalizedLandmark[];

function at(points: Landmarks, index: number): NormalizedLandmark {
  const point = points[index];
  if (!point) throw new Error(`Landmark eksik: ${index}`);
  return point;
}

function distance(a: NormalizedLandmark, b: NormalizedLandmark): number {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}

function clip(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

function relativeIris(points: Landmarks, iris: number[], eye: Eye): [number, number] {
  let cx = 0;
  let cy = 0;
  for (const index of iris) {
    const point = at(points, index);
    cx += point.x / iris.length;
    cy += point.y / iris.length;
  }
  const inner = at(points, eye.inner);
  const outer = at(points, eye.outer);
  const top = at(points, eye.top);
  const bottom = at(points, eye.bottom);
  if (distance(inner, outer) < 1e-6 || distance(top, bottom) < 1e-6) return [0.5, 0.5];
  const relX = (cx - outer.x) / (inner.x - outer.x + 1e-9);
  const relY = (cy - top.y) / (bottom.y - top.y + 1e-9);
  return [clip(relX, -1, 2), clip(relY, -1, 2)];
}

function eyeOpenness(points: Landmarks, eye: Eye): number {
  const width = distance(at(points, eye.inner), at(points, eye.outer));
  return width > 1e-6 ? distance(at(points, eye.top), at(points, eye.bottom)) / width : 0;
}

/** features.py, ``_head_pose``: yaw ve pitch. */
function headPose(points: Landmarks): [number, number] {
  const left = at(points, 234);
  const right = at(points, 454);
  const nose = at(points, 1);
  const chin = at(points, 152);
  const forehead = at(points, 10);
  const faceWidth = distance(right, left) + 1e-9;
  const faceHeight = distance(chin, forehead) + 1e-9;
  const yaw = (nose.x - (left.x + right.x) / 2) / faceWidth;
  const pitch = (nose.y - (forehead.y + chin.y) / 2) / faceHeight;
  return [yaw, pitch];
}

export interface IrisFeatures {
  /** FEATURE_NAMES'in ilk sekizi: dört iris konumu, iki göz açıklığı, yaw, pitch. */
  values: number[];
  confidence: number;
}

export const YAW = 6;
export const PITCH = 7;

export function openness(features: readonly number[]): number {
  return ((features[4] ?? 0) + (features[5] ?? 0)) / 2;
}

export function irisFeatures(points: Landmarks): IrisFeatures {
  const [lx, ly] = relativeIris(points, LEFT_IRIS, LEFT);
  const [rx, ry] = relativeIris(points, RIGHT_IRIS, RIGHT);
  const leftOpen = eyeOpenness(points, LEFT);
  const rightOpen = eyeOpenness(points, RIGHT);
  const [yaw, pitch] = headPose(points);
  return {
    values: [lx, ly, rx, ry, leftOpen, rightOpen, yaw, pitch],
    confidence: clip(Math.min(leftOpen, rightOpen) / 0.2, 0, 1),
  };
}

export interface GazeSample {
  features: number[];
  x: number;
  y: number;
}

export interface LinearGazeModel {
  mean: number[];
  scale: number[];
  weightsX: number[];
  weightsY: number[];
  interceptX: number;
  interceptY: number;
}

/** Simetrik pozitif tanımlı A için Ax = b (Cholesky). */
function solve(matrix: number[][], rhs: number[]): number[] {
  const n = rhs.length;
  const lower = matrix.map((row) => row.map(() => 0));
  const cell = (m: number[][], i: number, j: number) => m[i]?.[j] ?? 0;
  const set = (m: number[][], i: number, j: number, v: number) => {
    const row = m[i];
    if (row) row[j] = v;
  };

  for (let i = 0; i < n; i += 1) {
    for (let j = 0; j <= i; j += 1) {
      let sum = cell(matrix, i, j);
      for (let k = 0; k < j; k += 1) sum -= cell(lower, i, k) * cell(lower, j, k);
      set(lower, i, j, i === j ? Math.sqrt(sum) : sum / cell(lower, j, j));
    }
  }

  const forward = new Array<number>(n).fill(0);
  for (let i = 0; i < n; i += 1) {
    let sum = rhs[i] ?? 0;
    for (let k = 0; k < i; k += 1) sum -= cell(lower, i, k) * (forward[k] ?? 0);
    forward[i] = sum / cell(lower, i, i);
  }

  const result = new Array<number>(n).fill(0);
  for (let i = n - 1; i >= 0; i -= 1) {
    let sum = forward[i] ?? 0;
    for (let k = i + 1; k < n; k += 1) sum -= cell(lower, k, i) * (result[k] ?? 0);
    result[i] = sum / cell(lower, i, i);
  }
  return result;
}

const ALPHA = 1;

/** scikit-learn'deki StandardScaler + Ridge(alpha=1) ile aynı çözüm. */
export function fitLinear(samples: readonly GazeSample[]): LinearGazeModel {
  const count = samples.length;
  const dim = samples[0]?.features.length ?? 0;
  const mean = new Array<number>(dim).fill(0);
  const scale = new Array<number>(dim).fill(0);

  for (let d = 0; d < dim; d += 1) {
    let sum = 0;
    for (const sample of samples) sum += sample.features[d] ?? 0;
    const m = sum / count;
    let variance = 0;
    for (const sample of samples) variance += ((sample.features[d] ?? 0) - m) ** 2;
    const std = Math.sqrt(variance / count);
    mean[d] = m;
    scale[d] = std > 0 ? std : 1;
  }

  const z = samples.map((sample) =>
    sample.features.map((value, d) => (value - (mean[d] ?? 0)) / (scale[d] ?? 1)),
  );
  const matrix = Array.from({ length: dim }, (_, i) =>
    Array.from({ length: dim }, (_unused, j) => {
      let sum = i === j ? ALPHA : 0;
      for (const row of z) sum += (row[i] ?? 0) * (row[j] ?? 0);
      return sum;
    }),
  );

  const axis = (read: (sample: GazeSample) => number) => {
    let total = 0;
    for (const sample of samples) total += read(sample);
    const intercept = total / count;
    const rhs = Array.from({ length: dim }, (_, d) => {
      let sum = 0;
      samples.forEach((sample, index) => {
        sum += (z[index]?.[d] ?? 0) * (read(sample) - intercept);
      });
      return sum;
    });
    return { intercept, weights: solve(matrix, rhs) };
  };

  const x = axis((sample) => sample.x);
  const y = axis((sample) => sample.y);
  return {
    mean,
    scale,
    weightsX: x.weights,
    weightsY: y.weights,
    interceptX: x.intercept,
    interceptY: y.intercept,
  };
}

/** Kırpılmamış tahmin; tek noktalı düzeltme ekran dışı değerleri de görmeli. */
export function predictLinear(model: LinearGazeModel, features: readonly number[]): [number, number] {
  let x = model.interceptX;
  let y = model.interceptY;
  features.forEach((value, d) => {
    const z = (value - (model.mean[d] ?? 0)) / (model.scale[d] ?? 1);
    x += z * (model.weightsX[d] ?? 0);
    y += z * (model.weightsY[d] ?? 0);
  });
  return [x, y];
}

function medianOf(values: readonly number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)] ?? 0;
}

/**
 * Kırpış eşiği, kalibrasyondan.
 *
 * Aşağı bakınca göz kapağı doğal olarak iner; eşik genel ortalamadan
 * hesaplanırsa ekranın altına bakmak kırpış sayılır ve imleç donar. Bu yüzden
 * en alt sıradaki noktaların açıklığı temel alınır.
 */
export function blinkThreshold(samples: readonly GazeSample[]): number {
  const bottom = samples.filter((sample) => sample.y >= 0.85);
  return 0.85 * medianOf((bottom.length > 0 ? bottom : samples).map((s) => openness(s.features)));
}

const BLINK_HOLD_FRAMES = 3;

/** Kırpış karelerini ve göz yeniden açılırken gelen birkaç kareyi eler. */
export class BlinkGate {
  private hold = 0;
  private readonly threshold: number;

  constructor(threshold: number) {
    this.threshold = threshold;
  }

  accept(value: number): boolean {
    if (value < this.threshold) {
      this.hold = BLINK_HOLD_FRAMES;
      return false;
    }
    if (this.hold > 0) {
      this.hold -= 1;
      return false;
    }
    return true;
  }
}

/** Kısa kayan medyan: filtreden kaçan tek tük sıçramaları yutar (~66 ms gecikme). */
export class Median5 {
  private buffer: number[] = [];

  apply(value: number): number {
    this.buffer.push(value);
    if (this.buffer.length > 5) this.buffer.shift();
    return medianOf(this.buffer);
  }

  reset(): void {
    this.buffer = [];
  }
}

function alpha(cutoff: number, dt: number): number {
  const tau = 1 / (2 * Math.PI * cutoff);
  return 1 / (1 + tau / dt);
}

/** filters.py'deki One Euro filtresi, aynı varsayılanlarla. */
export class OneEuro {
  private value: number | null = null;
  private derivative: number | null = null;
  private lastT: number | null = null;

  apply(input: number, t: number): number {
    if (this.value === null || this.lastT === null || t <= this.lastT) {
      this.lastT = t;
      this.value = this.value ?? input;
      return this.value;
    }
    const dt = t - this.lastT;
    this.lastT = t;
    const raw = (input - this.value) / dt;
    const dAlpha = alpha(1, dt);
    this.derivative = this.derivative === null ? raw : dAlpha * raw + (1 - dAlpha) * this.derivative;
    const a = alpha(1 + 0.007 * Math.abs(this.derivative), dt);
    this.value = a * input + (1 - a) * this.value;
    return this.value;
  }

  reset(): void {
    this.value = null;
    this.derivative = null;
    this.lastT = null;
  }
}
