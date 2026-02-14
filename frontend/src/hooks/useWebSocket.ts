/** WebSocket connection management hook */

import { useEffect, useRef, useState } from 'react';

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected';

interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: unknown) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  heartbeatInterval?: number;
}

interface UseWebSocketReturn {
  status: ConnectionStatus;
  send: (data: unknown) => void;
}

export function useWebSocket({
  url,
  onMessage,
  onConnect,
  onDisconnect,
  onError,
  heartbeatInterval = 30000, // 30 seconds default
}: UseWebSocketOptions): UseWebSocketReturn {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const connectionIdRef = useRef(0);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const missedHeartbeatsRef = useRef(0);
  
  // Store callbacks in refs
  const onMessageRef = useRef(onMessage);
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  const onErrorRef = useRef(onError);
  
  // Update refs when callbacks change
  onMessageRef.current = onMessage;
  onConnectRef.current = onConnect;
  onDisconnectRef.current = onDisconnect;
  onErrorRef.current = onError;
  
  // Clear heartbeat timer
  const clearHeartbeat = () => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  };
  
  // Start heartbeat to detect dead connections
  const startHeartbeat = () => {
    clearHeartbeat();
    missedHeartbeatsRef.current = 0;
    
    heartbeatTimerRef.current = setInterval(() => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        return;
      }
      
      missedHeartbeatsRef.current++;
      
      // If we've missed too many heartbeats, consider connection dead
      if (missedHeartbeatsRef.current > 3) {
        console.warn('WebSocket heartbeat failed, closing connection');
        ws.close();
        return;
      }
      
      // Send ping - server should respond with pong or any message resets the counter
      try {
        ws.send(JSON.stringify({ type: 'ping' }));
      } catch {
        console.warn('Failed to send heartbeat, closing connection');
        ws.close();
      }
    }, heartbeatInterval);
  };
  
  // Main connection effect
  useEffect(() => {
    // Don't connect if URL is empty
    if (!url) {
      setStatus('disconnected');
      return;
    }
    
    const connectionId = ++connectionIdRef.current;
    
    setStatus('connecting');
    
    const ws = new WebSocket(url);
    wsRef.current = ws;
    
    ws.onopen = () => {
      if (connectionId === connectionIdRef.current) {
        setStatus('connected');
        missedHeartbeatsRef.current = 0;
        startHeartbeat();
        onConnectRef.current?.();
      }
    };
    
    ws.onclose = () => {
      // Always update status if this was our connection
      if (connectionId === connectionIdRef.current) {
        wsRef.current = null;
        clearHeartbeat();
        setStatus('disconnected');
        onDisconnectRef.current?.();
      }
    };
    
    ws.onerror = (error) => {
      if (connectionId === connectionIdRef.current) {
        onErrorRef.current?.(error);
      }
    };
    
    ws.onmessage = (event) => {
      // Reset heartbeat counter on any message
      missedHeartbeatsRef.current = 0;
      
      try {
        const data = JSON.parse(event.data);
        // Ignore pong messages
        if (data.type === 'pong') {
          return;
        }
        onMessageRef.current?.(data);
      } catch {
        console.error('Failed to parse WebSocket message:', event.data);
      }
    };
    
    // Cleanup
    return () => {
      // Mark this connection as stale
      connectionIdRef.current++;
      clearHeartbeat();
      
      // Close connection properly
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
      wsRef.current = null;
    };
  }, [url, heartbeatInterval]);
  
  // Send message
  const send = (data: unknown) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify(data));
      } catch (error) {
        console.error('Failed to send WebSocket message:', error);
        // Connection might be dead
        if (connectionIdRef.current === connectionIdRef.current) {
          setStatus('disconnected');
        }
      }
    } else {
      console.warn('WebSocket is not connected, cannot send message');
    }
  };
  
  // Monitor online/offline events
  useEffect(() => {
    const handleOnline = () => {
      console.log('Network back online');
      // Status will update when WebSocket reconnects
    };
    
    const handleOffline = () => {
      console.log('Network offline');
      // Immediately mark as disconnected
      if (wsRef.current) {
        wsRef.current.close();
      }
      setStatus('disconnected');
    };
    
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);
  
  return {
    status,
    send,
  };
}
