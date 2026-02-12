import React, { useState, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import ChatInterface from '../components/ChatInterface';
import TaskVisualization from '../components/TaskVisualization';
import SubAgentControls from '../components/SubAgentControls';
import HeartbeatMonitor from '../components/HeartbeatMonitor';
import { chatService } from '../services/chatService';

const ChatPage: React.FC = () => {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const [currentSessionId, setCurrentSessionId] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Initialize session
  useEffect(() => {
    const initSession = async () => {
      try {
        let sid = sessionId;

        // If no session ID provided, create a new one
        if (!sid) {
          const response = await chatService.createSession();
          sid = response.sessionId;
          setCurrentSessionId(sid);
        } else {
          setCurrentSessionId(sid);
        }

        setIsLoading(false);
      } catch (err) {
        setError('Failed to initialize session');
        console.error('Session initialization error:', err);
        setIsLoading(false);
      }
    };

    initSession();

    // Cleanup on unmount
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [sessionId]);

  // Establish WebSocket connection
  useEffect(() => {
    if (currentSessionId) {
      try {
        wsRef.current = chatService.connectWebSocket(currentSessionId);

        // Handle WebSocket messages
        wsRef.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            // Handle different message types
            if (data.type === 'heartbeat') {
              // Handle heartbeat updates
              console.log('Received heartbeat:', data);
            } else if (data.type === 'assistant_response') {
              // Handle assistant responses
              console.log('Received response:', data);
            } else if (data.type === 'system') {
              // Handle system messages
              console.log('System message:', data);
            }
          } catch (error) {
            console.error('Error parsing WebSocket message:', error);
          }
        };

        wsRef.current.onclose = () => {
          console.log('WebSocket connection closed');
        };

        wsRef.current.onerror = (error) => {
          console.error('WebSocket error:', error);
        };
      } catch (error) {
        console.error('Failed to establish WebSocket connection:', error);
      }
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [currentSessionId]);

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
          <strong className="font-bold">Error! </strong>
          <span className="block sm:inline">{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Navigation Bar */}
      <nav className="bg-white shadow-md p-4">
        <div className="container mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold text-gray-800">x-agent2 AI Assistant</h1>
          <div className="flex items-center space-x-4">
            <span className="text-sm text-gray-600">Session: {currentSessionId.substring(0, 8)}...</span>
            <button
              className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
              onClick={() => {
                if (wsRef.current?.readyState === WebSocket.OPEN) {
                  wsRef.current.close();
                }
                chatService.endSession(currentSessionId);
              }}
            >
              End Session
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel - Main Chat Interface */}
        <div className="flex-1 flex flex-col">
          <div className="p-4 bg-white border-b">
            <h2 className="text-lg font-semibold text-gray-800">Chat Interface</h2>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <ChatInterface sessionId={currentSessionId} />
          </div>
        </div>

        {/* Right Panel - Controls and Monitoring */}
        <div className="w-96 bg-white border-l flex flex-col">
          {/* SubAgent Controls */}
          <div className="border-b p-4">
            <h3 className="font-medium text-gray-800 mb-2">SubAgent Controls</h3>
            <SubAgentControls sessionId={currentSessionId} />
          </div>

          {/* Task Visualization */}
          <div className="border-b p-4 flex-1 overflow-y-auto">
            <h3 className="font-medium text-gray-800 mb-2">Task Visualization</h3>
            <TaskVisualization sessionId={currentSessionId} />
          </div>

          {/* Heartbeat Monitor */}
          <div className="p-4">
            <h3 className="font-medium text-gray-800 mb-2">Task Monitor</h3>
            <HeartbeatMonitor />
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-white border-t p-2 text-center text-sm text-gray-500">
        x-agent2 AI Assistant System • Secure and Private AI Interaction
      </footer>
    </div>
  );
};

export default ChatPage;