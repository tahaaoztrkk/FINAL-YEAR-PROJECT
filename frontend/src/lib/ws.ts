/**
 * WebSocket istemcisi.
 *
 * Bağlantı kopması kullanıcıyı cümlesinin ortasında bırakır, bu yüzden
 * yeniden bağlanma üstel geri çekilmeyle otomatik yapılır. Mesaj gönderimi
 * bağlantı kapalıyken kuyruğa alınır.
 */

import type { ClientMessage, ServerMessage } from '@/types/messages';

export type ConnectionState = 'connecting' | 'open' | 'closed';

export interface GazeSocketOptions {
  url?: string;
  onMessage: (message: ServerMessage) => void;
  onStateChange?: (state: ConnectionState) => void;
  maxRetryDelayMs?: number;
}

function defaultUrl(): string {
  const configured = import.meta.env.VITE_WS_URL;
  if (configured) return configured;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

export class GazeSocket {
  private socket: WebSocket | null = null;
  private readonly url: string;
  private readonly options: GazeSocketOptions;
  private queue: ClientMessage[] = [];
  private retryCount = 0;
  private retryTimer: number | null = null;
  private closedByUser = false;

  constructor(options: GazeSocketOptions) {
    this.options = options;
    this.url = options.url ?? defaultUrl();
  }

  connect(): void {
    this.closedByUser = false;
    this.options.onStateChange?.('connecting');

    const socket = new WebSocket(this.url);
    this.socket = socket;

    socket.onopen = () => {
      this.retryCount = 0;
      this.options.onStateChange?.('open');
      // Kuyrukta bekleyen mesajları sırayla gönder.
      const pending = this.queue;
      this.queue = [];
      pending.forEach((message) => this.send(message));
    };

    socket.onmessage = (event) => {
      try {
        this.options.onMessage(JSON.parse(event.data as string) as ServerMessage);
      } catch {
        // Bozuk tek mesaj akışı durdurmamalı.
      }
    };

    socket.onclose = () => {
      this.options.onStateChange?.('closed');
      if (!this.closedByUser) this.scheduleRetry();
    };

    socket.onerror = () => socket.close();
  }

  private scheduleRetry(): void {
    if (this.retryTimer !== null) return;
    const maxDelay = this.options.maxRetryDelayMs ?? 5000;
    const delay = Math.min(maxDelay, 250 * 2 ** this.retryCount);
    this.retryCount += 1;
    this.retryTimer = window.setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, delay);
  }

  send(message: ClientMessage): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
      return;
    }
    // Bakış örnekleri 30 Hz akar; kuyruğun sınırsız büyümesine izin verilmez.
    if (message.type === 'gaze') return;
    this.queue.push(message);
  }

  close(): void {
    this.closedByUser = true;
    if (this.retryTimer !== null) {
      window.clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.socket?.close();
    this.socket = null;
  }
}
