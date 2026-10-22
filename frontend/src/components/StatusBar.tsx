/**
 * Bağlantı ve yapılandırma durumu.
 *
 * Deney oturumlarında hangi sağlayıcının ve hangi dwell süresinin aktif
 * olduğunu görmek gerekir: yanlış koşulda toplanan veri sonradan fark
 * edilirse oturum tekrarlanır.
 */

import type { SessionState } from '@/hooks/useGazeSession';

interface Props {
  state: SessionState;
  scheme: string;
  onSchemeChange: (scheme: string) => void;
}

const SCHEMES = [
  { id: 'S1', label: 'S1 · baş harf' },
  { id: 'S2', label: 'S2 · ilk iki harf' },
  { id: 'S3', label: 'S3 · baş + son' },
  { id: 'S4', label: 'S4 · ek işaretli' },
];

export function StatusBar({ state, scheme, onSchemeChange }: Props) {
  return (
    <header className="status">
      <span className={`status__dot status__dot--${state.connection}`} aria-hidden="true" />
      <span className="status__item">
        {state.connection === 'open' ? 'bağlı' : 'bağlanıyor'}
      </span>
      <span className="status__item">bakış: {state.gazeSource ?? '—'}</span>
      <span className="status__item">model: {state.expanderProvider ?? '—'}</span>
      <span className="status__item">dwell: {state.dwellMs} ms</span>
      {state.calibrationErrorDeg !== null && (
        <span className="status__item">hata: {state.calibrationErrorDeg.toFixed(2)}°</span>
      )}
      <label className="status__scheme">
        şema
        <select value={scheme} onChange={(event) => onSchemeChange(event.target.value)}>
          {SCHEMES.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      {state.lastError && <span className="status__error">{state.lastError}</span>}
    </header>
  );
}
