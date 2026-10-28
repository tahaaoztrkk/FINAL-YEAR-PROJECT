/**
 * Uygulama kabuğu.
 *
 * Tüm durum burada toplanır ve bileşenlere aktarılır: klavye modu, girilen
 * kısaltma, seçilen şema ve söylenen cümleler. Bileşenlerin kendi durumu
 * yoktur, böylece deney sırasında her şey tek yerden kaydedilebilir.
 *
 * Kullanıcı testi `?deney` adresiyle açılır. Deneyde koşul plandan gelir:
 * A'da yalnızca harf harf yazılır (aday listesi ve 'Tamamla' yok), B'de
 * kısaltma planın şemasıyla girilir ve şema seçicisi kilitlenir.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { CandidateList } from '@/components/CandidateList';
import { GazeCursor } from '@/components/GazeCursor';
import { StatusBar } from '@/components/StatusBar';
import { StudyControls, StudyOverlay, StudyTarget } from '@/components/StudyPanel';
import { TargetTile } from '@/components/TargetTile';
import {
  GRID_TOP,
  LETTER_GROUPS,
  buildTargets,
  type KeyboardMode,
} from '@/features/keyboard/layout';
import { useStudy } from '@/features/study/useStudy';
import { useGazeSession } from '@/hooks/useGazeSession';
import { useGazeSource } from '@/hooks/useGazeSource';
import { speak } from '@/lib/speech';
import type { GazeTarget } from '@/types/messages';

export default function App() {
  const studyEnabled = useMemo(
    () => new URLSearchParams(window.location.search).has('deney'),
    [],
  );

  const [mode, setMode] = useState<KeyboardMode>('groups');
  const [activeGroup, setActiveGroup] = useState<number | null>(null);
  const [abbreviation, setAbbreviation] = useState('');
  const [scheme, setScheme] = useState('S1');
  const [spoken, setSpoken] = useState<string[]>([]);
  const [candidateTargets, setCandidateTargets] = useState<GazeTarget[]>([]);

  // Seçim işleyicisi, aday listesinin ve şemanın güncel değerine ihtiyaç
  // duyar ama bağımlılık listesine girerlerse WebSocket her değişimde
  // yeniden kurulur. Ref'ler bu ikisini ayırır.
  const candidatesRef = useRef<string[]>([]);
  const schemeRef = useRef(scheme);
  const lettersOnlyRef = useRef(false);
  const abbreviationRef = useRef(abbreviation);
  abbreviationRef.current = abbreviation;
  // 'Tamamla' seçimi dwell ile de gelir; o yol handleSelection'dan geçer
  // ve requestExpansion oradan görünmez. Ref köprüsü bunu bağlar.
  const expandRef = useRef<() => void>(() => {});
  // Seslendirmeden sonra yapılacaklar (sunucuya bildirmek, deneyi
  // ilerletmek) da useGazeSession'dan sonra tanımlanır. `true` dönerse
  // yazılan metin silinmez: deneyde yanlış cümle söylendi, katılımcı düzeltecek.
  const afterSpeakRef = useRef<(text: string) => boolean>(() => false);

  const resetComposer = useCallback(() => {
    setAbbreviation('');
    setMode('groups');
    setActiveGroup(null);
  }, []);

  const speakAndReset = useCallback(
    (text: string) => {
      speak(text);
      setSpoken((prev) => [text, ...prev].slice(0, 10));
      if (!afterSpeakRef.current(text)) resetComposer();
    },
    [resetComposer],
  );

  /** Hedef kimliğinin önekine göre dallanan tek seçim işleyicisi. */
  const handleSelection = useCallback(
    (targetId: string) => {
      const separator = targetId.indexOf(':');
      const kind = separator === -1 ? targetId : targetId.slice(0, separator);
      const value = separator === -1 ? '' : targetId.slice(separator + 1);

      switch (kind) {
        case 'group':
          setActiveGroup(Number(value));
          setMode('letters');
          return;

        case 'letter':
          setAbbreviation((prev) => prev + value);
          setActiveGroup(null);
          // S4'te her harften sonra ek sınıfı sorulur; diğer şemalarda ve
          // harf harf yazarken doğrudan gruplara dönülür.
          setMode(schemeRef.current === 'S4' && !lettersOnlyRef.current ? 'suffixes' : 'groups');
          return;

        case 'suffix':
          setAbbreviation((prev) => `${prev}-${value}`);
          setMode('groups');
          return;

        case 'candidate': {
          const text = candidatesRef.current[Number(value)];
          if (text) speakAndReset(text);
          return;
        }

        case 'action':
          if (value === 'space') {
            // Kelime sınırı. Arka arkaya iki boşluk eklenmez: kısaltma
            // normalleştirilirken yutulur ama ekranda karışıklık yaratır.
            setAbbreviation((prev) => (prev === '' || prev.endsWith(' ') ? prev : `${prev} `));
            return;
          }
          if (value === 'delete') {
            setAbbreviation((prev) => prev.replace(/-[A-Z0-9+]+$|.$/u, ''));
            return;
          }
          if (value === 'back') {
            setMode('groups');
            setActiveGroup(null);
            return;
          }
          if (value === 'speak') {
            // Aday yoksa yazılan metin okunur: harf harf yazan ya da
            // kelimeleri açık yazan kullanıcı da cümlesini söyleyebilsin.
            const text = candidatesRef.current[0] ?? abbreviationRef.current.trim();
            if (text) speakAndReset(text);
            return;
          }
          if (value === 'expand') {
            // Ref üzerinden: requestExpansion, handleSelection tanımlanırken
            // henüz yok (useGazeSession bu geri çağrıyı argüman alıyor).
            expandRef.current();
            return;
          }
          return;
      }
    },
    [speakAndReset],
  );

  const { state, send, sendTargets, sendGaze, requestExpansion, clearCandidates } =
    useGazeSession(handleSelection);

  const restartTrial = useCallback(() => {
    resetComposer();
    clearCandidates();
  }, [resetComposer, clearCandidates]);

  const { study, block, trial, start, beginBlock, handleSpoken, skip } = useStudy(
    send,
    state.studyPlan,
    state.sessionId,
    restartTrial,
  );

  const inStudy = study.phase !== 'idle';
  const condition = inStudy ? (block?.condition ?? null) : null;
  const lettersOnly = condition === 'A';
  const activeScheme = condition === 'B' && block ? block.scheme : scheme;
  schemeRef.current = activeScheme;
  lettersOnlyRef.current = lettersOnly;
  // Blok tanıtımında, molada ve bitişte hiçbir tuş seçilemez.
  const blocked = inStudy && study.phase !== 'trial';

  afterSpeakRef.current = (text: string) => {
    // Önce seslendirme kaydedilir, sonra deneme biter: sunucu kaydında
    // söylenen cümle o denemenin içinde kalmalı.
    send({ type: 'speak', text });
    if (handleSpoken(text) === 'retry') return true;
    clearCandidates();
    return false;
  };

  // 'Tamamla' seçimi burada yakalanır: requestExpansion henüz
  // handleSelection tanımlanırken mevcut değil.
  const handleExpand = useCallback(() => {
    if (lettersOnlyRef.current) return;
    const text = abbreviationRef.current.trim();
    if (text) requestExpansion(text, schemeRef.current);
  }, [requestExpansion]);

  expandRef.current = handleExpand;

  useGazeSource({
    kind: 'mouse',
    onSample: ({ x, y, t, confidence }) => sendGaze(x, y, t, confidence),
    enabled: state.connection === 'open',
  });

  const targets = useMemo(
    () => buildTargets(mode, activeGroup, { expand: !lettersOnly }),
    [mode, activeGroup, lettersOnly],
  );

  const validCandidates = useMemo(
    () => (lettersOnly ? [] : state.candidates.filter((candidate) => candidate.valid)),
    [state.candidates, lettersOnly],
  );

  candidatesRef.current = validCandidates.map((candidate) => candidate.text);

  // Ekran düzeni her değiştiğinde sunucudaki dwell hedefleri de değişmeli;
  // ayrışırlarsa kullanıcı bir yere bakar, başka yer seçilir. Yeniden
  // bağlanınca (yeni oturum) sunucu hedefleri bilmez, yine gönderilir.
  useEffect(() => {
    if (blocked) {
      sendTargets([]);
      return;
    }
    sendTargets([...targets, ...(lettersOnly ? [] : candidateTargets)]);
  }, [targets, candidateTargets, lettersOnly, blocked, sendTargets, state.sessionId]);

  // Tıklama doğrudan işlenmez, sunucuya gönderilir: sunucu dwell'e kilit
  // koyar ve seçimi geri yollar. Böylece tıklama ile dwell aynı tuşu iki
  // kez seçmez ve her seçim tek yoldan (handleSelection) geçer.
  const handleTileClick = useCallback(
    (targetId: string) => {
      if (!blocked) send({ type: 'select', target_id: targetId });
    },
    [send, blocked],
  );

  const handleBeginBlock = useCallback(() => {
    restartTrial();
    beginBlock();
  }, [restartTrial, beginBlock]);

  const handleSkip = useCallback(() => {
    skip(abbreviationRef.current.trim());
    restartTrial();
  }, [skip, restartTrial]);

  return (
    <div className="app">
      <div className="top" style={{ height: `calc(${GRID_TOP * 100}% - 8px)` }}>
        <StatusBar
          state={state}
          scheme={activeScheme}
          onSchemeChange={setScheme}
          schemeLocked={condition !== null}
        >
          {studyEnabled && (
            <StudyControls
              study={study}
              block={block}
              connected={state.connection === 'open'}
              error={state.lastError}
              onStart={start}
              onSkip={handleSkip}
            />
          )}
        </StatusBar>

        {block && trial && <StudyTarget study={study} block={block} trial={trial} />}

        <section className="composer">
          <p className="composer__label">{lettersOnly ? 'Metin' : 'Kısaltma'}</p>
          <p className="composer__value">{abbreviation || '—'}</p>
          <p className="composer__hint">
            {mode === 'groups' &&
              (lettersOnly
                ? 'Harf grubuna bakın · kelime bitince Boşluk · cümle bitince Seslendir'
                : 'Harf grubuna bakın · kelime bitince Boşluk')}
            {mode === 'letters' &&
              activeGroup !== null &&
              `Grup: ${LETTER_GROUPS[activeGroup]?.join(' ')}`}
            {mode === 'suffixes' && 'Bu kelimenin eki hangisi?'}
          </p>
        </section>

        {!lettersOnly && (
          <CandidateList
            candidates={state.candidates}
            dwellTargetId={state.dwellTargetId}
            dwellProgress={state.dwellProgress}
            latencyMs={state.lastLatencyMs}
            noResult={
              validCandidates.length === 0 &&
              abbreviation.trim() !== '' &&
              state.candidatesFor === abbreviation.trim()
            }
            onSelect={handleTileClick}
            onTargetsChange={setCandidateTargets}
          />
        )}
      </div>

      <main className="keyboard">
        {targets.map((target) => (
          <TargetTile
            key={target.id}
            target={target}
            progress={state.dwellTargetId === target.id ? state.dwellProgress : 0}
            active={state.dwellTargetId === target.id}
            onClick={handleTileClick}
          />
        ))}
      </main>

      {!inStudy && spoken.length > 0 && (
        <aside className="history" aria-label="Söylenen cümleler">
          {spoken.map((text, index) => (
            <button key={`${text}-${index}`} type="button" onClick={() => speak(text)}>
              {text}
            </button>
          ))}
        </aside>
      )}

      <StudyOverlay study={study} block={block} onBegin={handleBeginBlock} />

      <GazeCursor position={state.gaze} />

      {!inStudy && (
        <p className="devnote">
          Geliştirme modu: fare imleci bakış yerine geçiyor. Tuşların üstünde{' '}
          {state.dwellMs} ms bekleyin ya da doğrudan tıklayın.
        </p>
      )}
    </div>
  );
}
