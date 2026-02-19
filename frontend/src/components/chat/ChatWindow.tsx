/** Main chat container component */

import { useState, useEffect } from 'react';
import { Message } from '../../types';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { Spinner } from '../ui/Spinner';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { DevModeWindow } from '../dev/DevModeWindow';
import { Skill } from '@/services/api';
import { listSkills } from '@/services/api';

interface ChatWindowProps {
  sessionId: string | null;
  messages: Message[];
  streamingContent?: string;
  streamingModel?: string;
  isLoading?: boolean;
  isConnecting?: boolean;
  onSendMessage: (content: string) => void;
  onToolConfirm?: (toolCallId: string, confirmationId?: string, command?: string) => void;
  connectionStatus?: 'connected' | 'connecting' | 'disconnected';
  onOpenSettings?: () => void;
  onNewSession?: () => void;
}

export function ChatWindow({
  sessionId,
  messages,
  streamingContent,
  streamingModel,
  isLoading = false,
  isConnecting = false,
  onSendMessage,
  onToolConfirm,
  connectionStatus = 'disconnected',
  onOpenSettings,
  onNewSession,
}: ChatWindowProps) {
  // Developer mode state
  const [isDevModeOpen, setIsDevModeOpen] = useState(false);
  
  // Skills state
  const [skills, setSkills] = useState<Skill[]>([]);
  const [isLoadingSkills, setIsLoadingSkills] = useState(true);

  // Load skills on mount
  useEffect(() => {
    async function loadSkills() {
      try {
        setIsLoadingSkills(true);
        const loadedSkills = await listSkills();
        setSkills(loadedSkills);
      } catch (error) {
        console.error('Failed to load skills:', error);
      } finally {
        setIsLoadingSkills(false);
      }
    }
    
    loadSkills();
  }, []);

  // Connection status indicator
  const getStatusConfig = () => {
    switch (connectionStatus) {
      case 'connected':
        return { variant: 'success' as const, label: '已连接', dotClass: 'bg-green-500' };
      case 'connecting':
        return { variant: 'warning' as const, label: '连接中...', dotClass: 'bg-yellow-500 animate-pulse' };
      case 'disconnected':
        return { variant: 'destructive' as const, label: '已断开', dotClass: 'bg-red-500' };
    }
  };
  
  const statusConfig = getStatusConfig();
  
  return (
    <div className="flex flex-col h-screen bg-white dark:bg-gray-900 safe-area-inset-top">
      {/* Header */}
      <header className="chat-header flex-shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 sm:px-4 py-2 sm:py-3">
        <div className="flex items-center justify-between max-w-3xl mx-auto">
          <div className="flex items-center gap-2 sm:gap-3">
            <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white">
              X-Agent
            </h1>
            {sessionId && (
              <span className="text-xs text-gray-400 font-mono hidden sm:inline">
                {sessionId.slice(0, 8)}...
              </span>
            )}
          </div>
          
          {/* Connection status */}
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="flex items-center gap-1 sm:gap-2">
              <div className={`w-2 h-2 rounded-full ${statusConfig.dotClass}`} />
              <Badge variant={statusConfig.variant} className="text-xs sm:text-sm">{statusConfig.label}</Badge>
            </div>
            
            {/* Developer mode button */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsDevModeOpen(true)}
              className="touch-target text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
              title="开发者模式"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
            </Button>

            {/* New Session button */}
            {onNewSession && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onNewSession}
                className="touch-target text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
                title="新建会话"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
              </Button>
            )}

            {/* Settings button */}
            {onOpenSettings && (
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={onOpenSettings} 
                className="touch-target text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </Button>
            )}
          </div>
        </div>
      </header>
      
      {/* Connecting overlay */}
      {isConnecting && (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <Spinner size="lg" className="text-blue-600" />
            <p className="text-gray-500 dark:text-gray-400">正在初始化会话...</p>
          </div>
        </div>
      )}
      
      {/* Disconnected overlay */}
      {!isConnecting && connectionStatus === 'disconnected' && sessionId && (
        <div className="absolute inset-0 top-14 bg-white/80 dark:bg-gray-900/80 flex items-center justify-center z-10">
          <div className="flex flex-col items-center gap-4 text-center">
            <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <svg className="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414" />
              </svg>
            </div>
            <div>
              <p className="font-medium text-gray-900 dark:text-white">连接已断开</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">正在尝试重新连接...</p>
            </div>
          </div>
        </div>
      )}
      
      {/* Message list - constrained width */}
      {!isConnecting && (
        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="h-full max-w-3xl mx-auto flex flex-col">
            <MessageList
              messages={messages}
              streamingContent={streamingContent}
              streamingModel={streamingModel}
              isLoading={isLoading}
              onToolConfirm={onToolConfirm}
            />
          </div>
        </div>
      )}
      
      {/* Input - constrained width */}
      <div className="message-input-container flex-shrink-0 border-t border-gray-200 dark:border-gray-700 safe-area-inset-bottom">
        <div className="max-w-3xl mx-auto px-2 sm:px-0">
          <MessageInput
            onSend={onSendMessage}
            disabled={isConnecting || !sessionId || connectionStatus !== 'connected'}
            placeholder={
              isConnecting ? '正在连接...' : 
              connectionStatus !== 'connected' ? '等待连接...' : 
              isLoadingSkills ? '加载技能...' : '输入消息... (输入 / 显示技能菜单)'
            }
            skills={skills}
          />
        </div>
      </div>

      {/* Developer Mode Window */}
      <DevModeWindow isOpen={isDevModeOpen} onClose={() => setIsDevModeOpen(false)} />
    </div>
  );
}
