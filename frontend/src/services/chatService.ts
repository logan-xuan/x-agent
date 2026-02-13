/**
 * Chat service for x-agent2 AI assistant system
 * Handles API calls to the backend chat endpoints
 */

// Removed unused ChatMessage interface

interface ChatResponse {
  response: string;
  sessionId: string;
  timestamp: string;
  usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  metadata?: {
    processing_time_ms: number;
    model_used: string;
    langchain_trace_id?: string;
  };
}

interface ToolExecutionResponse {
  result: any;
  status: 'success' | 'failed';
  execution_time_ms: number;
  metadata: {
    tool_used: string;
    parameters_used: Record<string, any>;
    langchain_tool_call_id?: string;
  };
}

interface FileUploadResponse {
  status: 'success' | 'failed';
  file_path: string;
  filename: string;
  timestamp: string;
}

class ChatService {
  private baseUrl: string;
  private defaultHeaders: HeadersInit;

  constructor(baseUrl: string = '/api/v1') {
    this.baseUrl = baseUrl;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    };
  }

  /**
   * Send a chat message to the AI assistant
   */
  async sendMessage(
    message: string,
    sessionId?: string,
    context?: Record<string, any>
  ): Promise<ChatResponse> {
    const requestBody = {
      message,
      ...(sessionId && { session_id: sessionId }),
      ...(context && { context }),
    };

    try {
      const response = await fetch(`${this.baseUrl}/chat`, {
        method: 'POST',
        headers: this.defaultHeaders,
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data as ChatResponse;
    } catch (error) {
      console.error('Error sending message:', error);
      throw error;
    }
  }

  /**
   * Execute a specific tool with provided parameters
   */
  async executeTool(
    toolName: string,
    parameters: Record<string, any>,
    sessionId?: string
  ): Promise<ToolExecutionResponse> {
    const requestBody = {
      tool_name: toolName,
      parameters,
      ...(sessionId && { session_id: sessionId }),
    };

    try {
      const response = await fetch(`${this.baseUrl}/tools/execute`, {
        method: 'POST',
        headers: this.defaultHeaders,
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data as ToolExecutionResponse;
    } catch (error) {
      console.error('Error executing tool:', error);
      throw error;
    }
  }

  /**
   * Upload a file to the server
   */
  async uploadFile(
    file: File,
    sessionId: string,
    _onProgress?: (progress: number) => void // Renamed with underscore to indicate it's intentionally unused
  ): Promise<FileUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('session_id', sessionId);

    try {
      const response = await fetch(`${this.baseUrl}/files/upload`, {
        method: 'POST',
        body: formData,
        // Note: Don't set Content-Type header when using FormData
        headers: {
          // Don't include Content-Type as it will be set automatically by the browser
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data as FileUploadResponse;
    } catch (error) {
      console.error('Error uploading file:', error);
      throw error;
    }
  }

  /**
   * Establish a WebSocket connection for real-time chat
   */
  connectWebSocket(sessionId?: string): WebSocket {
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss://' : 'ws://'}${window.location.host}${this.baseUrl}/ws`;
    const urlWithSession = sessionId ? `${wsUrl}?session_id=${encodeURIComponent(sessionId)}` : wsUrl;

    const ws = new WebSocket(urlWithSession);

    ws.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    return ws;
  }

  /**
   * Get available tools from the backend
   */
  async getAvailableTools(): Promise<string[]> {
    try {
      const response = await fetch(`${this.baseUrl}/tools/list`, {
        method: 'GET',
        headers: this.defaultHeaders,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return Array.isArray(data.tools) ? data.tools : [];
    } catch (error) {
      console.error('Error getting available tools:', error);
      throw error;
    }
  }

  /**
   * Create a new session
   */
  async createSession(userId?: string): Promise<{ sessionId: string }> {
    try {
      const requestBody = userId ? { user_id: userId } : {};
      const response = await fetch(`${this.baseUrl}/sessions/create`, {
        method: 'POST',
        headers: this.defaultHeaders,
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return { sessionId: data.session_id };
    } catch (error) {
      console.error('Error creating session:', error);
      throw error;
    }
  }

  /**
   * Get session details
   */
  async getSession(sessionId: string): Promise<any> {
    try {
      const response = await fetch(`${this.baseUrl}/sessions/${sessionId}`, {
        method: 'GET',
        headers: this.defaultHeaders,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error getting session:', error);
      throw error;
    }
  }

  /**
   * End a session
   */
  async endSession(sessionId: string): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/end`, {
        method: 'POST',
        headers: this.defaultHeaders,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return true;
    } catch (error) {
      console.error('Error ending session:', error);
      return false;
    }
  }
}

// Export a singleton instance
export const chatService = new ChatService();

export default ChatService;