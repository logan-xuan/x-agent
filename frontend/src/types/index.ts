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

/** Prompt log entry for developer mode */
export interface PromptLogEntry {
  timestamp: string;
  session_id: string | null;
  trace_id: string | null;
  provider: string;
  model: string;
  latency_ms: number;
  success: boolean;
  request: {
    message_count: number;
    messages: Array<{
      role: string;
      content: string;
    }>;
  };
  response: string;
  token_usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
  error?: string;
}

/** Prompt logs response */
export interface PromptLogsResponse {
  logs: PromptLogEntry[];
  total: number;
}

/** Prompt test request */
export interface PromptTestRequest {
  messages: Array<{
    role: string;
    content: string;
  }>;
  stream?: boolean;
  system_prompt?: string;
}

/** Prompt test response */
export interface PromptTestResponse {
  content: string;
  model: string;
  provider: string;
  latency_ms: number;
  token_usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
}

/** Prompt test stream chunk */
export interface PromptTestStreamChunk {
  type: 'chunk' | 'done' | 'error';
  content?: string;
  model?: string;
  provider?: string;
  latency_ms?: number;
  error?: string;
}

// ============================================================================
// Trace Visualization Types
// ============================================================================

/** Detail level for trace visualization */
export type TraceDetailLevel = 'high' | 'medium' | 'detailed';

/** Flow node position */
export interface FlowNodePosition {
  x: number;
  y: number;
}

/** Flow node data */
export interface FlowNodeData {
  label: string;
  module: string;
  timestamp?: string | null;
  level?: string | null;
  source?: string;
  [key: string]: unknown;
}

/** React Flow node */
export interface FlowNode {
  id: string;
  type: string;
  data: FlowNodeData;
  position: FlowNodePosition;
}

/** React Flow edge */
export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  label?: string | null;
  animated?: boolean;
  type?: string;
}

/** Flow graph metadata */
export interface FlowMetadata {
  trace_id: string;
  total_nodes: number;
  total_edges: number;
  start_time?: string | null;
  end_time?: string | null;
  total_duration_ms: number;
  execution_path: string[];
  node_types: string[];
}

/** Trace flow response */
export interface TraceFlowResponse {
  nodes: FlowNode[];
  edges: FlowEdge[];
  metadata: FlowMetadata;
}

/** X-Agent log entry */
export interface XAgentLogEntry {
  timestamp: string | null;
  level: string | null;
  module: string;
  message: string;
  event: string | null;
  trace_id: string | null;
  request_id: string | null;
  session_id: string | null;
  data: Record<string, unknown>;
}

/** Prompt LLM log entry */
export interface PromptLLMLogEntry {
  timestamp: string;
  session_id: string | null;
  trace_id: string;
  provider: string;
  model: string;
  latency_ms: number;
  success: boolean;
  request: {
    message_count: number;
    messages: Array<{
      role: string;
      content: string;
    }>;
  };
  response: string;
  token_usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
  error?: string;
}

/** Trace raw data response */
export interface TraceRawDataResponse {
  trace_id: string;
  session_id: string | null;
  x_agent_logs: XAgentLogEntry[];
  prompt_llm_logs: PromptLLMLogEntry[];
  start_time: string | null;
  end_time: string | null;
  total_duration_ms: number;
}

/** Analysis insight */
export interface AnalysisInsight {
  type: string;  // performance, error, optimization
  title: string;
  description: string;
  location?: string | null;
  severity?: string | null;  // low, medium, high
}

/** Trace analysis request */
export interface TraceAnalysisRequest {
  focus_areas?: string[];
  include_suggestions?: boolean;
}

/** Trace analysis response */
export interface TraceAnalysisResponse {
  analysis: string;
  insights: AnalysisInsight[];
  suggestions: string[];
}
