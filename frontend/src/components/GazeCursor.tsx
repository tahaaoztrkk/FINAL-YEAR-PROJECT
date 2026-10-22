/**
 * Yumuşatılmış bakış konumunu gösteren imleç.
 *
 * Kullanıcı nereye baktığını görmeden sistemin hata yapıp yapmadığını
 * anlayamaz; kalibrasyon sapmasını fark etmenin en hızlı yolu budur.
 */

interface Props {
  position: { x: number; y: number } | null;
}

export function GazeCursor({ position }: Props) {
  if (!position) return null;

  return (
    <div
      className="gaze-cursor"
      style={{ left: `${position.x * 100}%`, top: `${position.y * 100}%` }}
      aria-hidden="true"
    />
  );
}
