/** REST API client for X-Agent */

import type { 
  ApiResponse, 
  ChatRequest, 
  ChatResponse, 
  HealthResponse, 
  Message, 
  Session, 
  PromptLogsResponse, 
  PromptTestRequest, 
  PromptTestResponse, 
  PromptTestStreamChunk,
  TraceFlowResponse,
  TraceRawDataResponse,
  TraceAnalysisRequest,
  TraceAnalysisResponse,
  TraceDetailLevel,
} from '@/types';

const API_BASE_URL = '/api/v1';

/** Generic API request handler */
async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error?.message || 'API request failed');
  }

  const data: ApiResponse<T> = await response.json();
  if (!data.success) {
    throw new Error('API returned unsuccessful response');
  }

  return data.data;
}

/** Health check API */
export async function checkHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>('/health');
}

/** Session APIs */
export async function listSessions(limit = 20, offset = 0): Promise<{ items: Session[]; total: number }> {
  return apiRequest<{ items: Session[]; total: number }>(`/sessions?limit=${limit}&offset=${offset}`);
}

export async function createSession(title?: string): Promise<Session> {
  return apiRequest<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export async function getSession(sessionId: string): Promise<{ session: Session; messages: Message[] }> {
  return apiRequest<{ session: Session; messages: Message[] }>(`/sessions/${sessionId}`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiRequest<void>(`/sessions/${sessionId}`, {
    method: 'DELETE',
  });
}

/** Message APIs */
export async function listMessages(
  sessionId: string,
  limit = 50,
  before?: string
): Promise<{ items: Message[]; hasMore: boolean }> {
  const params = new URLSearchParams({ limit: limit.toString() });
  if (before) params.append('before', before);
  return apiRequest<{ items: Message[]; hasMore: boolean }>(`/sessions/${sessionId}/messages?${params}`);
}

/** Chat API (non-streaming) */
export async function sendMessage(sessionId: string, content: string): Promise<ChatResponse> {
  const request: ChatRequest = { session_id: sessionId, content };
  return apiRequest<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/** Developer mode APIs */

/** Get prompt interaction logs */
export async function getPromptLogs(limit = 20): Promise<PromptLogsResponse> {
  const response = await fetch(`${API_BASE_URL}/dev/prompt-logs?limit=${limit}`, {
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch prompt logs');
  }

  return response.json();
}

/** Test prompt with primary LLM (non-streaming) */
export async function testPrompt(request: PromptTestRequest): Promise<PromptTestResponse> {
  const response = await fetch(`${API_BASE_URL}/dev/prompt-test`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to test prompt');
  }

  return response.json();
}

/** Test prompt with primary LLM (streaming) */
export async function testPromptStream(
  request: PromptTestRequest,
  onChunk: (chunk: PromptTestStreamChunk) => void,
  onError?: (error: Error) => void
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/dev/prompt-test/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error?.message || 'Stream request failed');
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data: PromptTestStreamChunk = JSON.parse(line.slice(6));
            onChunk(data);
            if (data.type === 'done' || data.type === 'error') {
              return;
            }
          } catch (e) {
            console.error('Failed to parse SSE data:', line);
          }
        }
      }
    }
  } catch (error) {
    onError?.(error as Error);
    throw error;
  } finally {
    reader.releaseLock();
  }
}

/** Trace visualization APIs */

/** Get trace raw data (logs aggregated by trace_id) */
export async function getTraceRawData(traceId: string): Promise<TraceRawDataResponse> {
  const response = await fetch(`${API_BASE_URL}/trace/${traceId}/raw`, {
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch trace raw data');
  }

  return response.json();
}

/** Get trace flow graph for visualization */
export async function getTraceFlow(
  traceId: string,
  detailLevel: TraceDetailLevel = 'high'
): Promise<TraceFlowResponse> {
  const response = await fetch(
    `${API_BASE_URL}/trace/${traceId}/flow?detail_level=${detailLevel}`,
    {
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to fetch trace flow');
  }

  return response.json();
}

/** Analyze trace with LLM */
export async function analyzeTrace(
  traceId: string,
  request?: TraceAnalysisRequest
): Promise<TraceAnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}/trace/${traceId}/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request || {}),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to analyze trace');
  }

  return response.json();
}
