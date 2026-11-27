/**
 * Kamera modunda kalibrasyon ekranı ve canlı bakış uyarısı.
 *
 * Kalibrasyon tam ekran yapılır; klavye de aynı pencere boyutunda kullanılmalı
 * (K4d). Akış ?bakis ile aynı: baş sabitken 9 nokta, sonra dört baş pozunda
 * beşer nokta. Doğrulama noktaları ve derece cinsinden hata ayrı bir adımda
 * eklenecek (Görev 2).
 *
 * İmleç durduğunda nedeni yazılır: sessizce donmak en kötüsü.
 */

import type { HoldReason } from '@/features/gaze/browserGaze';
import type { WebcamGaze } from '@/features/gaze/useWebcamGaze';

interface Props {
  gaze: WebcamGaze;
}

function trackingText(gaze: WebcamGaze): string {
  const { status } = gaze;
  if (status.state === 'running') return `Kamera hazır (${status.delegate}).`;
  if (status.state === 'error') return status.message;
  if (status.state === 'loading') return `${status.step}…`;
  return 'Kamera bekleniyor…';
}

export function CalibrationScreen({ gaze }: Props) {
  const { phase, view } = gaze;
  if (phase === 'off' || phase === 'live') return null;

  if (phase === 'needs_calibration') {
    const ready = gaze.status.state === 'running';
    return (
      <div className="calibration calibration--setup">
        <h2>Kalibrasyon</h2>
        <p>
          Yaklaşık 75 saniye sürer. Önce başın sabitken dokuz noktaya bakacaksın, sonra yazının
          istediği gibi başını hafifçe çevirip beşer noktaya. Nokta yeşilken bakmaya devam et.
        </p>
        <p className={gaze.status.state === 'error' ? 'calibration__error' : 'calibration__dim'}>
          {trackingText(gaze)}
        </p>
        {gaze.message && <p className="calibration__error">{gaze.message}</p>}
        <button type="button" disabled={!ready} onClick={gaze.calibrate}>
          Kalibrasyonu başlat
        </button>
      </div>
    );
  }

  const point = view?.point ?? null;
  return (
    <div className="calibration">
      {view?.pose && (
        <div className="calibration__pose">
          <h2>
            Başını hafifçe <strong>{view.pose}</strong> çevir.
          </h2>
          <p>
            {view.poseReady
              ? 'Tamam, böyle kal…'
              : view.poseWrongWay
                ? 'Ters yöne döndün, diğer tarafa çevir.'
                : 'Yeterince dönünce çubuk dolar ve kendiliğinden devam eder.'}
          </p>
          <div className="calibration__meter" aria-hidden="true">
            <div style={{ width: `${(view.poseProgress ?? 0) * 100}%` }} />
          </div>
        </div>
      )}

      {phase === 'recentering' && !point && <h2 className="calibration__hint">Noktalara bak.</h2>}

      {point && (
        <div
          className={`calibration__dot${view?.collecting ? ' calibration__dot--collecting' : ''}`}
          style={{ left: `${point[0] * 100}%`, top: `${point[1] * 100}%` }}
          aria-hidden="true"
        />
      )}

      <p className="calibration__footer">
        {phase === 'recentering' ? 'Ortalama' : 'Kalibrasyon'} · adım {view?.step ?? 0}/
        {view?.totalSteps ?? 0} · Esc: iptal
      </p>
    </div>
  );
}

const HOLD_TEXT: Record<HoldReason, string> = {
  no_face: 'Yüzün bulunamıyor: kameranın görüş alanına gel.',
  blink: 'Gözlerin kapalı görünüyor.',
  head: 'Başın kalibrasyondaki konumdan uzaklaştı: biraz geri getir ya da Boşluk ile ortala.',
  window: 'Pencere boyutu kalibrasyondakinden farklı: tam ekrana dön ya da yeniden kalibre et.',
};

export function GazeHoldBanner({ gaze }: Props) {
  if (gaze.phase !== 'live' || !gaze.hold) return null;
  return (
    <div className="gaze-hold" role="status">
      <span>{HOLD_TEXT[gaze.hold]}</span>
      {gaze.hold === 'window' && (
        <button
          type="button"
          onClick={() => void document.documentElement.requestFullscreen().catch(() => undefined)}
        >
          Tam ekran
        </button>
      )}
    </div>
  );
}
