/**
 * Agent 消息列表组件
 * 
 * 显示所有 Agent 消息，包括流式输出。
 */

import { useRef, useEffect } from 'react';
import { AgentMessage } from '../../hooks/useAgent';
import { AgentMessageItem } from './AgentMessageItem';

interface AgentMessageListProps {
    messages: AgentMessage[];
    streamingContent?: string;
    streamingThinking?: string;
    streamingModel?: string;
    isLoading?: boolean;
}

export function AgentMessageList({
    messages,
    streamingContent,
    streamingThinking,
    streamingModel,
    isLoading = false,
}: AgentMessageListProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const bottomRef = useRef<HTMLDivElement>(null);

    // 自动滚动到底部
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, streamingContent]);

    // 流式消息
    const streamingMessage: AgentMessage | null = streamingContent || streamingThinking
        ? {
            id: 'streaming',
            sessionId: '',
            role: 'assistant',
            content: streamingContent || '',
            createdAt: new Date().toISOString(),
            model: streamingModel,
            thinking: streamingThinking,
        }
        : null;

    return (
        <div
            ref={containerRef}
            className="flex-1 overflow-y-auto px-4 py-4"
        >
            {/* 空状态 */}
            {messages.length === 0 && !streamingMessage && (
                <div className="flex flex-col items-center justify-center h-full text-center">
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center mb-4 shadow-lg shadow-violet-500/25">
                        <svg className="w-8 h-8 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <circle cx="12" cy="12" r="3" fill="currentColor" />
                            <circle cx="12" cy="5" r="1.5" />
                            <circle cx="12" cy="19" r="1.5" />
                            <circle cx="5" cy="12" r="1.5" />
                            <circle cx="19" cy="12" r="1.5" />
                        </svg>
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                        Agent Core
                    </h3>
                    <p className="text-gray-500 dark:text-gray-400 max-w-sm">
                        使用新的 Agent Core 架构进行对话。
                        输入消息开始交互。
                    </p>
                </div>
            )}

            {/* 消息列表 */}
            {messages.map((message) => (
                <AgentMessageItem key={message.id} message={message} />
            ))}

            {/* 流式消息 */}
            {streamingMessage && (
                <AgentMessageItem message={streamingMessage} isStreaming={true} />
            )}

            {/* 加载指示器 */}
            {isLoading && !streamingMessage && (
                <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 mb-4">
                    <div className="flex gap-1">
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    <span className="text-sm">Agent 正在思考...</span>
                </div>
            )}

            {/* 滚动锚点 */}
            <div ref={bottomRef} />
        </div>
    );
}
