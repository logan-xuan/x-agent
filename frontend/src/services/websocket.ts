/** WebSocket client for real-time chat with distributed tracing */

import type { WebSocketMessage } from '@/types';
import { logger } from '@/utils/logger';

export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface WebSocketCallbacks {
  onMessage?: (message: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
}

/** Generate UUID v4 */
function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private callbacks: WebSocketCallbacks;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private status: WebSocketStatus = 'disconnected';
  private traceId: string | null = null;

  constructor(url: string = '/ws/chat', callbacks: WebSocketCallbacks = {}) {
    this.url = url;
    this.callbacks = callbacks;
  }

  get connectionStatus(): WebSocketStatus {
    return this.status;
  }

  get currentTraceId(): string | null {
    return this.traceId;
  }

  connect(sessionId?: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    this.status = 'connecting';
    
    // Generate trace ID for this connection
    this.traceId = generateUUID();
    
    logger.info('[WebSocketClient] Connecting', { 
      traceId: this.traceId, 
      sessionId,
      url: this.url 
    });
    
    try {
      // Build URL with trace ID header simulation (via query param for WebSocket)
      const urlWithTrace = sessionId 
        ? `${this.url}/${sessionId}?trace_id=${this.traceId}`
        : `${this.url}?trace_id=${this.traceId}`;
      
      this.ws = new WebSocket(urlWithTrace);
      
      this.ws.onopen = () => {
        this.status = 'connected';
        this.reconnectAttempts = 0;
        logger.info('[WebSocketClient] Connected', { traceId: this.traceId });
        this.callbacks.onConnect?.();
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          
          // Log received message with trace ID
          if ('trace_id' in message) {
            logger.debug('[WebSocketClient] Received message', { 
              traceId: message.trace_id,
              type: message.type 
            });
          }
          
          this.callbacks.onMessage?.(message);
        } catch (error) {
          logger.error('[WebSocketClient] Failed to parse message', { error, traceId: this.traceId });
        }
      };

      this.ws.onclose = () => {
        this.status = 'disconnected';
        logger.info('[WebSocketClient] Disconnected', { traceId: this.traceId });
        this.callbacks.onDisconnect?.();
        this.attemptReconnect();
      };

      this.ws.onerror = (error) => {
        this.status = 'error';
        logger.error('[WebSocketClient] Connection error', { error, traceId: this.traceId });
        this.callbacks.onError?.(error);
      };
    } catch (error) {
      this.status = 'error';
      logger.error('[WebSocketClient] Failed to create connection', { error, traceId: this.traceId });
    }
  }

  disconnect(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    
    this.reconnectAttempts = this.maxReconnectAttempts; // Prevent reconnection
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    this.status = 'disconnected';
  }

  send(message: WebSocketMessage): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      console.error('WebSocket is not connected');
      return false;
    }

    try {
      this.ws.send(JSON.stringify(message));
      return true;
    } catch (error) {
      console.error('Failed to send WebSocket message:', error);
      return false;
    }
  }

  sendUserMessage(sessionId: string, content: string): boolean {
    return this.send({
      type: 'user_message',
      session_id: sessionId,
      content,
    });
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    
    console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`);
    
    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, delay);
  }
}

/** Create WebSocket client instance */
export function createWebSocketClient(callbacks: WebSocketCallbacks = {}): WebSocketClient {
  return new WebSocketClient('/ws/chat', callbacks);
}
