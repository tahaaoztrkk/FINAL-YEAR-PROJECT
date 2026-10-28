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

export interface StudyBlock {
  /** A: harf harf, B: kısaltma ve aday listesi */
  condition: string;
  /** B koşulunda kullanılan kısaltma şeması */
  scheme: string;
  trials: StudyTrial[];
}

export interface StudyTrial {
  /** Blok içindeki sıra */
  index: number;
  /** Hedef cümle */
  text: string;
  /** Alıştırma cümlesi mi; analize girmez */
  practice: boolean;
}

export interface ClientHello {
  type?: "hello";
  /** Ekran genişliği, piksel */
  screen_width: number;
  /** Ekran yüksekliği, piksel */
  screen_height: number;
  /** Deney oturumlarında katılımcı kodu (ör. K07) */
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

export interface ClientStudyStart {
  type?: "study_start";
  /** Katılımcı kodu (ör. K07) */
  participant_id: string;
}

export interface ClientTrialStart {
  type?: "trial_start";
  block_index: number;
  trial_index: number;
}

export interface ClientTrialEnd {
  type?: "trial_end";
  block_index: number;
  trial_index: number;
  outcome: string;
  /** Katılımcının son ürettiği metin */
  output?: string;
}

export interface ClientStudyEnd {
  type?: "study_end";
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

export interface ServerStudyPlan {
  type?: "study_plan";
  /** Tek biçime getirilmiş kod (k7 -> K07) */
  participant_id: string;
  /** Koşul sırası, AB ya da BA */
  order: string;
  blocks: StudyBlock[];
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
  | ClientSpeak
  | ClientStudyStart
  | ClientTrialStart
  | ClientTrialEnd
  | ClientStudyEnd;

export type ServerMessage =
  | ServerReady
  | ServerGaze
  | ServerDwellProgress
  | ServerSelection
  | ServerCalibrationResult
  | ServerCandidates
  | ServerStudyPlan
  | ServerError;
