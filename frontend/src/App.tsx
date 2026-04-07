/** X-Agent main application */

import { useEffect, useRef, useState } from 'react';
import './index.css';
import { AgentChatWindow } from './components/agent';
import { SettingsWindow } from './components/settings/SettingsWindow';
import { AdminPanel } from './components/admin/AdminPanel';
import { useAgent } from './hooks/useAgent';
import { AgentInfo, createSession as createSessionApi, getActiveSessionByAgent } from './services/api';

type View = 'agent' | 'settings' | 'admin';

/** 默认 Agent ID - 确保新用户首次访问时也有正确的 agent_id */
const DEFAULT_AGENT_ID = 'main-agent';

/** 全局当前 session key（兼容旧数据） */
const AGENT_SESSION_STORAGE_KEY = 'x-agent-agent-session-id';

/** 按 agent_id 存储各自 session ID 的 localStorage key */
function agentSessionKey(agentId: string): string {
  return `x-agent-session-${agentId}`;
}

/** 从 localStorage 读取指定 agent 的 session ID */
function getStoredSessionId(agentId: string): string | null {
  return localStorage.getItem(agentSessionKey(agentId));
}

/** 将指定 agent 的 session ID 写入 localStorage */
function storeSessionId(agentId: string, sessionId: string): void {
  localStorage.setItem(agentSessionKey(agentId), sessionId);
  // 同步更新全局 key，供兼容旧逻辑使用
  localStorage.setItem(AGENT_SESSION_STORAGE_KEY, sessionId);
}

/** 简单的 URL 路由检测 */
function getInitialView(): View {
  const path = window.location.pathname;
  if (path === '/settings') return 'settings';
  if (path === '/admin') return 'admin';
  return 'agent';
}

