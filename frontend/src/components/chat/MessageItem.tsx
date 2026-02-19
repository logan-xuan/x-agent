/** Individual message display component */

import { Message } from '../../types';
import { TerminalCard } from './TerminalCard';

interface MessageItemProps {
  message: Message;
  isStreaming?: boolean;
  onToolConfirm?: (toolCallId: string, confirmationId?: string, command?: string) => void;
}

// AI Icon - 未来感神经网络/AI风格
function AIIcon() {
  return (
    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/25">
      <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        {/* 中心核心 */}
        <circle cx="12" cy="12" r="3" fill="currentColor" />
        {/* 神经网络节点 */}
        <circle cx="12" cy="5" r="1.5" />
        <circle cx="12" cy="19" r="1.5" />
        <circle cx="5" cy="12" r="1.5" />
        <circle cx="19" cy="12" r="1.5" />
        <circle cx="7" cy="7" r="1.5" />
        <circle cx="17" cy="7" r="1.5" />
        <circle cx="7" cy="17" r="1.5" />
        <circle cx="17" cy="17" r="1.5" />
        {/* 连接线 */}
        <path d="M12 5v4M12 15v4M5 12h4M15 12h4M7 7l3 3M14 14l3 3M7 17l3-3M14 10l3-3" opacity="0.6" />
      </svg>
    </div>
  );
}

// User Icon - 未来感简约用户图标
function UserIcon() {
  return (
    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/25">
      <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        {/* 头部 */}
        <circle cx="12" cy="8" r="4" fill="currentColor" />
        {/* 身体 - 六边形风格 */}
        <path 
          d="M4 20c0-4 3.5-7 8-7s8 3 8 7" 
          stroke="currentColor" 
          strokeLinecap="round"
        />
        {/* 科技感装饰线 */}
        <path 
          d="M12 16v3M9 18l3 2 3-2" 
          opacity="0.5" 
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export function MessageItem({ message, isStreaming = false, onToolConfirm }: MessageItemProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const hasToolCalls = message.tool_calls && message.tool_calls.length > 0;

  // System message styling
  if (isSystem) {
    return (
      <div className="flex w-full mb-2">
        <details className="w-full text-xs">
          <summary className="cursor-pointer text-yellow-700 dark:text-yellow-400 font-mono select-none flex items-center gap-2">
            <span>🔧 System Log: {message.metadata?.log_type || 'info'}</span>
            <span className="text-gray-500 dark:text-gray-600">▼</span>
          </summary>
          <pre className="mt-2 p-3 bg-black/10 dark:bg-white/5 rounded border-l-4 border-yellow-500 overflow-auto text-xs font-mono whitespace-pre-wrap break-all">
            {message.content}
          </pre>
        </details>
      </div>
    );
  }

  return (
    <div
      className={`flex w-full mb-4 gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {/* Avatar */}
      <div className="flex-shrink-0 mt-1">
        {isUser ? <UserIcon /> : <AIIcon />}
      </div>

      {/* Message bubble */}
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'bg-gradient-to-br from-cyan-500 to-blue-600 text-white'
            : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700'
        }`}
      >
        {/* Role indicator */}
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-medium ${isUser ? 'text-cyan-100' : 'text-gray-500 dark:text-gray-400'}`}>
            {isUser ? 'YOU' : 'X-AGENT'}
          </span>
          {message.metadata?.model && (
            <span className={`text-xs ${isUser ? 'text-cyan-200/70' : 'text-gray-400 dark:text-gray-500'}`}>
              · {message.metadata.model}
            </span>
          )}
        </div>

        {/* Message content */}
        <div className="whitespace-pre-wrap break-words leading-relaxed">
          {message.content}
          {isStreaming && (
            <span className="inline-block w-2 h-4 ml-1 bg-current animate-pulse rounded-sm" />
          )}
        </div>

        {/* Tool calls - Terminal cards */}
        {hasToolCalls && (
          <div className="mt-3 space-y-2">
            {message.tool_calls?.map((toolCall) => (
              <TerminalCard
                key={toolCall.id}
                toolCall={toolCall}
                onConfirm={(id, confirmationId, command) => onToolConfirm?.(id, confirmationId, command)}
              />
            ))}
          </div>
        )}

        {/* Timestamp */}
        <div className={`text-xs mt-2 ${isUser ? 'text-cyan-100/60' : 'text-gray-400 dark:text-gray-500'}`}>
          {new Date(message.created_at).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
    </div>
  );
}
