/** REST API client for X-Agent */

import type { ApiResponse, ChatRequest, ChatResponse, HealthResponse, Message, Session } from '@/types';

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
