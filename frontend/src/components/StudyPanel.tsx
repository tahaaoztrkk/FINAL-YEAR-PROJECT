/**
 * Kullanıcı testi: deneyi yürüten kişinin denetimleri ve hedef cümle.
 *
 * Denetimler (kod, başlat, atla) fareyle kullanılır ve bakış hedefi
 * değildir; katılımcı bunları bakışla seçemez. Blok tanıtımı ekranı kaplar
 * ve o sırada hiçbir tuş seçilemez: katılımcı mola verirken yanlışlıkla
 * yazmaya başlamasın.
 */

import { useState } from 'react';

import type { StudyState } from '@/features/study/useStudy';
import type { StudyBlock, StudyTrial } from '@/types/messages';

const CONDITION_LABEL: Record<string, string> = {
  A: 'harf harf yazma',
  B: 'kısaltma ve aday cümleler',
};

interface ControlsProps {
  study: StudyState;
  block: StudyBlock | null;
  /** Bağlantı yokken atlanan cümle sunucuya ulaşmaz ve kayıttan düşer. */
  connected: boolean;
  error: string | null;
  onStart: (participantId: string) => void;
  onSkip: () => void;
}

/** Durum çubuğundaki denetimler. */
export function StudyControls({ study, block, connected, error, onStart, onSkip }: ControlsProps) {
  const [code, setCode] = useState('');

  if (study.phase === 'idle' || (study.phase === 'starting' && error)) {
    return (
      <form
        className="study-controls"
        onSubmit={(event) => {
          event.preventDefault();
          if (code.trim()) onStart(code.trim());
        }}
      >
        <input
          aria-label="Katılımcı kodu"
          placeholder="K01"
          value={code}
          maxLength={4}
          onChange={(event) => setCode(event.target.value)}
        />
        <button type="submit" disabled={!connected}>
          Deneyi başlat
        </button>
      </form>
    );
  }

  return (
    <div className="study-controls">
      <span>
        {study.participantId} · {study.order ?? '…'}
        {block && ` · blok ${study.blockIndex + 1}/${study.blocks.length} (${block.condition})`}
      </span>
      {study.phase === 'trial' && (
        <button type="button" onClick={onSkip} disabled={!connected}>
          Atla
        </button>
      )}
    </div>
  );
}

interface TargetProps {
  study: StudyState;
  block: StudyBlock;
  trial: StudyTrial;
}

/** Yazılacak cümle. Kısaltma alanının üstünde, ekranın tepesinde durur. */
export function StudyTarget({ study, block, trial }: TargetProps) {
  const practice = block.trials.filter((item) => item.practice).length;
  const measured = block.trials.length - practice;
  // Alıştırmalar önce gelir; ölçülen cümleler 1'den numaralanır.
  const position = trial.practice ? 'alıştırma' : `${trial.index - practice + 1}/${measured}`;

  return (
    <div className={`study-target${study.mismatch ? ' study-target--mismatch' : ''}`}>
      <span className="study-target__meta">
        {position} · {block.condition}
      </span>
      <span className="study-target__text">{trial.text}</span>
      {study.mismatch && <span className="study-target__hint">Aynı değil, düzeltip yeniden seslendirin</span>}
    </div>
  );
}

interface OverlayProps {
  study: StudyState;
  block: StudyBlock | null;
  onBegin: () => void;
}

/** Blok tanıtımı, mola ve bitiş ekranı. */
export function StudyOverlay({ study, block, onBegin }: OverlayProps) {
  if (study.phase === 'finished') {
    return (
      <div className="study-overlay" role="dialog" aria-label="Deney bitti">
        <h2>Teşekkürler, deney bitti.</h2>
        <p>Şimdi anketlere geçebiliriz.</p>
      </div>
    );
  }
  if (study.phase !== 'intro' || !block) return null;

  const practice = block.trials.filter((trial) => trial.practice).length;
  const measured = block.trials.length - practice;
  return (
    <div className="study-overlay" role="dialog" aria-label="Blok tanıtımı">
      {study.blockIndex > 0 && <p className="study-overlay__break">Mola</p>}
      <h2>
        Blok {study.blockIndex + 1}/{study.blocks.length}: {CONDITION_LABEL[block.condition]}
      </h2>
      <p>
        {practice} alıştırma cümlesi, ardından {measured} cümle.
        {block.condition === 'B' && ` Şema: ${block.scheme}.`}
      </p>
      <button type="button" onClick={onBegin}>
        Bloğu başlat
      </button>
    </div>
  );
}
