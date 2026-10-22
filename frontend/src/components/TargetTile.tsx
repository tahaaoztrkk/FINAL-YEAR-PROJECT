/**
 * Tek bir bakış hedefi.
 *
 * Erişilebilirlik kuralları burada somutlaşıyor: yazı en az 32 piksel,
 * yüksek kontrast, animasyon 300 ms altında, yanıp sönme yok. Üçü de göz
 * takibi arayüzlerinde yorgunluk ve hata kaynağı.
 */

import type { GazeTarget } from '@/types/messages';

interface Props {
  target: GazeTarget;
  progress: number;
  active: boolean;
  onClick?: (targetId: string) => void;
}

export function TargetTile({ target, progress, active, onClick }: Props) {
  const style: React.CSSProperties = {
    left: `${target.x * 100}%`,
    top: `${target.y * 100}%`,
    width: `${target.width * 100}%`,
    height: `${target.height * 100}%`,
  };

  return (
    <button
      type="button"
      className={`tile tile--${target.kind}${active ? ' tile--active' : ''}`}
      style={style}
      onClick={() => onClick?.(target.id)}
      aria-label={target.label}
    >
      {/* Dwell halkası: kullanıcı ilerlemeyi görür ve bakışını çekerek iptal edebilir */}
      {active && progress > 0 && <DwellRing progress={progress} />}
      <span className="tile__label">{target.label}</span>
    </button>
  );
}

function DwellRing({ progress }: { progress: number }) {
  const radius = 26;
  const circumference = 2 * Math.PI * radius;

  return (
    <svg className="dwell-ring" viewBox="0 0 64 64" aria-hidden="true">
      <circle className="dwell-ring__track" cx="32" cy="32" r={radius} />
      <circle
        className="dwell-ring__fill"
        cx="32"
        cy="32"
        r={radius}
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - progress)}
      />
    </svg>
  );
}
