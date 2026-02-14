/** Type definitions for X-Agent frontend */

/** Message role types */
export type MessageRole = 'user' | 'assistant' | 'system';

/** Chat message interface */
export interface Message {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  created_at: string;
  metadata?: {
    model?: string;
    tokens?: number;
  };
}

/** Chat session interface */
export interface Session {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

/** WebSocket message types */
export type WebSocketMessageType = 
  | 'user_message'
  | 'assistant_start'
  | 'assistant_chunk'
  | 'assistant_end'
  | 'error';

/** WebSocket message interface */
export interface WebSocketMessage {
  type: WebSocketMessageType;
  session_id: string;
  content?: string;
  error?: {
    code: string;
    message: string;
  };
  metadata?: {
    model?: string;
    tokens?: number;
  };
}

/** API response wrapper */
export interface ApiResponse<T> {
  success: boolean;
  timestamp: string;
  request_id?: string;
  data: T;
}

/** API error response */
export interface ApiError {
  success: false;
  timestamp: string;
  request_id?: string;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

/** Health check response */
export interface HealthResponse {
  status: 'healthy' | 'unhealthy';
  version: string;
  uptime: number;
}

/** Chat request payload */
export interface ChatRequest {
  session_id: string;
  content: string;
}

/** Chat response */
export interface ChatResponse {
  message: Message;
}