function App() {
  const [view, setView] = useState<View>(getInitialView);
  const [agentSessionId, setAgentSessionId] = useState<string | null>(() => {
    return localStorage.getItem(AGENT_SESSION_STORAGE_KEY);
  });
  const [currentAgentId, setCurrentAgentId] = useState<string | null>(() => {
    // 如果没有保存的 agent_id，使用默认值
    return localStorage.getItem('x-agent-current-agent-id') || DEFAULT_AGENT_ID;
  });
  const [isAgentInitialized, setIsAgentInitialized] = useState(false);
  const initializingRef = useRef(false);

  // Agent hook
  const {
    messages: agentMessages,
    sessionId: currentAgentSessionId,
    isLoading: agentIsLoading,
    streamingContent: agentStreamingContent,
    streamingThinking: agentStreamingThinking,
    connectionStatus: agentConnectionStatus,
    sendMessage: agentSendMessage,
    abort: agentAbort,
    clearMessages: agentClearMessages,
    createSession: agentCreateSession,
    loadHistory: agentLoadHistory,
  } = useAgent({ sessionId: agentSessionId });

  // Initialize agent session on mount
  useEffect(() => {
    const initAgentSession = async () => {
      try {
        // 使用默认 agent_id 确保 session 始终绑定到正确的 agent
        const savedAgentId = localStorage.getItem('x-agent-current-agent-id') || DEFAULT_AGENT_ID;

        // 1. 优先恢复当前 agent 已保存的 session，避免切 agent 时被“最新 active”劫持
        const savedSessionId = getStoredSessionId(savedAgentId)
          || localStorage.getItem(AGENT_SESSION_STORAGE_KEY);

        if (savedSessionId) {
          try {
            await agentLoadHistory(savedSessionId);
            storeSessionId(savedAgentId, savedSessionId);
            setAgentSessionId(savedSessionId);
            localStorage.setItem('x-agent-current-agent-id', savedAgentId);
            setIsAgentInitialized(true);
            return;
          } catch (error) {
            console.warn('Failed to load saved agent session, will try backend active session:', error);
            localStorage.removeItem(agentSessionKey(savedAgentId));
            localStorage.removeItem(AGENT_SESSION_STORAGE_KEY);
          }
        }

        // 2. 再查询当前 agent 的 active session，兼容首次打开 delegated agent 窗口
        try {
          const existingSession = await getActiveSessionByAgent(savedAgentId);
          if (existingSession) {
            await agentLoadHistory(existingSession.id);
            storeSessionId(savedAgentId, existingSession.id);
            setAgentSessionId(existingSession.id);
            localStorage.setItem('x-agent-current-agent-id', savedAgentId);
            setIsAgentInitialized(true);
            return;
          }
        } catch (error) {
          console.warn('Failed to find active session for agent, will try stored session:', error);
        }

        // 3. 没有可复用的 session，创建新 session（始终带 agent_id）
        const session = await agentCreateSession('Agent 对话', savedAgentId);
        storeSessionId(savedAgentId, session.id);
        // 确保 localStorage 中有 agent_id
        localStorage.setItem('x-agent-current-agent-id', savedAgentId);
        setAgentSessionId(session.id);
        setIsAgentInitialized(true);
      } catch (error) {
        console.error('Failed to initialize agent session:', error);
        setIsAgentInitialized(true);
      }
    };

    if (!isAgentInitialized && !initializingRef.current) {
      initializingRef.current = true;
      initAgentSession();
    }
  }, [isAgentInitialized, agentCreateSession, agentLoadHistory]);

  // Handle agent switch: restore the session for this agent from localStorage first,
  // then fall back to querying the backend for an active session, and finally create a new one.
  // Never close existing sessions during a switch — only the "New Session" button does that.
  const handleAgentChange = async (agent: AgentInfo) => {
    try {
      setCurrentAgentId(agent.agent_id);
      localStorage.setItem('x-agent-current-agent-id', agent.agent_id);
      agentClearMessages();

      // 1. 优先恢复当前 agent 已保存的 session，保持会话连续性
      const storedSessionId = getStoredSessionId(agent.agent_id);
      if (storedSessionId) {
        try {
          await agentLoadHistory(storedSessionId);
          storeSessionId(agent.agent_id, storedSessionId);
          setAgentSessionId(storedSessionId);
          return;
        } catch (error) {
          console.warn('Stored session no longer valid, creating new one:', error);
          localStorage.removeItem(agentSessionKey(agent.agent_id));
        }
      }

      // 2. 再查询后端该 agent 的 active session，兼容首次打开 delegated agent 窗口
      const existingSession = await getActiveSessionByAgent(agent.agent_id);
      if (existingSession) {
        await agentLoadHistory(existingSession.id);
        storeSessionId(agent.agent_id, existingSession.id);
        setAgentSessionId(existingSession.id);
        return;
      }

      // 3. 没有可复用的 session，创建新 session（不关闭其他 agent 的 session）
      const session = await agentCreateSession(agent.agent_name + ' 对话', agent.agent_id);
      storeSessionId(agent.agent_id, session.id);
      setAgentSessionId(session.id);
    } catch (error) {
      console.error('Failed to switch agent:', error);
    }
  };

  // Update URL when view changes
  useEffect(() => {
    const pathMap: Record<View, string> = { agent: '/', settings: '/settings', admin: '/admin' };
    const path = pathMap[view];
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path);
    }
  }, [view]);

  // Handle browser back/forward
  useEffect(() => {
    const handlePopState = () => {
      setView(getInitialView());
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Render admin view
  if (view === 'admin') {
    return <AdminPanel onClose={() => setView('agent')} />;
  }

  // Render settings view
  if (view === 'settings') {
    return <SettingsWindow onClose={() => setView('agent')} />;
  }

  // Render agent view
  return (
    <AgentChatWindow
      sessionId={currentAgentSessionId}
      messages={agentMessages}
      streamingContent={agentStreamingContent}
      streamingThinking={agentStreamingThinking}
      isLoading={agentIsLoading}
      isConnecting={!isAgentInitialized}
      connectionStatus={agentConnectionStatus}
      currentAgentId={currentAgentId}
      onSendMessage={agentSendMessage}
      onAbort={agentAbort}
      onClearMessages={agentClearMessages}
      onOpenSettings={() => setView('settings')}
      onAgentChange={handleAgentChange}
      onNewSession={async () => {
        try {
          // 用户主动新建会话：关闭当前 agent 的旧 session，创建新 session
          const session = await createSessionApi(
            currentAgentId ? undefined : 'Agent 对话',
            currentAgentId ?? undefined,
            true, // closeExisting=true，仅此处关闭旧 session
          );
          if (currentAgentId) {
            storeSessionId(currentAgentId, session.id);
          } else {
            localStorage.setItem(AGENT_SESSION_STORAGE_KEY, session.id);
          }
          setAgentSessionId(session.id);
        } catch (error) {
          console.error('Failed to create new agent session:', error);
        }
      }}
    />
  );
}

export default App;
