/** Terminal command execution card component */

import { useState } from 'react';
import { ToolCall } from '../../types';

interface TerminalCardProps {
  toolCall: ToolCall;
  onConfirm?: (toolCallId: string, confirmationId?: string, command?: string) => void;
}

/**
 * TerminalCard - Display terminal command execution status and results
 *
 * Status flow:
 * - pending: Waiting to execute
 * - executing: Running (show spinner)
 * - needs_confirmation: High-risk command, needs user confirmation
 * - completed: Success, show output (collapsible)
 * - error: Failed, show error message
 */
export function TerminalCard({ toolCall, onConfirm }: TerminalCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const { arguments: args, status, result } = toolCall;
  const command = (args?.command as string) || '';

  // Determine actual status based on result metadata
  let displayStatus = status;
  if (status === 'error' && result?.requires_confirmation) {
    displayStatus = 'needs_confirmation';
  } else if (status === 'error' && result?.is_blocked) {
    displayStatus = 'blocked';
  }

  // Status icon and color mapping
  const statusConfig: Record<string, { icon: string; color: string; label: string }> = {
    pending: { icon: '⏳', color: 'text-yellow-500', label: '等待执行' },
    executing: { icon: '▶️', color: 'text-blue-500', label: '执行中' },
    needs_confirmation: { icon: '⚠️', color: 'text-orange-500', label: '需要确认' },
    blocked: { icon: '🚫', color: 'text-red-600', label: '已阻止' },
    completed: { icon: result?.success ? '✓' : '✗', color: result?.success ? 'text-green-500' : 'text-red-500', label: result?.success ? '执行成功' : '执行失败' },
    error: { icon: '✗', color: 'text-red-500', label: '执行错误' },
  };

  const config = statusConfig[displayStatus];

  // Format output for display
  const formatOutput = (output: string | undefined): string => {
    if (!output) return '';
    // Limit to 500 chars in collapsed state
    if (!isExpanded && output.length > 500) {
      return output.slice(0, 500) + '\n... (点击展开查看更多)';
    }
    return output;
  };

  // Check if this is a high-risk command that needs confirmation
  const needsConfirmation = displayStatus === 'needs_confirmation';

  // Check if we have output to display
  const hasOutput = result?.output || result?.error;

  return (
    <div className="my-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 overflow-hidden">
      {/* Header - Always visible */}
      <div
        className="flex items-center justify-between px-3 py-2 bg-gray-100 dark:bg-gray-800 cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-750 transition-colors"
        onClick={() => hasOutput && setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <span className="text-lg">🖥️</span>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            终端命令
          </span>
          <span className={`text-sm ${config.color} font-medium`}>
            {config.icon} {config.label}
          </span>
        </div>
        {hasOutput && (
          <button className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
            {isExpanded ? '收起' : '展开'}
          </button>
        )}
      </div>

      {/* Command display */}
      <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700">
        <code className="text-sm font-mono text-gray-800 dark:text-gray-200 bg-gray-200 dark:bg-gray-800 px-2 py-1 rounded block overflow-x-auto">
          {command}
        </code>
      </div>

      {/* Confirmation section for high-risk commands */}
      {needsConfirmation && (
        <div className="px-3 py-3 bg-orange-50 dark:bg-orange-900/20 border-b border-orange-200 dark:border-orange-800">
          <p className="text-sm text-orange-700 dark:text-orange-300 mb-2">
            ⚠️ 这是一个高危命令，需要您的确认才能执行。
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => onConfirm?.(toolCall.id, result?.confirmation_id, command)}
              className="px-4 py-1.5 bg-orange-500 hover:bg-orange-600 text-white text-sm rounded transition-colors"
            >
              确认执行
            </button>
            <button
              onClick={() => setIsExpanded(false)}
              className="px-4 py-1.5 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 text-sm rounded transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* Output section - Collapsible */}
      {isExpanded && hasOutput && (
        <div className="px-3 py-2">
          {result?.error && !result?.output && (
            <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded">
              <span className="font-medium">错误:</span> {result.error}
            </div>
          )}
          {result?.output && (
            <pre className="text-xs font-mono text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 p-2 rounded overflow-x-auto max-h-96 overflow-y-auto whitespace-pre-wrap">
              {formatOutput(result.output)}
            </pre>
          )}
        </div>
      )}

      {/* Executing spinner */}
      {status === 'executing' && (
        <div className="px-3 py-2 flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-gray-600 dark:text-gray-400">正在执行...</span>
        </div>
      )}
    </div>
  );
}

export default TerminalCard;
