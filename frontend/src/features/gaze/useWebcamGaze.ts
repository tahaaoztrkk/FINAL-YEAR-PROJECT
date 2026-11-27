/**
 * Ana uygulamada kamerayla bakış: kamera + kalibrasyon akışı + canlı tahmin.
 *
 * Kare başına bir kez çalışır (useFaceTracking). Canlıdayken tahmin edilen
 * nokta `onSample` ile dışarı verilir; App onu mevcut `gaze` mesajıyla sunucuya
 * yollar, sunucudaki yumuşatma ve dwell olduğu gibi çalışır (K1-a).
 *
 * Kırpışta, yüz yokken, baş kalibrasyon aralığının dışındayken ya da pencere
 * boyutu değişmişken hiçbir şey gönderilmez: imleç yerinde kalır, dwell
 * ilerlemez ve neden `hold` ile ekrana yazılır.
 *
 * KVKK: görüntü ve landmark'lar bu dosyadan dışarı çıkmaz; dışarı yalnızca
 * ekran koordinatı verilir.
 */

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

import {
  BrowserGazeModel,
  CALIBRATION_GRID,
  HEAD_POSES,
  HEAD_POSE_POINTS,
  MIN_CONFIDENCE,
  POSE_AXIS,
  PoseWatcher,
  RECENTER_POINTS,
  median,
  type HoldReason,
  type Point,
} from './browserGaze';
import { PITCH, YAW, irisFeatures, type GazeSample } from './gazeLinear';
import { useFaceTracking, type FaceFrame, type TrackingStatus } from './useFaceTracking';

// Zamanlamalar GazeLive.tsx ile aynı.
const PREP_MS = 600;
const DISCARD_MS = 300;
const HOLD_MS = 1200;
const START_DELAY_MS = 800;
const POSE_READ_DELAY_MS = 600;
const POSE_CONFIRM_TIMEOUT_MS = 8000;
const POSE_SETTLE_MS = 500;
/** Bu kadar kare üst üste göz kapalıysa uyarı çıkar (~0,5 sn); tek kırpış sessizce atlanır. */
const CLOSED_WARNING_FRAMES = 15;

export type WebcamPhase = 'off' | 'needs_calibration' | 'calibrating' | 'recentering' | 'live';

/** Kalibrasyon ekranının çizeceği her şey. */
export interface CalibrationView {
  /** Bakılacak nokta (0–1); poz komutu sırasında `null`. */
  point: Point | null;
  /** Örnek toplanıyor mu (nokta yeşil). */
  collecting: boolean;
  /** Baş pozu komutu, ör. "sağa". */
  pose: string | null;
  poseProgress: number;
  poseWrongWay: boolean;
  poseReady: boolean;
  /** İlerleme: kaçıncı adım / toplam. */
  step: number;
  totalSteps: number;
}

export interface WebcamGaze {
  videoRef: RefObject<HTMLVideoElement>;
  status: TrackingStatus;
  phase: WebcamPhase;
  view: CalibrationView | null;
  hold: HoldReason | null;
  /** Son kalibrasyon başarısızsa nedeni. */
  message: string | null;
  sampleCount: number | null;
  calibrate: () => void;
  recenter: () => void;
  cancel: () => void;
}

export interface RawGazeSample {
  x: number;
  y: number;
  t: number;
  confidence: number;
}

interface Options {
  /** Kamera açık mı. */
  enabled: boolean;
  /** Örnek gönderilsin mi (ör. bağlantı açıkken). */
  sending: boolean;
  onSample: (sample: RawGazeSample) => void;
}

const TOTAL_STEPS = CALIBRATION_GRID.length + HEAD_POSES.length * (HEAD_POSE_POINTS.length + 1);

class Cancelled extends Error {}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function shuffled<T>(items: readonly T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j] as T, copy[i] as T];
  }
  return copy;
}

function currentWindow() {
  return { width: window.innerWidth, height: window.innerHeight };
}

