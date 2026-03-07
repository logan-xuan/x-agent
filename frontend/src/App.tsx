/** X-Agent main application */

import { useEffect, useRef, useState } from 'react';
import './index.css';
import { AgentChatWindow } from './components/agent';
import { SettingsWindow } from './components/settings/SettingsWindow';
import { AdminPanel } from './components/admin/AdminPanel';
import { useAgent } from './hooks/useAgent';

type View = 'agent' | 'settings' | 'admin';

const AGENT_SESSION_STORAGE_KEY = 'x-agent-agent-session-id';

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
        const savedSessionId = localStorage.getItem(AGENT_SESSION_STORAGE_KEY);

        if (savedSessionId) {
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

        const session = await agentCreateSession('Agent 对话');
        localStorage.setItem(AGENT_SESSION_STORAGE_KEY, session.id);
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

  // Save agent session ID
  useEffect(() => {
    if (agentSessionId) {
      localStorage.setItem(AGENT_SESSION_STORAGE_KEY, agentSessionId);
    }
  }, [agentSessionId]);

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
      onSendMessage={agentSendMessage}
      onAbort={agentAbort}
      onClearMessages={agentClearMessages}
      onOpenSettings={() => setView('settings')}
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

export default App;
