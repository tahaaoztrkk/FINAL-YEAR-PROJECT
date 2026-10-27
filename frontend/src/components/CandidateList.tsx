/**
 * Aday cümle listesi.
 *
 * Yalnızca geri kontrolden geçen adaylar gösterilir: kısaltması girdiyle
 * eşleşmeyen bir cümleyi kullanıcıya sunmak, seçtiğinde yanlış cümle
 * söyletir.
 */

import type { Candidate } from '@/types/messages';

interface Props {
  candidates: Candidate[];
  dwellTargetId: string | null;
  dwellProgress: number;
  latencyMs: number | null;
  /** Genişletme yapıldı ama geçerli aday çıkmadı. */
  noResult: boolean;
  onSelect: (text: string) => void;
}

export function CandidateList({
  candidates,
  dwellTargetId,
  dwellProgress,
  latencyMs,
  noResult,
  onSelect,
}: Props) {
  const visible = candidates.filter((candidate) => candidate.valid);

  if (visible.length === 0) {
    return (
      <div className="candidates candidates--empty">
        <p>
          {noResult
            ? 'Bu kısaltma için aday bulunamadı. Kelimeler arasına Boşluk koymayı deneyin.'
            : 'Harf seçin, ardından “Tamamla” deyin.'}
        </p>
      </div>
    );
  }

  return (
    <div className="candidates">
      {visible.map((candidate, index) => {
        const targetId = `candidate:${index}`;
        const active = dwellTargetId === targetId;
        return (
          <button
            key={candidate.text}
            type="button"
            className={`candidate${active ? ' candidate--active' : ''}`}
            onClick={() => onSelect(candidate.text)}
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
