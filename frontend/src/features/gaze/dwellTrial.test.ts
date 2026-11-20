import { describe, expect, it } from 'vitest';

import { DwellTrial, parseGrid, pickTargets } from './dwellTrial';

/** Bakışı ``tile``'da ``seconds`` boyunca 30 Hz tutar; son güncellemeyi döndürür. */
function hold(trial: DwellTrial, tile: number, from: number, seconds: number) {
  let last = trial.update(tile, from);
  for (let t = from + 1 / 30; t <= from + seconds + 1e-9; t += 1 / 30) {
    last = trial.update(tile, t);
    if (last.selected) return { update: last, t };
  }
  return { update: last, t: from + seconds };
}

describe('pickTargets', () => {
  it('12 hücreden 10 farklı hedef seçer', () => {
    const targets = pickTargets(10, 12);
    expect(targets).toHaveLength(10);
    expect(new Set(targets).size).toBe(10);
    targets.forEach((t) => expect(t).toBeGreaterThanOrEqual(0));
  });
});

describe('pickTargets az hücrede', () => {
  it('2x2 ızgarada 10 hedef, art arda aynı hücre yok', () => {
    for (let seed = 0; seed < 50; seed += 1) {
      const targets = pickTargets(10, 4);
      expect(targets).toHaveLength(10);
      targets.forEach((t, i) => {
        expect(t).toBeLessThan(4);
        if (i > 0) expect(t).not.toBe(targets[i - 1]);
      });
    }
  });
});

describe('parseGrid', () => {
  it('izgara parametresini okur, tanınmayanı 4x3 yapar', () => {
    expect(parseGrid('?bakis')).toEqual([4, 3]);
    expect(parseGrid('?bakis&izgara=3x2')).toEqual([3, 2]);
    expect(parseGrid('?bakis&izgara=2x2')).toEqual([2, 2]);
    expect(parseGrid('?bakis&izgara=9x9')).toEqual([4, 3]);
  });
});

describe('DwellTrial', () => {
  it('700 ms dolmadan seçmez, dolunca seçer', () => {
    const trial = new DwellTrial([3]);
    expect(hold(trial, 3, 0, 0.6).update.selected).toBeNull();
    const { update } = hold(trial, 3, 0.6 + 1 / 30, 0.8);
    expect(update.selected).toMatchObject({ target: 3, selected: 3, correct: true });
  });

  it('hücre değişince sayaç sıfırlanır', () => {
    const trial = new DwellTrial([3]);
    hold(trial, 3, 0, 0.5);
    expect(trial.update(4, 0.55).progress).toBe(0);
    expect(hold(trial, 3, 0.6, 0.5).update.selected).toBeNull();
  });

  it('karelerde uzun boşluk olursa dwell baştan başlar', () => {
    const trial = new DwellTrial([3]);
    hold(trial, 3, 0, 0.5);
    // ör. 2 sn yeniden ortalama; dönüşte biriken süreyle anında seçmemeli
    expect(trial.update(3, 2.5).selected).toBeNull();
    expect(trial.update(3, 2.6).selected).toBeNull();
    expect(hold(trial, 3, 2.6, 0.8).update.selected).not.toBeNull();
  });

  it('yanlış hücre de seçilir ve yanlış sayılır', () => {
    const trial = new DwellTrial([3, 5]);
    const { update } = hold(trial, 7, 0, 1);
    expect(update.selected).toMatchObject({ target: 3, selected: 7, correct: false });
    expect(trial.target).toBe(5);
  });

  it('seçimden sonraki arada yeni seçim olmaz', () => {
    const trial = new DwellTrial([3, 3]);
    const first = hold(trial, 3, 0, 1);
    const during = hold(trial, 3, first.t + 1 / 30, 0.7);
    expect(during.update.selected).toBeNull();
    expect(trial.results).toHaveLength(1);
  });

  it('10 denemeyi sayar ve süreyi hedef gösterildiği andan ölçer', () => {
    const targets = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
    const trial = new DwellTrial(targets);
    let t = 0;
    for (const target of targets) {
      const looked = target < 8 ? target : 11; // son ikisi yanlış
      const { t: end } = hold(trial, looked, t, 2);
      t = end + 1; // aradan sonra
    }
    expect(trial.done).toBe(true);
    expect(trial.correctCount).toBe(8);
    trial.results.forEach((r) => expect(r.timeMs).toBeGreaterThanOrEqual(700));
  });
});
