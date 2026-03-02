/** X-Agent main application */

import { useEffect, useState } from 'react';
import './index.css';
import { ChatWindow } from './components/chat/ChatWindow';
import { AgentChatWindow } from './components/agent';
import { SettingsWindow } from './components/settings/SettingsWindow';
import { useChat } from './hooks/useChat';
import { useAgent } from './hooks/useAgent';

type View = 'chat' | 'agent' | 'settings';

const SESSION_STORAGE_KEY = 'x-agent-session-id';
const AGENT_SESSION_STORAGE_KEY = 'x-agent-agent-session-id';

/** 简单的 URL 路由检测 */
function getInitialView(): View {
  const path = window.location.pathname;
  if (path === '/agent') return 'chat';  // /agent 路径显示聊天界面
  if (path === '/settings') return 'settings';
  return 'agent';  // 根路径默认显示 Agent 界面
}

function App() {
  const [view, setView] = useState<View>(getInitialView);
  const [previousView, setPreviousView] = useState<View>('chat'); // 记录进入设置前的视图
  const [agentSessionId, setAgentSessionId] = useState<string | null>(() => {
    return localStorage.getItem(AGENT_SESSION_STORAGE_KEY);
  });
  const [isInitialized, setIsInitialized] = useState(false);
  const [isAgentInitialized, setIsAgentInitialized] = useState(false);

  // Chat hook
  const {
    messages,
    sessionId,
    isLoading,
    streamingContent,
    streamingModel,
    connectionStatus,
    sendMessage,
    confirmToolCall,
    createSession,
    loadHistory,
  } = useChat({ sessionId: null });

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

  // Initialize chat session on mount
  useEffect(() => {
    const initSession = async () => {
      try {
        // Try to restore previous session from localStorage
        const savedSessionId = localStorage.getItem(SESSION_STORAGE_KEY);

        if (savedSessionId) {
          // Try to load history from saved session
          try {
            await loadHistory(savedSessionId);
            setIsInitialized(true);
            return;
          } catch (error) {
            console.warn('Failed to load saved session, creating new one:', error);
            localStorage.removeItem(SESSION_STORAGE_KEY);
          }
        }

        // Create new session if no saved session or load failed
        const session = await createSession('新对话');
        localStorage.setItem(SESSION_STORAGE_KEY, session.id);
        setIsInitialized(true);
      } catch (error) {
        console.error('Failed to initialize session:', error);
      }
    };

    if (!sessionId && !isInitialized) {
      initSession();
    }
  }, [sessionId, isInitialized, createSession, loadHistory]);

  // Initialize agent session on mount
  useEffect(() => {
    const initAgentSession = async () => {
      try {
        // Try to restore previous session from localStorage
        const savedSessionId = localStorage.getItem(AGENT_SESSION_STORAGE_KEY);

        if (savedSessionId) {
          // Try to load history from saved session
          try {
            await agentLoadHistory(savedSessionId);
            setAgentSessionId(savedSessionId);
            setIsAgentInitialized(true);
            return;
          } catch (error) {
            console.warn('Failed to load saved agent session, creating new one:', error);
            localStorage.removeItem(AGENT_SESSION_STORAGE_KEY);
          }
        }

        // Create new session if no saved session or load failed
        const session = await agentCreateSession('Agent 对话');
        localStorage.setItem(AGENT_SESSION_STORAGE_KEY, session.id);
        setAgentSessionId(session.id);
        setIsAgentInitialized(true);
      } catch (error) {
        console.error('Failed to initialize agent session:', error);
        // 即使初始化失败也标记为完成，避免无限循环
        setIsAgentInitialized(true);
      }
    };

    if (!isAgentInitialized) {
      initAgentSession();
    }
  }, [isAgentInitialized, agentCreateSession, agentLoadHistory]);

  // Save session ID when it changes
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    }
  }, [sessionId]);

  // Save agent session ID
  useEffect(() => {
    if (agentSessionId) {
      localStorage.setItem(AGENT_SESSION_STORAGE_KEY, agentSessionId);
    }
  }, [agentSessionId]);

  // Update URL when view changes
  useEffect(() => {
    const path = view === 'chat' ? '/agent' : view === 'settings' ? '/settings' : '/';
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

  // Render settings view
  if (view === 'settings') {
    return <SettingsWindow onClose={() => setView(previousView)} />;
  }

  // Render agent view
  if (view === 'agent') {
    return (
      <AgentChatWindow
        sessionId={currentAgentSessionId}
        messages={agentMessages}
        streamingContent={agentStreamingContent}
        streamingThinking={agentStreamingThinking}
        isLoading={agentIsLoading}
        isConnecting={!isAgentInitialized}
        connectionStatus={agentConnectionStatus}
        onSendMessage={agentSendMessage}
        onAbort={agentAbort}
        onClearMessages={agentClearMessages}
        onOpenSettings={() => { setPreviousView('agent'); setView('settings'); }}
        onNewSession={async () => {
          try {
            const session = await agentCreateSession('Agent 对话');
            localStorage.setItem(AGENT_SESSION_STORAGE_KEY, session.id);
            setAgentSessionId(session.id);
          } catch (error) {
            console.error('Failed to create new agent session:', error);
          }
        }}
      />
    );
  }

  // Render chat view
  return (
    <ChatWindow
      sessionId={sessionId}
      messages={messages}
      streamingContent={streamingContent}
      streamingModel={streamingModel}
      isLoading={isLoading}
      isConnecting={!isInitialized}
      onSendMessage={sendMessage}
      onToolConfirm={confirmToolCall}
      connectionStatus={connectionStatus}
      onOpenSettings={() => { setPreviousView('chat'); setView('settings'); }}
      onNewSession={async () => {
        try {
          const session = await createSession('新对话');
          localStorage.setItem(SESSION_STORAGE_KEY, session.id);
        } catch (error) {
          console.error('Failed to create new session:', error);
        }
      }}
    />
  );
}

export default App;
