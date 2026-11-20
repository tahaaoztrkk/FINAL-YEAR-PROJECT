/**
 * Kamera akışını açma.
 *
 * Görüntü yalnızca bellekte işlenir: hiçbir kare kaydedilmez ya da sunucuya
 * gönderilmez (docs/architecture.md, "Gizlilik"). Bu dosya akışı açar ve
 * kapatır, başka bir şey yapmaz.
 */

export class CameraError extends Error {
  constructor(
    message: string,
    readonly code: 'denied' | 'not_found' | 'busy' | 'insecure' | 'unknown',
  ) {
    super(message);
    this.name = 'CameraError';
  }
}

/**
 * 640x480 yeterli: iris yarıçapı bu çözünürlükte ~8-12 px ve FaceLandmarker
 * görüntüyü zaten 256x256'ya küçültür. Daha yüksek çözünürlük yalnızca kare
 * kopyalama süresini artırır.
 */
const VIDEO_CONSTRAINTS: MediaTrackConstraints = {
  facingMode: 'user',
  width: { ideal: 640 },
  height: { ideal: 480 },
  frameRate: { ideal: 30 },
};

export async function openCamera(video: HTMLVideoElement): Promise<MediaStream> {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    throw new CameraError(
      'Kamera yalnızca güvenli bağlamda açılır: sayfayı localhost ya da https üzerinden açın.',
      'insecure',
    );
  }

  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: VIDEO_CONSTRAINTS, audio: false });
  } catch (error) {
    const name = error instanceof DOMException ? error.name : '';
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      throw new CameraError(
        'Kamera izni verilmedi. Adres çubuğundaki kamera simgesinden izin verip sayfayı yenileyin.',
        'denied',
      );
    }
    if (name === 'NotFoundError' || name === 'OverconstrainedError') {
      throw new CameraError('Bağlı bir kamera bulunamadı.', 'not_found');
    }
    if (name === 'NotReadableError' || name === 'AbortError') {
      throw new CameraError(
        'Kamera başka bir uygulama tarafından kullanılıyor (Zoom, Teams, başka bir sekme).',
        'busy',
      );
    }
    throw new CameraError(`Kamera açılamadı: ${String(error)}`, 'unknown');
  }

  video.srcObject = stream;
  video.muted = true;
  video.playsInline = true;
  await video.play();
  return stream;
}

export function closeCamera(video: HTMLVideoElement | null, stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
  if (video) video.srcObject = null;
}
