/**
 * backend/src/gaze_aac/gaze/features.py'nin TypeScript karşılığı.
 *
 * Aynı 12 öznitelik, aynı sıra, aynı formüller. Sıra bir sözleşmedir: sunucuda
 * eğitilen kalibrasyon modeli bu sütunları bu sırayla bekler. features.py
 * değişirse bu dosya da değişmeli; ikisi de
 * `__fixtures__/features.json` dosyasına karşı test ediliyor
 * (Python: tests/test_gaze.py, TypeScript: features.test.ts).
 *
 * Mesafeler Python'daki gibi x, y ve z'yi birlikte kullanır (np.linalg.norm
 * üç boyutlu satırlar üzerinde).
 */

import type { NormalizedLandmark } from '@mediapipe/tasks-vision';

export const FEATURE_NAMES = [
  'left_iris_rel_x',
  'left_iris_rel_y',
  'right_iris_rel_x',
  'right_iris_rel_y',
  'left_eye_openness',
  'right_eye_openness',
  'head_yaw',
  'head_pitch',
  'head_roll',
  'face_scale',
  'iris_disparity_x',
  'iris_disparity_y',
] as const;

export const FEATURE_DIM = FEATURE_NAMES.length;

/** FEATURE_NAMES içindeki konumlar; dizinle erişimde sihirli sayı olmasın. */
export const FEATURE_INDEX = Object.fromEntries(
  FEATURE_NAMES.map((name, index) => [name, index]),
) as { readonly [K in (typeof FEATURE_NAMES)[number]]: number };

const LEFT_IRIS = [468, 469, 470, 471, 472];
const RIGHT_IRIS = [473, 474, 475, 476, 477];
const LEFT_EYE = { inner: 133, outer: 33, top: 159, bottom: 145 };
const RIGHT_EYE = { inner: 362, outer: 263, top: 386, bottom: 374 };
const FACE_LEFT = 234;
const FACE_RIGHT = 454;
const NOSE_TIP = 1;
const CHIN = 152;
const FOREHEAD = 10;

/** MediaPipe iris dahil 478 nokta döndürür; features.py de bunu şart koşar. */
export const REQUIRED_LANDMARKS = 478;

interface Eye {
  inner: number;
  outer: number;
  top: number;
  bottom: number;
}

/** x ve y zorunlu, z yoksa 0 sayılır (Python'da 2 sütunlu dizi gibi). */
export type Point = Pick<NormalizedLandmark, 'x' | 'y'> & { z?: number };
export type Landmarks = readonly Point[];

export interface EyeFeatures {
  /** FEATURE_NAMES sırasıyla 12 sayı. */
  values: number[];
  /** Göz açıklığından; iki göz de kapalıyken 0. */
  confidence: number;
}

function at(points: Landmarks, index: number): Point {
  const point = points[index];
  if (!point) throw new Error(`Landmark eksik: ${index}`);
  return point;
}

function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y, (a.z ?? 0) - (b.z ?? 0));
}

function clip(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

function centroid(points: Landmarks, indices: readonly number[]): [number, number] {
  // np.mean ile aynı sonuç için önce topla, sonra böl.
  let sx = 0;
  let sy = 0;
  for (const index of indices) {
    const point = at(points, index);
    sx += point.x;
    sy += point.y;
  }
  return [sx / indices.length, sy / indices.length];
}

/** features.py, ``_relative_iris``. 0 = dış köşe, 1 = iç köşe. */
function relativeIris(points: Landmarks, iris: readonly number[], eye: Eye): [number, number] {
  const [cx, cy] = centroid(points, iris);
  const inner = at(points, eye.inner);
  const outer = at(points, eye.outer);
  const top = at(points, eye.top);
  const bottom = at(points, eye.bottom);
  if (distance(inner, outer) < 1e-6 || distance(top, bottom) < 1e-6) return [0.5, 0.5];
  const relX = (cx - outer.x) / (inner.x - outer.x + 1e-9);
  const relY = (cy - top.y) / (bottom.y - top.y + 1e-9);
  return [clip(relX, -1, 2), clip(relY, -1, 2)];
}

/** features.py, ``_eye_openness``. */
function eyeOpenness(points: Landmarks, eye: Eye): number {
  const height = distance(at(points, eye.top), at(points, eye.bottom));
  const width = distance(at(points, eye.inner), at(points, eye.outer));
  return width > 1e-6 ? height / width : 0;
}

/** features.py, ``_head_pose``: yaw, pitch, roll. */
function headPose(points: Landmarks): [number, number, number] {
  const left = at(points, FACE_LEFT);
  const right = at(points, FACE_RIGHT);
  const nose = at(points, NOSE_TIP);
  const chin = at(points, CHIN);
  const forehead = at(points, FOREHEAD);

  const faceWidth = distance(right, left) + 1e-9;
  const faceHeight = distance(chin, forehead) + 1e-9;

  const yaw = (nose.x - (left.x + right.x) / 2) / faceWidth;
  const pitch = (nose.y - (forehead.y + chin.y) / 2) / faceHeight;
  const roll = Math.atan2(right.y - left.y, right.x - left.x);
  return [yaw, pitch, roll];
}

/** features.py, ``extract_features``. */
export function extractFeatures(points: Landmarks): EyeFeatures {
  if (points.length < REQUIRED_LANDMARKS) {
    throw new Error(
      `${REQUIRED_LANDMARKS} landmark bekleniyordu, ${points.length} geldi. ` +
        'FaceLandmarker iris noktalarını döndürüyor mu?',
    );
  }

  const [lx, ly] = relativeIris(points, LEFT_IRIS, LEFT_EYE);
  const [rx, ry] = relativeIris(points, RIGHT_IRIS, RIGHT_EYE);
  const leftOpen = eyeOpenness(points, LEFT_EYE);
  const rightOpen = eyeOpenness(points, RIGHT_EYE);
  const [yaw, pitch, roll] = headPose(points);
  const faceScale = distance(at(points, FACE_RIGHT), at(points, FACE_LEFT));

  return {
    values: [lx, ly, rx, ry, leftOpen, rightOpen, yaw, pitch, roll, faceScale, lx - rx, ly - ry],
    confidence: clip(Math.min(leftOpen, rightOpen) / 0.2, 0, 1),
  };
}
