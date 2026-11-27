import { describe, expect, it } from 'vitest';

import {
  BrowserGazeModel,
  CALIBRATION_GRID,
  HEAD_POSE_POINTS,
  PoseWatcher,
  RECENTER_POINTS,
  fitAxis,
  sameWindow,
  type Point,
} from './browserGaze';
import { PITCH, YAW, type GazeSample } from './gazeLinear';

const WINDOW = { width: 1920, height: 1080 };
const BASELINE = { yaw: 0, pitch: 0 };

/** Tekrarlanabilir küçük gürültü. */
function noise(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296 - 0.5;
  };
}

/**
 * irisFeatures çıktısına benzeyen sentetik 10 öznitelik: iris konumu bakılan
 * noktayla doğrusal, açıklık sabit, baş pozu küçük gürültü, sonda iki çarpım terimi.
 */
function features(
  [x, y]: Point,
  rand: () => number,
  { shift = 0, open = 0.3, yaw = 0, pitch = 0 } = {},
): number[] {
  const lx = 0.4 + 0.2 * x + shift + rand() * 0.002;
  const ly = 0.4 + 0.2 * y + rand() * 0.002;
  const rx = 0.42 + 0.2 * x + shift + rand() * 0.002;
  const ry = 0.41 + 0.2 * y + rand() * 0.002;
  return [lx, ly, rx, ry, open, open, yaw + rand() * 0.02, pitch + rand() * 0.02, lx * ly, rx * ry];
}

function calibrationSamples(rand: () => number): GazeSample[] {
  const targets = [...CALIBRATION_GRID, ...HEAD_POSE_POINTS, ...HEAD_POSE_POINTS];
  return targets.flatMap((target) =>
    Array.from({ length: 10 }, () => ({
      features: features(target, rand),
      x: target[0],
      y: target[1],
    })),
  );
}

function fitted(seed = 1): BrowserGazeModel {
  const model = BrowserGazeModel.fit(calibrationSamples(noise(seed)), BASELINE, WINDOW);
  if (!model) throw new Error('model kurulamadı');
  return model;
}

describe('fitAxis', () => {
  it('iki noktadan kazanç ve kaymayı çözüyor', () => {
    const { gain, offset } = fitAxis(0.2, 0.1, 0.6, 0.9);
    expect(gain).toBeCloseTo(2);
    expect(offset).toBeCloseTo(-0.3);
  });

  it('noktalar çakışırsa kazancı 1 sayıyor', () => {
    expect(fitAxis(0.5, 0.4, 0.5, 0.9)).toEqual({ gain: 1, offset: expect.closeTo(-0.1) });
  });
});

