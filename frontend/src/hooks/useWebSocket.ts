/** WebSocket connection management hook */

import { useEffect, useRef, useState } from 'react';

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected' | 'reconnecting';

interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: unknown) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
  heartbeatInterval?: number;
  reconnect?: boolean; // 是否启用自动重连
  maxReconnectAttempts?: number; // 最大重连次数
  reconnectInterval?: number; // 重连间隔（毫秒）
}

interface UseWebSocketReturn {
  status: ConnectionStatus;
  send: (data: unknown) => void;
}

// 全局连接缓存，用于处理 React StrictMode 双重挂载
const connectionCache = new Map<string, WebSocket>();
const cleanupTimeouts = new Map<string, ReturnType<typeof setTimeout>>();

export function useWebSocket({
  url,
  onMessage,
  onConnect,
  onDisconnect,
  onError,
  heartbeatInterval = 30000, // 30 seconds default
  reconnect = true, // 默认启用自动重连
  maxReconnectAttempts = 5,
  reconnectInterval = 3000, // 3 秒
}: UseWebSocketOptions): UseWebSocketReturn {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const connectionIdRef = useRef(0);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const missedHeartbeatsRef = useRef(0);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(true); // 用于控制是否应该重连

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

    // 取消任何待处理的 cleanup timeout（处理 StrictMode 重新挂载）
    const existingTimeout = cleanupTimeouts.get(url);
    if (existingTimeout) {
      clearTimeout(existingTimeout);
      cleanupTimeouts.delete(url);
    }

    // 尝试复用缓存的连接
    const cachedWs = connectionCache.get(url);
    if (cachedWs && cachedWs.readyState === WebSocket.OPEN) {
      console.log('[WS_REUSE] Reusing cached connection to:', url);
      wsRef.current = cachedWs;
      setStatus('connected');

      // 重新绑定事件处理器
      cachedWs.onmessage = (event) => {
        missedHeartbeatsRef.current = 0;
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'pong') return;
          onMessageRef.current?.(data);
        } catch (e) {
          console.error('Failed to parse WebSocket message:', event.data, e);
        }
      };

      startHeartbeat();
      onConnectRef.current?.();
      return;
    }

    // Check if we already have an open connection to the same URL
    if (wsRef.current?.url === url && wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WS_SKIP] Already connected to:', url);
      return;
    }

    setStatus('connecting');

    console.log('[WS_CONNECT] Connecting to:', url);

    const ws = new WebSocket(url);
    wsRef.current = ws;
    connectionCache.set(url, ws);

    ws.onopen = () => {
      console.log('[WS_OPEN] Connection opened');
      if (connectionId === connectionIdRef.current) {
        // 重连成功，重置计数器
        if (reconnectAttemptsRef.current > 0) {
          console.log('[WS_RECONNECT] Reconnection successful!');
          reconnectAttemptsRef.current = 0;
        }

        setStatus('connected');
        missedHeartbeatsRef.current = 0;
        startHeartbeat();
        onConnectRef.current?.();
      }
    };

    ws.onclose = (event) => {
      console.log('[WS_CLOSE] Connection closed:', { code: event.code, reason: event.reason, wasClean: event.wasClean });

      // Always update status if this was our connection
      if (connectionId === connectionIdRef.current) {
        wsRef.current = null;
        clearHeartbeat();

        // 从缓存中移除
        if (connectionCache.get(url) === ws) {
          connectionCache.delete(url);
        }

        // 判断是否需要自动重连
        const shouldAttemptReconnect =
          reconnect &&
          shouldReconnectRef.current &&
          reconnectAttemptsRef.current < maxReconnectAttempts &&
          // 非正常关闭（1000 = 正常关闭）
          event.code !== 1000;

        if (shouldAttemptReconnect) {
          reconnectAttemptsRef.current++;
          setStatus('reconnecting');

          console.log(
            `[WS_RECONNECT] Attempting reconnection (${reconnectAttemptsRef.current}/${maxReconnectAttempts}) in ${reconnectInterval}ms`
          );

          // 延迟重连
          reconnectTimerRef.current = setTimeout(() => {
            if (shouldReconnectRef.current && connectionId === connectionIdRef.current) {
              console.log('[WS_RECONNECT] Initiating reconnection...');
              // 触发重新连接（通过增加 connectionId）
              connectionIdRef.current++;
            }
          }, reconnectInterval);
        } else {
          setStatus('disconnected');
          if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
            console.warn('[WS_RECONNECT] Max reconnection attempts reached');
          }
        }

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

      // Debug: log raw WebSocket message
      console.log('[WS_RAW] Received message:', event.data);

      try {
        const data = JSON.parse(event.data);
        console.log('[WS_PARSED] Parsed data:', data);
        // Ignore pong messages
        if (data.type === 'pong') {
          return;
        }
        onMessageRef.current?.(data);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', event.data, e);
      }
    };

    // Cleanup
    return () => {
      // Mark this connection as stale
      connectionIdRef.current++;
      clearHeartbeat();

      // 停止自动重连
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      // 延迟关闭连接，给 StrictMode 重新挂载的机会
      const timeoutId = setTimeout(() => {
        cleanupTimeouts.delete(url);
        const cached = connectionCache.get(url);
        if (cached === ws) {
          connectionCache.delete(url);
        }
        // Close connection properly
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          console.log('[WS_CLOSE] Closing connection to:', url);
          ws.close();
        }
      }, 100); // 100ms 延迟，足够 StrictMode 重新挂载

      cleanupTimeouts.set(url, timeoutId);
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
