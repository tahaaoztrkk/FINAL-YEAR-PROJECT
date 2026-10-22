/**
 * İstemci–sunucu mesaj sözleşmesi.
 *
 * Bu dosya backend'deki `schemas/messages.py` dosyasının aynasıdır.
 * Sözleşme değiştiğinde `python backend/scripts/export_schema.py` çalıştırılır
 * ve `messages.generated.ts` yeniden üretilir; bu dosya ise elle tutulan,
 * okunabilir arayüzü sağlar. İkisi arasında fark oluşursa üretilen dosya
 * doğrudur.
 */

export interface GazePoint {
  x: number;
  y: number;
  /** İstemci zaman damgası, saniye */
  t: number;
  confidence: number;
}

export type TargetKind = 'key' | 'group' | 'candidate' | 'action';

export interface GazeTarget {
  id: string;
  /** Sol kenar, 0–1 normalize */
  x: number;
  /** Üst kenar, 0–1 normalize */
  y: number;
  width: number;
  height: number;
  label: string;
  kind: TargetKind;
}

export interface Candidate {
  text: string;
  score: number;
  /** Adayın kısaltması girdiyle eşleşiyor mu */
  valid: boolean;
}

// --- İstemci -> Sunucu ----------------------------------------------------

export interface ClientHello {
  type: 'hello';
  screen_width: number;
  screen_height: number;
  participant_id?: string | null;
}

export interface ClientGazeSample {
  type: 'gaze';
  point: GazePoint;
}

export interface ClientCalibrationSample {
  type: 'calibration_sample';
  target_x: number;
  target_y: number;
  features: number[];
}

export interface ClientCalibrationFit {
  type: 'calibration_fit';
}

export interface ClientTargets {
  type: 'targets';
  targets: GazeTarget[];
}

export interface ClientSelect {
  type: 'select';
  target_id: string;
}

export interface ClientExpand {
  type: 'expand';
  abbreviation: string;
  scheme: string;
  context?: string | null;
  top_k: number;
}

export interface ClientSpeak {
  type: 'speak';
  text: string;
}

export type ClientMessage =
  | ClientHello
  | ClientGazeSample
  | ClientCalibrationSample
  | ClientCalibrationFit
  | ClientTargets
  | ClientSelect
  | ClientExpand
  | ClientSpeak;

// --- Sunucu -> İstemci ----------------------------------------------------

export interface ServerReady {
  type: 'ready';
  session_id: string;
  gaze_source: string;
  expander_provider: string;
  dwell_ms: number;
}

export interface ServerGaze {
  type: 'gaze';
  x: number;
  y: number;
  t: number;
}

export interface ServerDwellProgress {
  type: 'dwell_progress';
  target_id: string;
  progress: number;
}

export interface ServerSelection {
  type: 'selection';
  target_id: string;
  dwell_ms: number;
}

export interface ServerCalibrationResult {
  type: 'calibration_result';
  ok: boolean;
  sample_count: number;
  mean_error_px?: number | null;
  mean_error_deg?: number | null;
  message?: string | null;
}

export interface ServerCandidates {
  type: 'candidates';
  abbreviation: string;
  scheme: string;
  candidates: Candidate[];
  latency_ms: number;
}

export interface ServerError {
  type: 'error';
  code: string;
  detail: string;
}

export type ServerMessage =
  | ServerReady
  | ServerGaze
  | ServerDwellProgress
  | ServerSelection
  | ServerCalibrationResult
  | ServerCandidates
  | ServerError;
