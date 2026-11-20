/**
 * Tarayıcıda MediaPipe FaceLandmarker.
 *
 * backend/src/gaze_aac/gaze/landmarks.py ile aynı modeli ve aynı ayarları
 * kullanır: tek yüz, video modu, blendshape ve dönüşüm matrisi kapalı. Böylece
 * tarayıcıdaki 478 nokta Python tarafındakiyle aynı anlama gelir ve
 * features.py tarayıcıya birebir taşınabilir.
 *
 * Wasm dosyaları paketin kendisinden sunulur (vite.config.ts, mediapipeWasm):
 * CDN'den gelseydi npm sürümüyle wasm sürümü ayrışabilirdi.
 */

import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision';

/** Python tarafındaki ``MODEL_URL`` ile aynı dosya. */
const DEFAULT_MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';

export const WASM_BASE_PATH = '/mediapipe/wasm';

/** İris noktaları dahil, MediaPipe FaceLandmarker çıktısının nokta sayısı. */
export const LANDMARK_COUNT = 478;

export type Delegate = 'GPU' | 'CPU';

export interface LoadedLandmarker {
  landmarker: FaceLandmarker;
  delegate: Delegate;
}

function modelUrl(): string {
  const fromEnv = import.meta.env.VITE_FACE_LANDMARKER_MODEL as string | undefined;
  return fromEnv && fromEnv.trim() !== '' ? fromEnv.trim() : DEFAULT_MODEL_URL;
}

/**
 * Önce GPU ile dener; WebGL yoksa ya da sürücü sorunluysa CPU'ya düşer.
 * Hangisiyle çalıştığı döndürülür çünkü gecikme ölçümü buna bağlı.
 */
export async function loadLandmarker(): Promise<LoadedLandmarker> {
  const fileset = await FilesetResolver.forVisionTasks(WASM_BASE_PATH);
  const url = modelUrl();

  let lastError: unknown = null;
  for (const delegate of ['GPU', 'CPU'] as const) {
    try {
      const landmarker = await FaceLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: url, delegate },
        runningMode: 'VIDEO',
        numFaces: 1,
        outputFaceBlendshapes: false,
        outputFacialTransformationMatrixes: false,
      });
      return { landmarker, delegate };
    } catch (error) {
      lastError = error;
      console.warn(`FaceLandmarker ${delegate} ile açılamadı`, error);
    }
  }
  // MediaPipe'ın hata metni adresi zaten içeriyor; tekrar yazmıyoruz.
  const detail = lastError instanceof Error ? lastError.message : String(lastError);
  throw new Error(
    `Yüz modeli yüklenemedi. ${detail}. İnternet yoksa modeli frontend/public/ altına koyup ` +
      'VITE_FACE_LANDMARKER_MODEL ayarını kullanın.',
  );
}
