/**
 * Tarayıcıda çalışan canlı bakış tahmini (`?bakis` sayfası için).
 *
 * features.py'deki iris ve göz açıklığı hesabının aynısı, üstüne
 * StandardScaler + Ridge(alpha=1) ile doğrusal eşleme. 10 Kasım ölçümlerinde
 * baş öznitelikleri olmadan 1. derece model en iyi sonucu verdi: kalibrasyonda
 * baş neredeyse sabit olduğu için baş öznitelikleri küçük bir harekette
 * tahmini ekran dışına fırlatıyor.
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

export interface IrisFeatures {
  /** left_iris_rel_x, left_iris_rel_y, right_iris_rel_x, right_iris_rel_y, iki göz açıklığı. */
  values: number[];
  confidence: number;
}

export function irisFeatures(points: Landmarks): IrisFeatures {
  const [lx, ly] = relativeIris(points, LEFT_IRIS, LEFT);
  const [rx, ry] = relativeIris(points, RIGHT_IRIS, RIGHT);
  const leftOpen = eyeOpenness(points, LEFT);
  const rightOpen = eyeOpenness(points, RIGHT);
  return {
    values: [lx, ly, rx, ry, leftOpen, rightOpen],
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
