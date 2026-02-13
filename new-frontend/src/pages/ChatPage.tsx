import React, { useState, useEffect, useRef } from 'react';
import ChatInterface from '@/components/ChatInterface';

const ChatPage: React.FC = () => {
  const [sessionId] = useState<string>(() => {
    const savedSessionId = localStorage.getItem('x-agent2-session');
    return savedSessionId || `session_${Date.now()}`;
  });

  // Save session ID to localStorage
  useEffect(() => {
    localStorage.setItem('x-agent2-session', sessionId);
  }, [sessionId]);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="glass-effect p-4 backdrop-blur-sm border-b border-slate-700">
        <div className="container mx-auto flex justify-between items-center">
          <div className="flex items-center space-x-2">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-r from-blue-500 to-cyan-400 flex items-center justify-center">
              <span className="text-white font-bold text-lg">XA</span>
            </div>
            <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-cyan-300">
              x-agent2
            </h1>
          </div>
          <div className="text-sm text-slate-400">
            Session: {sessionId.substring(0, 8)}...
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-grow container mx-auto px-4 py-6 max-w-6xl">
        <div className="glass-effect rounded-xl p-6 h-[calc(100vh-200px)] flex flex-col">
          <ChatInterface sessionId={sessionId} />
        </div>
      </main>

      {/* Footer */}
      <footer className="glass-effect p-4 text-center text-xs text-slate-500 border-t border-slate-700">
        x-agent2 - Future AI Assistant • Secure & Private
      </footer>
    </div>
  );
};

export default ChatPage;