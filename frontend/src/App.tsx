/**
 * Uygulama kabuğu.
 *
 * Tüm durum burada toplanır ve bileşenlere aktarılır: klavye modu, girilen
 * kısaltma, seçilen şema ve söylenen cümleler. Bileşenlerin kendi durumu
 * yoktur, böylece deney sırasında her şey tek yerden kaydedilebilir.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { CandidateList } from '@/components/CandidateList';
import { GazeCursor } from '@/components/GazeCursor';
import { StatusBar } from '@/components/StatusBar';
import { TargetTile } from '@/components/TargetTile';
import {
  LETTER_GROUPS,
  buildCandidateTargets,
  buildTargets,
  type KeyboardMode,
} from '@/features/keyboard/layout';
import { useGazeSession } from '@/hooks/useGazeSession';
import { useGazeSource } from '@/hooks/useGazeSource';
import { speak } from '@/lib/speech';

export default function App() {
  const [mode, setMode] = useState<KeyboardMode>('groups');
  const [activeGroup, setActiveGroup] = useState<number | null>(null);
  const [abbreviation, setAbbreviation] = useState('');
  const [scheme, setScheme] = useState('S1');
  const [spoken, setSpoken] = useState<string[]>([]);

  // Seçim işleyicisi, aday listesinin ve şemanın güncel değerine ihtiyaç
  // duyar ama bağımlılık listesine girerlerse WebSocket her değişimde
  // yeniden kurulur. Ref'ler bu ikisini ayırır.
  const candidatesRef = useRef<string[]>([]);
  const schemeRef = useRef(scheme);
  schemeRef.current = scheme;
  const abbreviationRef = useRef(abbreviation);
  abbreviationRef.current = abbreviation;
  // 'Tamamla' seçimi dwell ile de gelir; o yol handleSelection'dan geçer
  // ve requestExpansion oradan görünmez. Ref köprüsü bunu bağlar.
  const expandRef = useRef<() => void>(() => {});

  const speakAndReset = useCallback((text: string) => {
    speak(text);
    setSpoken((prev) => [text, ...prev].slice(0, 10));
    setAbbreviation('');
    setMode('groups');
    setActiveGroup(null);
  }, []);

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
          // S4'te her harften sonra ek sınıfı sorulur; diğer şemalarda
          // doğrudan gruplara dönülür.
          setMode(schemeRef.current === 'S4' ? 'suffixes' : 'groups');
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
            const first = candidatesRef.current[0];
            if (first) speakAndReset(first);
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

  const { state, send, sendTargets, sendGaze, requestExpansion } =
    useGazeSession(handleSelection);

  // 'Tamamla' seçimi burada yakalanır: requestExpansion henüz
  // handleSelection tanımlanırken mevcut değil.
  const handleExpand = useCallback(() => {
    const text = abbreviationRef.current.trim();
    if (text) requestExpansion(text, schemeRef.current);
  }, [requestExpansion]);

  expandRef.current = handleExpand;

  useGazeSource({
    kind: 'mouse',
    onSample: ({ x, y, t, confidence }) => sendGaze(x, y, t, confidence),
    enabled: state.connection === 'open',
  });

  const targets = useMemo(() => buildTargets(mode, activeGroup), [mode, activeGroup]);

  const validCandidates = useMemo(
    () => state.candidates.filter((candidate) => candidate.valid),
    [state.candidates],
  );

  candidatesRef.current = validCandidates.map((candidate) => candidate.text);

  // Ekran düzeni her değiştiğinde sunucudaki dwell hedefleri de değişmeli;
  // ayrışırlarsa kullanıcı bir yere bakar, başka yer seçilir.
  useEffect(() => {
    sendTargets([...targets, ...buildCandidateTargets(validCandidates.length)]);
  }, [targets, validCandidates.length, sendTargets]);

  const handleSpeak = useCallback(
    (text: string) => {
      send({ type: 'speak', text });
      speakAndReset(text);
    },
    [send, speakAndReset],
  );

  // Tıklama doğrudan işlenmez, sunucuya gönderilir: sunucu dwell'e kilit
  // koyar ve seçimi geri yollar. Böylece tıklama ile dwell aynı tuşu iki
  // kez seçmez ve her seçim tek yoldan (handleSelection) geçer.
  const handleTileClick = useCallback(
    (targetId: string) => send({ type: 'select', target_id: targetId }),
    [send],
  );

  return (
    <div className="app">
      <StatusBar state={state} scheme={scheme} onSchemeChange={setScheme} />

      <section className="composer">
        <p className="composer__label">Kısaltma</p>
        <p className="composer__value">{abbreviation || '—'}</p>
        <p className="composer__hint">
          {mode === 'groups' && 'Harf grubuna bakın · kelime bitince Boşluk'}
          {mode === 'letters' &&
            activeGroup !== null &&
            `Grup: ${LETTER_GROUPS[activeGroup]?.join(' ')}`}
          {mode === 'suffixes' && 'Bu kelimenin eki hangisi?'}
        </p>
      </section>

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
        onSelect={handleSpeak}
      />

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

      {spoken.length > 0 && (
        <aside className="history" aria-label="Söylenen cümleler">
          {spoken.map((text, index) => (
            <button key={`${text}-${index}`} type="button" onClick={() => speak(text)}>
              {text}
            </button>
          ))}
        </aside>
      )}

      <GazeCursor position={state.gaze} />

      <p className="devnote">
        Geliştirme modu: fare imleci bakış yerine geçiyor. Tuşların üstünde{' '}
        {state.dwellMs} ms bekleyin ya da doğrudan tıklayın.
      </p>
    </div>
  );
}
