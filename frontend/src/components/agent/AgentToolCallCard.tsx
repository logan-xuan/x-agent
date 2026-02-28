/**
 * Agent 工具调用卡片组件
 * 
 * 显示工具调用的状态和结果。
 */

import { AgentToolCall } from '../../hooks/useAgent';

interface AgentToolCallCardProps {
    toolCall: AgentToolCall;
}

export function AgentToolCallCard({ toolCall }: AgentToolCallCardProps) {
    const statusConfig = {
        executing: {
            icon: '⏳',
            text: '执行中...',
            bgClass: 'bg-yellow-50 dark:bg-yellow-900/20',
            borderClass: 'border-yellow-200 dark:border-yellow-800',
        },
        completed: {
            icon: '✅',
            text: '已完成',
            bgClass: 'bg-green-50 dark:bg-green-900/20',
            borderClass: 'border-green-200 dark:border-green-800',
        },
        error: {
            icon: '❌',
            text: '错误',
            bgClass: 'bg-red-50 dark:bg-red-900/20',
            borderClass: 'border-red-200 dark:border-red-800',
        },
    };

    const config = statusConfig[toolCall.status] || statusConfig.executing;

    return (
        <div className={`rounded-lg border p-3 text-sm ${config.bgClass} ${config.borderClass}`}>
            {/* Header */}
            <div className="flex items-center gap-2 mb-2">
                <span>{config.icon}</span>
                <span className="font-mono font-medium text-gray-700 dark:text-gray-300">
                    {toolCall.name}
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                    {config.text}
                </span>
                {toolCall.durationMs && (
                    <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
                        {toolCall.durationMs}ms
                    </span>
                )}
            </div>

            {/* Arguments */}
            {Object.keys(toolCall.arguments).length > 0 && (
                <details className="mb-2">
                    <summary className="cursor-pointer text-xs text-gray-500 dark:text-gray-400">
                        参数
                    </summary>
                    <pre className="mt-1 p-2 bg-black/5 dark:bg-white/5 rounded text-xs overflow-auto">
                        {JSON.stringify(toolCall.arguments, null, 2)}
                    </pre>
                </details>
            )}

            {/* Result */}
            {toolCall.result && (
                <div className="mt-2">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">结果:</div>
                    <pre className="p-2 bg-black/5 dark:bg-white/5 rounded text-xs overflow-auto max-h-32 whitespace-pre-wrap">
                        {toolCall.result}
                    </pre>
                </div>
            )}
        </div>
    );
}
