// BU DOSYA ÜRETİLMİŞTİR — ELLE DÜZENLEMEYİN.
// Kaynak: backend/src/gaze_aac/schemas/messages.py
// Yeniden üretmek için: python backend/scripts/export_schema.py

export interface Candidate {
  text: string;
  /** Sağlayıcının güven puanı; karşılaştırma için sıralama anahtarı */
  score?: number;
  /** Adayın kısaltması girdiyle eşleşiyor mu (geri kontrol sonucu) */
  valid?: boolean;
}

export interface GazePoint {
  x: number;
  y: number;
  /** İstemci zaman damgası, saniye */
  t: number;
  confidence?: number;
}

export interface GazeTarget {
  id: string;
  /** Sol kenar */
  x: number;
  /** Üst kenar */
  y: number;
  width: number;
  height: number;
  label?: string;
  /** key | group | candidate | action */
  kind?: string;
}

export interface ClientHello {
  type?: "hello";
  /** Ekran genişliği, piksel */
  screen_width: number;
  /** Ekran yüksekliği, piksel */
  screen_height: number;
  /** Deney oturumlarında katılımcı kodu (ör. P07) */
  participant_id?: string | null;
}

export interface ClientGazeSample {
  type?: "gaze";
  point: GazePoint;
}

export interface ClientCalibrationSample {
  type?: "calibration_sample";
  /** Hedefin normalize x konumu */
  target_x: number;
  /** Hedefin normalize y konumu */
  target_y: number;
  /** Göz/baş öznitelik vektörü */
  features: number[];
}

export interface ClientCalibrationFit {
  type?: "calibration_fit";
}

export interface ClientTargets {
  type?: "targets";
  targets: GazeTarget[];
}

export interface ClientSelect {
  type?: "select";
  target_id: string;
}

export interface ClientExpand {
  type?: "expand";
  /** Kullanıcının girdiği kısaltma */
  abbreviation: string;
  /** Kısaltma şeması kimliği */
  scheme?: string;
  /** Karşı tarafın son cümlesi, varsa */
  context?: string | null;
  top_k?: number;
}

export interface ClientSpeak {
  type?: "speak";
  text: string;
}

export interface ServerReady {
  type?: "ready";
  session_id: string;
  gaze_source: string;
  expander_provider: string;
  dwell_ms: number;
}

export interface ServerGaze {
  type?: "gaze";
  x: number;
  y: number;
  /** Örneğin zaman damgası, saniye */
  t: number;
}

export interface ServerDwellProgress {
  type?: "dwell_progress";
  target_id: string;
  progress: number;
}

export interface ServerSelection {
  type?: "selection";
  target_id: string;
  /** Seçimin gerçekte ne kadar sürdüğü */
  dwell_ms: number;
}

export interface ServerCalibrationResult {
  type?: "calibration_result";
  ok: boolean;
  sample_count: number;
  mean_error_px?: number | null;
  mean_error_deg?: number | null;
  message?: string | null;
}

export interface ServerCandidates {
  type?: "candidates";
  abbreviation: string;
  scheme: string;
  candidates: Candidate[];
  latency_ms: number;
}

export interface ServerError {
  type?: "error";
  code: string;
  detail: string;
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

export type ServerMessage =
  | ServerReady
  | ServerGaze
  | ServerDwellProgress
  | ServerSelection
  | ServerCalibrationResult
  | ServerCandidates
  | ServerError;
