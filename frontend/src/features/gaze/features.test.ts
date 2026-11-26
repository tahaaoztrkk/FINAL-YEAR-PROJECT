/**
 * features.ts, features.py ile aynı sonucu veriyor mu?
 *
 * Beklenen değerler Python'dan geliyor (backend/scripts/export_feature_fixture.py).
 * Python tarafı aynı dosyaya karşı backend/tests/test_gaze.py'de test ediliyor;
 * ikisi birlikte "TypeScript = Python" demek.
 */

import { describe, expect, it } from 'vitest';

import fixture from './__fixtures__/features.json';
import { FEATURE_DIM, FEATURE_NAMES, extractFeatures, type Point } from './features';
import { irisFeatures } from './gazeLinear';

const TOLERANCE = 1e-12;

interface Case {
  name: string;
  points: Record<string, number[]>;
  values: number[];
  confidence: number;
}

const cases = fixture.cases as Case[];

function landmarks(points: Record<string, number[]>): Point[] {
  const [fx, fy, fz] = fixture.fill as [number, number, number];
  const result: Point[] = Array.from({ length: 478 }, () => ({ x: fx, y: fy, z: fz }));
  for (const [index, xyz] of Object.entries(points)) {
    const [x = fx, y = fy, z = fz] = xyz;
    result[Number(index)] = { x, y, z };
  }
  return result;
}

describe('extractFeatures', () => {
  it('Python ile aynı öznitelik sırasını kullanıyor', () => {
    expect([...FEATURE_NAMES]).toEqual(fixture.feature_names);
    expect(FEATURE_DIM).toBe(12);
  });

  it('test verisinde yeterince vaka var', () => {
    expect(cases.length).toBeGreaterThanOrEqual(40);
  });

  it.each(cases.map((c) => [c.name, c] as const))('%s', (_name, c) => {
    const result = extractFeatures(landmarks(c.points));
    expect(result.values).toHaveLength(FEATURE_DIM);
    result.values.forEach((value, i) => {
      const expected = c.values[i] ?? Number.NaN;
      if (Math.abs(value - expected) > TOLERANCE) {
        throw new Error(`${FEATURE_NAMES[i]}: TypeScript ${value}, Python ${expected}`);
      }
    });
    expect(Math.abs(result.confidence - c.confidence)).toBeLessThanOrEqual(TOLERANCE);
  });

  it('eksik landmark dizisini reddediyor', () => {
    expect(() => extractFeatures(landmarks({}).slice(0, 468))).toThrow(/478/);
  });
});

describe('irisFeatures (?bakis)', () => {
  it('12 özniteliğin ilk 8\'ini aynen verip göz başına x*y çarpım terimi ekliyor', () => {
    for (const c of cases) {
      const points = landmarks(c.points) as Parameters<typeof irisFeatures>[0];
      const full = extractFeatures(points);
      const iris = irisFeatures(points);
      const base = full.values.slice(0, 8);
      const [lx, ly, rx, ry] = base;
      expect(iris.values).toEqual([...base, (lx ?? 0) * (ly ?? 0), (rx ?? 0) * (ry ?? 0)]);
      expect(iris.confidence).toBe(full.confidence);
    }
  });
});
