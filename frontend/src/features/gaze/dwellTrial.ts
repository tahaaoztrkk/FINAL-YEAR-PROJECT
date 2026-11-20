/**
 * `?bakis` dwell denemesi: 13 Kasım planındaki karar ölçütü
 * "700 ms dwell ile 10 denemede en az 8 doğru tuş".
 *
 * Ekranda bir hedef hücre işaretlenir; kullanıcı hangi hücrede 700 ms
 * durursa o seçilmiş sayılır (doğru ya da yanlış). Seçimden sonra kısa bir
 * ara verilir ki göz bir sonraki hedefe giderken yanlışlıkla seçim olmasın.
 *
 * React'ten bağımsızdır; zaman saniye cinsinden kare zamanıdır (FaceFrame.t).
 */

export const DWELL_S = 0.7;
export const PAUSE_S = 0.8;
/**
 * İki kare arasında bundan uzun boşluk (uzun kırpış, yeniden ortalama, yüz
 * kaybı) dwell'i keser; yoksa dönüşte biriken süre anında seçim yapardı.
 * Sunucudaki dwell'in iptal toleransına benzer.
 */
export const MAX_GAP_S = 0.25;
export const TRIAL_COUNT = 10;

export interface TrialResult {
  target: number;
  selected: number;
  correct: boolean;
  /** Hedef gösterildikten seçime kadar geçen süre. */
  timeMs: number;
}

export interface TrialUpdate {
  /** Şu anki hücrede dwell ilerlemesi, 0–1. */
  progress: number;
  /** Bu karede seçim olduysa sonucu. */
  selected: TrialResult | null;
  /** Ara bitti, yeni hedef gösterilmeli. */
  newTarget: boolean;
  done: boolean;
}

/** Aynı hücre iki kez sorulmasın: 12 hücreden 10 farklı hedef. */
export function pickTargets(count: number, tiles: number, random = Math.random): number[] {
  const all = Array.from({ length: tiles }, (_, i) => i);
  for (let i = all.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [all[i], all[j]] = [all[j] as number, all[i] as number];
  }
  const picked = [];
  while (picked.length < count) picked.push(...all);
  return picked.slice(0, count);
}

export class DwellTrial {
  readonly results: TrialResult[] = [];
  private index = 0;
  private shownAt: number | null = null;
  private dwellTile = -1;
  private dwellStart = 0;
  private pauseUntil = -Infinity;
  private lastT: number | null = null;

  constructor(
    readonly targets: readonly number[],
    readonly dwellS = DWELL_S,
    readonly pauseS = PAUSE_S,
  ) {}

  get done(): boolean {
    return this.index >= this.targets.length;
  }

  get target(): number | null {
    return this.done ? null : (this.targets[this.index] ?? null);
  }

  /** Kaçıncı denemede olunduğu, 1'den başlar. */
  get trialNumber(): number {
    return Math.min(this.index + 1, this.targets.length);
  }

  get correctCount(): number {
    return this.results.filter((r) => r.correct).length;
  }

  /** Bakışın şu an bulunduğu hücreyle her karede çağrılır. */
  update(tile: number, t: number): TrialUpdate {
    const idle = (newTarget = false): TrialUpdate => ({
      progress: 0,
      selected: null,
      newTarget,
      done: this.done,
    });
    if (this.done) return idle();

    if (this.lastT !== null && t - this.lastT > MAX_GAP_S) this.dwellTile = -1;
    this.lastT = t;

    if (t < this.pauseUntil) return idle();
    let newTarget = false;
    if (this.shownAt === null) {
      this.shownAt = t;
      newTarget = this.results.length > 0;
    }

    if (tile !== this.dwellTile) {
      this.dwellTile = tile;
      this.dwellStart = t;
      return idle(newTarget);
    }

    const progress = Math.min(1, (t - this.dwellStart) / this.dwellS);
    if (progress < 1) return { progress, selected: null, newTarget, done: false };

    const target = this.targets[this.index] ?? -1;
    const result: TrialResult = {
      target,
      selected: tile,
      correct: tile === target,
      timeMs: Math.round((t - this.shownAt) * 1000),
    };
    this.results.push(result);
    this.index += 1;
    this.shownAt = null;
    this.dwellTile = -1;
    this.pauseUntil = t + this.pauseS;
    return { progress: 1, selected: result, newTarget: false, done: this.done };
  }
}