describe('BrowserGazeModel', () => {
  it('az örnekle model kurmuyor', () => {
    const rand = noise(2);
    const few = calibrationSamples(rand).slice(0, 5);
    expect(BrowserGazeModel.fit(few, BASELINE, WINDOW)).toBeNull();
  });

  it('kalibrasyondan sonra bakılan noktayı buluyor', () => {
    const model = fitted();
    const rand = noise(3);
    for (const target of [[0.5, 0.5], [0.2, 0.8], [0.85, 0.15]] as Point[]) {
      const estimate = model.estimate(features(target, rand), WINDOW);
      expect(estimate.kind).toBe('point');
      if (estimate.kind !== 'point') continue;
      expect(estimate.x).toBeCloseTo(target[0], 1);
      expect(estimate.y).toBeCloseTo(target[1], 1);
    }
  });

  it('ekran dışı tahmini 0–1 aralığına kırpıyor', () => {
    const estimate = fitted().estimate(features([1.4, -0.3], noise(4)), WINDOW);
    expect(estimate).toEqual({ kind: 'point', x: 1, y: 0 });
  });

  it('yüz yoksa, gözler kapalıysa, baş uzaktaysa ya da pencere değiştiyse duruyor', () => {
    const model = fitted();
    const rand = noise(5);
    expect(model.estimate(null, WINDOW)).toEqual({ kind: 'hold', reason: 'no_face' });
    expect(model.estimate(features([0.5, 0.5], rand, { open: 0.05 }), WINDOW)).toEqual({
      kind: 'hold',
      reason: 'blink',
    });

    const head = fitted(6);
    expect(head.estimate(features([0.5, 0.5], rand, { yaw: 0.3 }), WINDOW)).toEqual({
      kind: 'hold',
      reason: 'head',
    });

    const win = fitted(7);
    expect(win.estimate(features([0.5, 0.5], rand), { width: 1280, height: 720 })).toEqual({
      kind: 'hold',
      reason: 'window',
    });
  });

  it('kırpıştan sonra göz açılırken gelen birkaç kareyi de atlıyor', () => {
    const model = fitted(8);
    const rand = noise(9);
    model.estimate(features([0.5, 0.5], rand, { open: 0.05 }), WINDOW);
    const next = model.estimate(features([0.5, 0.5], rand), WINDOW);
    expect(next).toEqual({ kind: 'hold', reason: 'blink' });
  });

  it('ortalama, kalibrasyondan sonraki kaymayı düzeltiyor', () => {
    const model = fitted(10);
    const rand = noise(11);
    const shift = 0.04; // iris ölçeğinde: ekranda ~0,2 kayma
    const before = model.estimate(features([0.5, 0.5], rand, { shift }), WINDOW);
    expect(before.kind === 'point' && Math.abs(before.x - 0.5) > 0.1).toBe(true);

    const groups = RECENTER_POINTS.map((target) => ({
      target,
      samples: Array.from({ length: 10 }, () => ({
        features: features(target, rand, { shift }),
        x: target[0],
        y: target[1],
      })),
    }));
    expect(model.recenter(groups)).toBe(true);

    const after = model.estimate(features([0.5, 0.5], rand, { shift }), WINDOW);
    expect(after.kind).toBe('point');
    if (after.kind === 'point') expect(after.x).toBeCloseTo(0.5, 1);
  });

  it('ortalama, izin verilen baş aralığını ölçülen kayma kadar taşıyor', () => {
    const model = fitted(12);
    const rand = noise(13);
    const moved = { yaw: 0.2 };
    expect(model.estimate(features([0.5, 0.5], rand, moved), WINDOW).kind).toBe('hold');

    const groups = RECENTER_POINTS.map((target) => ({
      target,
      samples: Array.from({ length: 10 }, () => ({
        features: features(target, rand, moved),
        x: target[0],
        y: target[1],
      })),
    }));
    model.recenter(groups);
    expect(model.estimate(features([0.5, 0.5], rand, moved), WINDOW).kind).toBe('point');
  });

  it('ortalamada örnek yoksa düzeltmeyi değiştirmiyor', () => {
    const model = fitted(14);
    const groups = RECENTER_POINTS.map((target) => ({ target, samples: [] }));
    expect(model.recenter(groups)).toBe(false);
  });
});

describe('sameWindow', () => {
  it('küçük farkı kabul ediyor, tam ekrandan çıkmayı etmiyor', () => {
    expect(sameWindow(WINDOW, { width: 1915, height: 1078 })).toBe(true);
    expect(sameWindow(WINDOW, { width: 1920, height: 960 })).toBe(false);
  });
});

describe('PoseWatcher', () => {
  const at = (yaw: number, pitch = 0) => {
    const values = new Array<number>(10).fill(0);
    values[YAW] = yaw;
    values[PITCH] = pitch;
    return values;
  };

  it('yeterince dönülüp ~0,6 sn tutulunca onaylıyor', () => {
    const watcher = new PoseWatcher('yaw', 0, null);
    for (let i = 0; i < 17; i += 1) expect(watcher.update(at(0.05)).ready).toBe(false);
    expect(watcher.update(at(0.05)).ready).toBe(true);
    expect(watcher.sign).toBe(1);
  });

  it('kısa bir kıpırdanmayı saymıyor', () => {
    const watcher = new PoseWatcher('yaw', 0, null);
    for (let i = 0; i < 10; i += 1) watcher.update(at(0.05));
    watcher.update(at(0));
    for (let i = 0; i < 10; i += 1) watcher.update(at(0.05));
    expect(watcher.ready).toBe(false);
  });

  it('çiftin ikinci pozunda ters yönü istiyor', () => {
    const watcher = new PoseWatcher('yaw', 0, -1);
    const update = watcher.update(at(0.05));
    expect(update.wrongWay).toBe(true);
    expect(update.progress).toBe(0);
    expect(watcher.update(at(-0.02)).progress).toBeCloseTo(0.5);
  });
});