export function useWebcamGaze({ enabled, sending, onSample }: Options): WebcamGaze {
  const [phase, setPhase] = useState<WebcamPhase>(enabled ? 'needs_calibration' : 'off');
  const [view, setView] = useState<CalibrationView | null>(null);
  const [hold, setHold] = useState<HoldReason | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [sampleCount, setSampleCount] = useState<number | null>(null);

  const onSampleRef = useRef(onSample);
  onSampleRef.current = onSample;
  const sendingRef = useRef(sending);
  sendingRef.current = sending;

  const modelRef = useRef<BrowserGazeModel | null>(null);
  const liveRef = useRef(false);
  const busyRef = useRef(false);
  const runRef = useRef(0);
  const collectRef = useRef<{ target: Point; samples: GazeSample[] } | null>(null);
  const poseRef = useRef<PoseWatcher | null>(null);
  const holdRef = useRef<HoldReason | null>(null);
  const closedFramesRef = useRef(0);

  const setHoldOnce = (reason: HoldReason | null) => {
    if (holdRef.current === reason) return;
    holdRef.current = reason;
    setHold(reason);
  };

  // Her karede React durumu güncellenmez; yalnızca değişen şeyler (bekleme
  // nedeni, poz çubuğu) durum olur.
  const onFrame = useCallback((frame: FaceFrame) => {
    const features = frame.landmarks ? irisFeatures(frame.landmarks) : null;

    if (features && features.confidence >= MIN_CONFIDENCE) {
      const collect = collectRef.current;
      if (collect) {
        collect.samples.push({
          features: features.values,
          x: collect.target[0],
          y: collect.target[1],
        });
      }
      const pose = poseRef.current;
      if (pose) {
        const update = pose.update(features.values);
        setView((prev) => {
          if (!prev) return prev;
          const progress = Math.round(update.progress * 20) / 20;
          if (
            prev.poseProgress === progress &&
            prev.poseWrongWay === update.wrongWay &&
            prev.poseReady === update.ready
          ) {
            return prev;
          }
          return {
            ...prev,
            poseProgress: progress,
            poseWrongWay: update.wrongWay,
            poseReady: update.ready,
          };
        });
      }
    }

    const model = modelRef.current;
    if (!model || !liveRef.current) return;

    const estimate = model.estimate(features?.values ?? null, currentWindow());
    if (estimate.kind === 'hold') {
      if (estimate.reason === 'blink') {
        closedFramesRef.current += 1;
        if (closedFramesRef.current >= CLOSED_WARNING_FRAMES) setHoldOnce('blink');
      } else {
        closedFramesRef.current = 0;
        setHoldOnce(estimate.reason);
      }
      return;
    }
    closedFramesRef.current = 0;
    setHoldOnce(null);
    if (!sendingRef.current) return;
    onSampleRef.current({
      x: estimate.x,
      y: estimate.y,
      t: frame.t,
      confidence: features?.confidence ?? 1,
    });
  }, []);

  const tracking = useFaceTracking({ enabled, onFrame });
  const { status, videoRef } = tracking;

  // 10 Kasım ölçümlerinde en düşük hata 1280x720'de çıktı (GazeLive ile aynı).
  useEffect(() => {
    if (status.state !== 'running') return;
    const stream = videoRef.current?.srcObject as MediaStream | null;
    stream
      ?.getVideoTracks()[0]
      ?.applyConstraints({ width: { ideal: 1280 }, height: { ideal: 720 } })
      .catch((error: unknown) => console.warn('Çözünürlük değiştirilemedi', error));
  }, [status.state, videoRef]);

  useEffect(() => {
    if (enabled) {
      setPhase((prev) => (prev === 'off' ? 'needs_calibration' : prev));
      return;
    }
    runRef.current += 1;
    liveRef.current = false;
    modelRef.current = null;
    collectRef.current = null;
    poseRef.current = null;
    busyRef.current = false;
    setView(null);
    setHoldOnce(null);
    setPhase('off');
  }, [enabled]);

  /** İptal edildiyse (yeni kalibrasyon, Esc, kamera kapandı) akışı keser. */
  const guard = (run: number) => {
    if (runRef.current !== run) throw new Cancelled();
  };

  const collectAt = async (
    run: number,
    target: Point,
    step: number,
  ): Promise<GazeSample[]> => {
    setView((prev) => ({
      ...(prev ?? emptyView()),
      point: target,
      collecting: false,
      pose: null,
      step,
    }));
    await sleep(PREP_MS + DISCARD_MS);
    guard(run);
    const collect = { target, samples: [] as GazeSample[] };
    collectRef.current = collect;
    setView((prev) => (prev ? { ...prev, collecting: true } : prev));
    await sleep(HOLD_MS);
    collectRef.current = null;
    guard(run);
    return collect.samples;
  };

  const waitForPose = async (run: number): Promise<void> => {
    const started = performance.now();
    while (!poseRef.current?.ready && performance.now() - started < POSE_CONFIRM_TIMEOUT_MS) {
      await sleep(50);
      guard(run);
    }
  };

  const goLive = () => {
    closedFramesRef.current = 0;
    setHoldOnce(null);
    setView(null);
    liveRef.current = true;
    setPhase('live');
  };

  const calibrate = useCallback(() => {
    if (status.state !== 'running') return;
    runRef.current += 1;
    const run = runRef.current;
    busyRef.current = true;
    liveRef.current = false;
    modelRef.current = null;
    collectRef.current = null;
    poseRef.current = null;
    setMessage(null);
    setHoldOnce(null);
    setPhase('calibrating');
    setView(emptyView());

    const flow = async () => {
      // Kalibrasyon ve klavye aynı pencere boyutunda olmalı (K4d).
      await document.documentElement.requestFullscreen().catch(() => undefined);
      await sleep(START_DELAY_MS);
      guard(run);

      let step = 0;
      const collected: GazeSample[] = [];
      for (const target of shuffled(CALIBRATION_GRID)) {
        step += 1;
        collected.push(...(await collectAt(run, target, step)));
      }

      // Baş düzken ölçülen yaw/pitch, pozların kıyaslanacağı taban.
      const baseline = {
        yaw: median(collected.map((sample) => sample.features[YAW] ?? 0)),
        pitch: median(collected.map((sample) => sample.features[PITCH] ?? 0)),
      };
      const signs: { yaw: number | null; pitch: number | null } = { yaw: null, pitch: null };

      for (const pose of HEAD_POSES) {
        step += 1;
        const axis = POSE_AXIS[pose];
        const leader = pose === 'sağa' || pose === 'yukarı';
        const recorded = signs[axis];
        const requireSign = leader ? null : recorded !== null ? -recorded : null;
        setView((prev) => ({
          ...(prev ?? emptyView()),
          point: null,
          collecting: false,
          pose,
          poseProgress: 0,
          poseWrongWay: false,
          poseReady: false,
          step,
        }));
        await sleep(POSE_READ_DELAY_MS);
        guard(run);
        const watcher = new PoseWatcher(axis, baseline[axis], requireSign);
        poseRef.current = watcher;
        await waitForPose(run);
        if (leader) signs[axis] = watcher.sign || null;
        await sleep(POSE_SETTLE_MS);
        poseRef.current = null;
        guard(run);
        for (const target of shuffled(HEAD_POSE_POINTS)) {
          step += 1;
          collected.push(...(await collectAt(run, target, step)));
        }
      }

      const model = BrowserGazeModel.fit(collected, baseline, currentWindow());
      busyRef.current = false;
      if (!model) {
        setView(null);
        setMessage('Yeterli örnek toplanamadı. Yüzün kamerada görünüyor mu?');
        setPhase('needs_calibration');
        return;
      }
      modelRef.current = model;
      setSampleCount(model.sampleCount);
      goLive();
    };

    flow().catch((error: unknown) => {
      if (error instanceof Cancelled) return;
      console.error('Kalibrasyon başarısız', error);
      busyRef.current = false;
      setView(null);
      setMessage('Kalibrasyon yarıda kaldı.');
      setPhase('needs_calibration');
    });
    // collectAt/waitForPose/goLive yalnızca ref ve setState kullanıyor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.state]);

  const recenter = useCallback(() => {
    const model = modelRef.current;
    if (!model || busyRef.current) return;
    runRef.current += 1;
    const run = runRef.current;
    busyRef.current = true;
    liveRef.current = false;
    setPhase('recentering');
    setView({ ...emptyView(), totalSteps: RECENTER_POINTS.length });

    const flow = async () => {
      const groups: Array<{ target: Point; samples: GazeSample[] }> = [];
      let step = 0;
      for (const target of RECENTER_POINTS) {
        step += 1;
        groups.push({ target, samples: await collectAt(run, target, step) });
      }
      busyRef.current = false;
      if (!model.recenter(groups)) {
        setMessage('Ortalama için yeterli örnek yok; önceki düzeltme korunuyor.');
      }
      goLive();
    };

    flow().catch((error: unknown) => {
      if (error instanceof Cancelled) return;
      busyRef.current = false;
      goLive();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Süren kalibrasyonu ya da ortalamayı bırakır. */
  const cancel = useCallback(() => {
    runRef.current += 1;
    collectRef.current = null;
    poseRef.current = null;
    busyRef.current = false;
    if (modelRef.current) {
      goLive();
    } else {
      setView(null);
      setPhase('needs_calibration');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    videoRef,
    status,
    // Kamera açıldığı render'da <video> da çizilmeli: useFaceTracking'in
    // efekti aynı commit'te videoRef'e bakar, yoksa kamera hiç başlamaz.
    phase: enabled ? (phase === 'off' ? 'needs_calibration' : phase) : 'off',
    view,
    hold,
    message,
    sampleCount,
    calibrate,
    recenter,
    cancel,
  };
}

function emptyView(): CalibrationView {
  return {
    point: null,
    collecting: false,
    pose: null,
    poseProgress: 0,
    poseWrongWay: false,
    poseReady: false,
    step: 0,
    totalSteps: TOTAL_STEPS,
  };
}
