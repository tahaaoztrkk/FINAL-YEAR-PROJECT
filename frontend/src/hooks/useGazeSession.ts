/**
 * WebSocket oturumunun React tarafı.
 *
 * Tüm sunucu mesajları tek yerde işlenir ve bileşenlerin kullanacağı sade
 * bir durum nesnesine indirgenir. Bileşenler WebSocket'i hiç görmez.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { GazeSocket, type ConnectionState } from '@/lib/ws';
import type {
  Candidate,
  ClientMessage,
  GazeTarget,
  ServerMessage,
} from '@/types/messages';

export interface SessionState {
  connection: ConnectionState;
  sessionId: string | null;
  gazeSource: string | null;
  expanderProvider: string | null;
  dwellMs: number;
  gaze: { x: number; y: number } | null;
  dwellTargetId: string | null;
  dwellProgress: number;
  candidates: Candidate[];
  /** Son aday listesinin ait olduğu kısaltma; boş sonucu "istenmedi"den ayırır. */
  candidatesFor: string | null;
  lastLatencyMs: number | null;
  calibrationErrorDeg: number | null;
  lastError: string | null;
}

const INITIAL: SessionState = {
  connection: 'connecting',
  sessionId: null,
  gazeSource: null,
  expanderProvider: null,
  dwellMs: 700,
  gaze: null,
  dwellTargetId: null,
  dwellProgress: 0,
  candidates: [],
  candidatesFor: null,
  lastLatencyMs: null,
  calibrationErrorDeg: null,
  lastError: null,
};

export interface UseGazeSessionResult {
  state: SessionState;
  send: (message: ClientMessage) => void;
  sendTargets: (targets: GazeTarget[]) => void;
  sendGaze: (x: number, y: number, t: number, confidence?: number) => void;
  requestExpansion: (abbreviation: string, scheme: string, context?: string) => void;
}

export function useGazeSession(
  onSelection: (targetId: string) => void,
): UseGazeSessionResult {
  const [state, setState] = useState<SessionState>(INITIAL);
  const socketRef = useRef<GazeSocket | null>(null);

  // Seçim geri çağrısı her render'da değişir; ref ile sabitlenmezse
  // WebSocket her render'da yeniden kurulur.
  const selectionRef = useRef(onSelection);
  selectionRef.current = onSelection;

  useEffect(() => {
    const socket = new GazeSocket({
      onStateChange: (connection) => setState((prev) => ({ ...prev, connection })),
      onMessage: (message: ServerMessage) => {
        switch (message.type) {
          case 'ready':
            setState((prev) => ({
              ...prev,
              sessionId: message.session_id,
              gazeSource: message.gaze_source,
              expanderProvider: message.expander_provider,
              dwellMs: message.dwell_ms,
            }));
            break;

          case 'gaze':
            setState((prev) => ({ ...prev, gaze: { x: message.x, y: message.y } }));
            break;

          case 'dwell_progress':
            setState((prev) => ({
              ...prev,
              dwellTargetId: message.target_id,
              dwellProgress: message.progress,
            }));
            break;

          case 'selection':
            setState((prev) => ({ ...prev, dwellTargetId: null, dwellProgress: 0 }));
            selectionRef.current(message.target_id);
            break;

          case 'candidates':
            setState((prev) => ({
              ...prev,
              candidates: message.candidates,
              candidatesFor: message.abbreviation,
              lastLatencyMs: message.latency_ms,
            }));
            break;

          case 'calibration_result':
            setState((prev) => ({
              ...prev,
              calibrationErrorDeg: message.mean_error_deg ?? null,
              lastError: message.ok ? null : (message.message ?? 'Kalibrasyon başarısız'),
            }));
            break;

          case 'error':
            setState((prev) => ({ ...prev, lastError: message.detail }));
            break;
        }
      },
    });

    socketRef.current = socket;
    socket.connect();
    socket.send({
      type: 'hello',
      screen_width: window.innerWidth,
      screen_height: window.innerHeight,
    });

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, []);

  const send = useCallback((message: ClientMessage) => {
    socketRef.current?.send(message);
  }, []);

  const sendTargets = useCallback(
    (targets: GazeTarget[]) => send({ type: 'targets', targets }),
    [send],
  );

  const sendGaze = useCallback(
    (x: number, y: number, t: number, confidence = 1) =>
      send({ type: 'gaze', point: { x, y, t, confidence } }),
    [send],
  );

  const requestExpansion = useCallback(
    (abbreviation: string, scheme: string, context?: string) =>
      send({
        type: 'expand',
        abbreviation,
        scheme,
        context: context ?? null,
        top_k: 5,
      }),
    [send],
  );

  return { state, send, sendTargets, sendGaze, requestExpansion };
}
