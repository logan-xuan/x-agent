/**
 * Agent 消息项组件
 * 
 * 显示单条 Agent 消息，包括用户消息和助手消息。
 */

import { AgentMessage } from '../../hooks/useAgent';
import { AgentToolCallCard } from './AgentToolCallCard';

interface AgentMessageItemProps {
    message: AgentMessage;
    isStreaming?: boolean;
}

// AI 图标
function AIIcon() {
    return (
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/25">
            <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="3" fill="currentColor" />
                <circle cx="12" cy="5" r="1.5" />
                <circle cx="12" cy="19" r="1.5" />
                <circle cx="5" cy="12" r="1.5" />
                <circle cx="19" cy="12" r="1.5" />
                <circle cx="7" cy="7" r="1.5" />
                <circle cx="17" cy="7" r="1.5" />
                <circle cx="7" cy="17" r="1.5" />
                <circle cx="17" cy="17" r="1.5" />
                <path d="M12 5v4M12 15v4M5 12h4M15 12h4M7 7l3 3M14 14l3 3M7 17l3-3M14 10l3-3" opacity="0.6" />
            </svg>
        </div>
    );
}

// 用户图标
function UserIcon() {
    return (
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/25">
            <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="8" r="4" fill="currentColor" />
                <path d="M4 20c0-4 3.5-7 8-7s8 3 8 7" stroke="currentColor" strokeLinecap="round" />
                <path d="M12 16v3M9 18l3 2 3-2" opacity="0.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
        </div>
    );
}

export function AgentMessageItem({ message, isStreaming = false }: AgentMessageItemProps) {
    const isUser = message.role === 'user';
    const hasToolCalls = message.toolCalls && message.toolCalls.length > 0;

    return (
        <div
            className={`flex w-full mb-4 gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
        >
            {/* 头像 */}
            <div className="flex-shrink-0 mt-1">
                {isUser ? <UserIcon /> : <AIIcon />}
            </div>

            {/* 消息气泡 */}
            <div
                className={`max-w-[75%] rounded-2xl px-4 py-3 ${isUser
                    ? 'bg-gradient-to-br from-cyan-500 to-blue-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700'
                    }`}
            >
                {/* 角色标识 */}
                <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-medium ${isUser ? 'text-cyan-100' : 'text-gray-500 dark:text-gray-400'}`}>
                        {isUser ? 'YOU' : 'AGENT'}
                    </span>
                    {message.model && (
                        <span className={`text-xs ${isUser ? 'text-cyan-200/70' : 'text-gray-400 dark:text-gray-500'}`}>
                            · {message.model}
                        </span>
                    )}
                </div>

                {/* 思考内容 (如果有) */}
                {message.thinking && (
                    <details className="mb-2">
                        <summary className="cursor-pointer text-xs text-purple-600 dark:text-purple-400">
                            💭 思考过程
                        </summary>
                        <div className="mt-1 p-2 bg-purple-50 dark:bg-purple-900/20 rounded text-xs text-purple-700 dark:text-purple-300 whitespace-pre-wrap">
                            {message.thinking}
                        </div>
                    </details>
                )}

                {/* 消息内容 */}
                <div className="whitespace-pre-wrap break-words leading-relaxed">
                    {message.content}
                    {isStreaming && (
                        <span className="inline-block w-2 h-4 ml-1 bg-current animate-pulse rounded-sm" />
                    )}
                </div>

                {/* 工具调用 */}
                {hasToolCalls && (
                    <div className="mt-3 space-y-2">
                        {message.toolCalls?.map((toolCall) => (
                            <AgentToolCallCard key={toolCall.id} toolCall={toolCall} />
                        ))}
                    </div>
                )}

                {/* 时间戳 */}
                <div className={`text-xs mt-2 ${isUser ? 'text-cyan-100/60' : 'text-gray-400 dark:text-gray-500'}`}>
                    {new Date(message.createdAt).toLocaleTimeString('zh-CN', {
                        hour: '2-digit',
                        minute: '2-digit',
                    })}
                </div>
            </div>
        </div>
    );
}
