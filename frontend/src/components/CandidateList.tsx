/**
 * Aday cümle listesi.
 *
 * Yalnızca geri kontrolden geçen adaylar gösterilir: kısaltması girdiyle
 * eşleşmeyen bir cümleyi kullanıcıya sunmak, seçtiğinde yanlış cümle
 * söyletir.
 *
 * Adayların dwell hedefleri ekrandaki konumlarından ölçülür. Liste akışta
 * yer aldığı için konumu üstündeki alanlara (durum çubuğu, hedef cümle,
 * kısaltma) bağlı; sabit koordinat verilirse kullanıcı bir adaya bakar,
 * dwell başkasını seçer.
 */

import { useEffect, useLayoutEffect, useReducer, useRef } from 'react';

import type { Candidate, GazeTarget } from '@/types/messages';

interface Props {
  candidates: Candidate[];
  dwellTargetId: string | null;
  dwellProgress: number;
  latencyMs: number | null;
  /** Genişletme yapıldı ama geçerli aday çıkmadı. */
  noResult: boolean;
  /** Tıklama hedef kimliğiyle bildirilir; seçim dwell ile aynı yoldan geçer. */
  onSelect: (targetId: string) => void;
  /** Adayların ekrandaki konumu değiştiğinde çağrılır. */
  onTargetsChange: (targets: GazeTarget[]) => void;
}

const round = (value: number) => Math.round(value * 10000) / 10000;

function measure(list: HTMLElement | null): GazeTarget[] {
  if (!list) return [];
  const width = window.innerWidth;
  const height = window.innerHeight;
  return Array.from(list.querySelectorAll<HTMLElement>('[data-target-id]')).map((element) => {
    const rect = element.getBoundingClientRect();
    return {
      id: element.dataset.targetId ?? '',
      x: round(Math.max(0, rect.left / width)),
      y: round(Math.max(0, rect.top / height)),
      width: round(Math.min(1, rect.width / width)),
      height: round(Math.min(1, rect.height / height)),
      label: '',
      kind: 'candidate' as const,
    };
  });
}

export function CandidateList({
  candidates,
  dwellTargetId,
  dwellProgress,
  latencyMs,
  noResult,
  onSelect,
  onTargetsChange,
}: Props) {
  const visible = candidates.filter((candidate) => candidate.valid);
  const listRef = useRef<HTMLDivElement>(null);
  const reported = useRef('');
  const [, remeasure] = useReducer((count: number) => count + 1, 0);

  // Her çizimden sonra ölçülür ama yalnızca değişince bildirilir: konum
  // üstteki alanların yüksekliğiyle de kayar, bunu tek tek izlemek kırılgan.
  useLayoutEffect(() => {
    const targets = measure(listRef.current);
    const key = JSON.stringify(targets);
    if (key !== reported.current) {
      reported.current = key;
      onTargetsChange(targets);
    }
  });

  useEffect(() => {
    window.addEventListener('resize', remeasure);
    return () => window.removeEventListener('resize', remeasure);
  }, []);

  if (visible.length === 0) {
    return (
      <div className="candidates candidates--empty" ref={listRef}>
        <p>
          {noResult
            ? 'Bu kısaltma için aday bulunamadı. Kelimeler arasına Boşluk koymayı deneyin.'
            : 'Harf seçin, ardından “Tamamla” deyin.'}
        </p>
      </div>
    );
  }

  return (
    <div className="candidates" ref={listRef}>
      {visible.map((candidate, index) => {
        const targetId = `candidate:${index}`;
        const active = dwellTargetId === targetId;
        return (
          <button
            key={candidate.text}
            type="button"
            data-target-id={targetId}
            className={`candidate${active ? ' candidate--active' : ''}`}
            onClick={() => onSelect(targetId)}
          >
            <span className="candidate__index">{index + 1}</span>
            <span className="candidate__text">{candidate.text}</span>
            {active && (
              <span className="candidate__progress" style={{ width: `${dwellProgress * 100}%` }} />
            )}
          </button>
        );
      })}
      {latencyMs !== null && (
        <p className="candidates__latency">{Math.round(latencyMs)} ms</p>
      )}
    </div>
  );
}
