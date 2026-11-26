/**
 * Yumuşatılmış bakış konumunu gösteren imleç.
 *
 * Kullanıcı nereye baktığını görmeden sistemin hata yapıp yapmadığını
 * anlayamaz; kalibrasyon sapmasını fark etmenin en hızlı yolu budur.
 */

interface Props {
  position: { x: number; y: number } | null;
  /** Kamera modunda bakış durdu (kırpış, baş, yüz yok): imleç soluklaşır. */
  held?: boolean;
}

export function GazeCursor({ position, held = false }: Props) {
  if (!position) return null;

  return (
    <div
      className={held ? 'gaze-cursor gaze-cursor--held' : 'gaze-cursor'}
      style={{ left: `${position.x * 100}%`, top: `${position.y * 100}%` }}
      aria-hidden="true"
    />
  );
}
