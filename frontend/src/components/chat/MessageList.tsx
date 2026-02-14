/** Message history list component */

import { useEffect, useRef } from 'react';
import { Message } from '../../types';
import { MessageItem } from './MessageItem';

interface MessageListProps {
  messages: Message[];
  streamingContent?: string;
  streamingModel?: string;
  isLoading?: boolean;
}

export function MessageList({ 
  messages, 
  streamingContent, 
  streamingModel,
  isLoading = false 
}: MessageListProps) {
  const listEndRef = useRef<HTMLDivElement>(null);
  
  // Auto-scroll to bottom on new messages
  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);
  
  // Create a temporary streaming message if content is being streamed
  const streamingMessage: Message | null = streamingContent ? {
    id: 'streaming',
    session_id: '',
    role: 'assistant',
    content: streamingContent,
    created_at: new Date().toISOString(),
    metadata: streamingModel ? { model: streamingModel } : undefined,
  } : null;
  
  return (
    <div className="h-full overflow-y-auto p-4 space-y-2 min-h-0">
      {/* Empty state */}
      {messages.length === 0 && !streamingMessage && !isLoading && (
        <div className="flex flex-col items-center justify-center h-full text-gray-500 dark:text-gray-400">
          <svg
            className="w-16 h-16 mb-4 opacity-50"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
          <p className="text-lg font-medium">开始对话</p>
          <p className="text-sm opacity-70">发送消息开始与 AI 助手对话</p>
        </div>
      )}
      
      {/* Message list */}
      {messages.map((message) => (
        <MessageItem key={message.id} message={message} />
      ))}
      
      {/* Streaming message */}
      {streamingMessage && (
        <MessageItem message={streamingMessage} isStreaming />
      )}
      
      {/* Loading indicator */}
      {isLoading && !streamingMessage && (
        <div className="flex justify-start mb-4">
          <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-sm text-gray-500">AI 正在思考...</span>
            </div>
          </div>
        </div>
      )}
      
      {/* Scroll anchor */}
      <div ref={listEndRef} />
    </div>
  );
}
