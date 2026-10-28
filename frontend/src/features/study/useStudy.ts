/**
 * Kullanıcı testinin akışı.
 *
 * Plan sunucudan gelir (koşul sırası ve cümleler orada kurulur); burası
 * yalnızca planı adım adım izler: blok tanıtımı, cümleler, mola, bitiş.
 * Ölçüm de sunucuda tutulur; arayüz her cümlenin başını ve sonunu bildirir.
 *
 * Gönderimler durum güncelleyicisinin içinde yapılmaz: React geliştirme
 * modunda güncelleyiciyi iki kez çalıştırır ve her mesaj iki kez kaydedilir.
 * Güncel durum bu yüzden bir ref'te tutulur.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { ClientMessage, ServerStudyPlan, StudyBlock, StudyTrial } from '@/types/messages';

import { sentencesMatch } from './normalize';

export type StudyPhase = 'idle' | 'starting' | 'intro' | 'trial' | 'finished';

export type SpokenResult = 'done' | 'retry' | null;

export interface StudyState {
  phase: StudyPhase;
  participantId: string | null;
  order: string | null;
  blocks: StudyBlock[];
  blockIndex: number;
  trialIndex: number;
  /** Son seslendirme hedefle eşleşmedi; katılımcı düzeltip yeniden dener. */
  mismatch: boolean;
}

const INITIAL: StudyState = {
  phase: 'idle',
  participantId: null,
  order: null,
  blocks: [],
  blockIndex: 0,
  trialIndex: 0,
  mismatch: false,
};

export interface UseStudyResult {
  study: StudyState;
  block: StudyBlock | null;
  trial: StudyTrial | null;
  start: (participantId: string) => void;
  beginBlock: () => void;
  /**
   * Seslendirilen her metin buraya gelir. Hedefle eşleşirse cümle biter
   * (`done`); eşleşmezse katılımcı düzeltip yeniden dener (`retry`). Deney
   * dışında `null` döner.
   */
  handleSpoken: (text: string) => SpokenResult;
  skip: (output: string) => void;
}

export function useStudy(
  send: (message: ClientMessage) => void,
  plan: ServerStudyPlan | null,
  sessionId: string | null,
  /** Yarım kalan cümle yeniden başlatılırken çağrılır; arayüz yazılanı siler. */
  onResume?: () => void,
): UseStudyResult {
  const [study, setStudy] = useState<StudyState>(INITIAL);
  const studyRef = useRef(study);
  const resumeRef = useRef(onResume);
  resumeRef.current = onResume;

  const update = useCallback((next: StudyState) => {
    studyRef.current = next;
    setStudy(next);
  }, []);

  const start = useCallback(
    (participantId: string) => {
      update({ ...INITIAL, phase: 'starting', participantId });
      send({ type: 'study_start', participant_id: participantId });
    },
    [send, update],
  );

  // Plan yalnızca başlatma beklenirken alınır. Yeniden bağlanınca sunucu
  // aynı planı tekrar yollar; o sırada süren deney baştan başlamamalı.
  useEffect(() => {
    if (!plan || studyRef.current.phase !== 'starting') return;
    update({
      ...studyRef.current,
      phase: 'intro',
      participantId: plan.participant_id,
      order: plan.order,
      blocks: plan.blocks,
      blockIndex: 0,
      trialIndex: 0,
    });
  }, [plan, update]);

  // Bağlantı koptuysa sunucu oturumu ve kaydı kapandı. Yeni bağlantıda
  // deney kaldığı yerden sürer: kayıt yeni dosyada açılır, yarım kalan
  // cümle baştan başlar. Yazılan da silinir; yoksa kopmadan önceki seçimler
  // yeni kayıtta görünmez ve cümle olduğundan hızlı ölçülür.
  useEffect(() => {
    const current = studyRef.current;
    if (!sessionId || !current.participantId) return;
    if (current.phase !== 'intro' && current.phase !== 'trial') return;
    send({ type: 'study_start', participant_id: current.participantId });
    if (current.phase === 'trial') {
      resumeRef.current?.();
      update({ ...current, mismatch: false });
      send({
        type: 'trial_start',
        block_index: current.blockIndex,
        trial_index: current.trialIndex,
      });
    }
  }, [sessionId, send, update]);

  const beginBlock = useCallback(() => {
    const current = studyRef.current;
    if (current.phase !== 'intro') return;
    update({ ...current, phase: 'trial', trialIndex: 0, mismatch: false });
    send({ type: 'trial_start', block_index: current.blockIndex, trial_index: 0 });
  }, [send, update]);

  const finishTrial = useCallback(
    (outcome: 'done' | 'skipped', output: string) => {
      const current = studyRef.current;
      if (current.phase !== 'trial') return;
      const block = current.blocks[current.blockIndex];
      if (!block) return;

      send({
        type: 'trial_end',
        block_index: current.blockIndex,
        trial_index: current.trialIndex,
        outcome,
        output,
      });

      const nextTrial = current.trialIndex + 1;
      if (nextTrial < block.trials.length) {
        update({ ...current, trialIndex: nextTrial, mismatch: false });
        send({ type: 'trial_start', block_index: current.blockIndex, trial_index: nextTrial });
        return;
      }

      const nextBlock = current.blockIndex + 1;
      if (nextBlock < current.blocks.length) {
        // Bloklar arasında mola: sonraki blok deneyi yürüten kişi başlatınca açılır.
        update({ ...current, phase: 'intro', blockIndex: nextBlock, trialIndex: 0, mismatch: false });
        return;
      }

      send({ type: 'study_end' });
      update({ ...current, phase: 'finished', mismatch: false });
    },
    [send, update],
  );

  const handleSpoken = useCallback(
    (text: string): SpokenResult => {
      const current = studyRef.current;
      if (current.phase !== 'trial') return null;
      const target = current.blocks[current.blockIndex]?.trials[current.trialIndex];
      if (!target) return null;
      if (sentencesMatch(text, target.text)) {
        finishTrial('done', text);
        return 'done';
      }
      update({ ...current, mismatch: true });
      return 'retry';
    },
    [finishTrial, update],
  );

  const skip = useCallback((output: string) => finishTrial('skipped', output), [finishTrial]);

  const block = study.phase === 'idle' ? null : (study.blocks[study.blockIndex] ?? null);
  const trial = study.phase === 'trial' ? (block?.trials[study.trialIndex] ?? null) : null;

  return { study, block, trial, start, beginBlock, handleSpoken, skip };
}
