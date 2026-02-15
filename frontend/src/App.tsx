/** X-Agent main application */

import { useEffect, useState } from 'react';
import './index.css';
import { ChatWindow } from './components/chat/ChatWindow';
import { SettingsWindow } from './components/settings/SettingsWindow';
import { useChat } from './hooks/useChat';

type View = 'chat' | 'settings';

const SESSION_STORAGE_KEY = 'x-agent-session-id';

function App() {
  const [view, setView] = useState<View>('chat');
  const [isInitialized, setIsInitialized] = useState(false);
  const {
    messages,
    sessionId,
    isLoading,
    streamingContent,
    streamingModel,
    connectionStatus,
    sendMessage,
    createSession,
    loadHistory,
  } = useChat({ sessionId: null });

  // Initialize session on mount
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

  // Save session ID when it changes
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    }
  }, [sessionId]);

  // Render settings view
  if (view === 'settings') {
    return <SettingsWindow onClose={() => setView('chat')} />;
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
      connectionStatus={connectionStatus}
      onOpenSettings={() => setView('settings')}
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
