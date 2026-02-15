/** Prompt Log List Component - Displays LLM interaction logs */

import { useState, useEffect, useCallback } from 'react';
import type { PromptLogEntry } from '@/types';
import { getPromptLogs } from '@/services/api';
import { Spinner } from '../ui/Spinner';
import { Button } from '../ui/Button';

interface PromptLogListProps {
  onError?: (error: string) => void;
  onViewTrace?: (traceId: string) => void;
}

export function PromptLogList({ onError, onViewTrace }: PromptLogListProps) {
  const [logs, setLogs] = useState<PromptLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getPromptLogs(20);
      setLogs(response.logs);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Failed to fetch logs');
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
    });
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const toggleExpand = (timestamp: string) => {
    setExpandedId(expandedId === timestamp ? null : timestamp);
  };

  if (loading && logs.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
          最近 {logs.length} 条交互记录
        </h3>
        <Button variant="ghost" size="sm" onClick={fetchLogs} disabled={loading}>
          {loading ? <Spinner size="sm" /> : '刷新'}
        </Button>
      </div>

      {/* Log List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {logs.length === 0 ? (
          <div className="text-center text-gray-500 dark:text-gray-400 py-8">
            暂无交互记录
          </div>
        ) : (
          logs.map((log, index) => {
            const isExpanded = expandedId === log.timestamp;
            const hasError = !log.success || log.error;

            return (
              <div
                key={`${log.timestamp}-${index}`}
                className={`border rounded-lg overflow-hidden transition-all ${
                  hasError
                    ? 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/10'
                    : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'
                }`}
              >
                {/* Summary Row */}
                <button
                  onClick={() => toggleExpand(log.timestamp)}
                  className="w-full p-3 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                >
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    {/* Status Icon */}
                    <div
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        log.success ? 'bg-green-500' : 'bg-red-500'
                      }`}
                    />

                    {/* Time */}
                    <div className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
                      <div>{formatDate(log.timestamp)}</div>
                      <div>{formatTime(log.timestamp)}</div>
                    </div>

                    {/* Model */}
                    <div className="text-xs font-mono text-gray-600 dark:text-gray-300 truncate max-w-[120px]">
                      {log.model}
                    </div>

                    {/* Latency */}
                    <div className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
                      {log.latency_ms}ms
                    </div>

                    {/* Token Usage */}
                    {log.token_usage && (
                      <div className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0 hidden sm:block">
                        {log.token_usage.prompt_tokens} → {log.token_usage.completion_tokens}
                        <span className="text-gray-400">({log.token_usage.total_tokens})</span>
                      </div>
                    )}
                  </div>

                  {/* Expand Icon */}
                  <svg
                    className={`w-4 h-4 text-gray-400 transition-transform ${
                      isExpanded ? 'rotate-180' : ''
                    }`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 9l-7 7-7-7"
                    />
                  </svg>
                </button>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-gray-200 dark:border-gray-700 p-3 space-y-3">
                    {/* Metadata */}
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="text-gray-500 dark:text-gray-400">
                        Provider: <span className="text-gray-700 dark:text-gray-300">{log.provider}</span>
                      </div>
                      <div className="text-gray-500 dark:text-gray-400">
                        Session:{' '}
                        <span className="text-gray-700 dark:text-gray-300 font-mono">
                          {log.session_id?.slice(0, 8) || 'N/A'}...
                        </span>
                      </div>
                      {log.trace_id && (
                        <div className="text-gray-500 dark:text-gray-400 col-span-2 flex items-center justify-between">
                          <div>
                            Trace:{' '}
                            <span className="text-gray-700 dark:text-gray-300 font-mono">
                              {log.trace_id}
                            </span>
                          </div>
                          {onViewTrace && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-6 text-xs"
                              onClick={() => onViewTrace(log.trace_id!)}
                            >
                              查看Trace
                            </Button>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Request Messages */}
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
                          请求 ({log.request.message_count} 条消息)
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 text-xs"
                          onClick={() => copyToClipboard(JSON.stringify(log.request.messages, null, 2))}
                        >
                          复制
                        </Button>
                      </div>
                      <pre className="text-xs bg-gray-100 dark:bg-gray-900 p-2 rounded overflow-auto max-h-40 text-gray-700 dark:text-gray-300">
                        {JSON.stringify(log.request.messages, null, 2)}
                      </pre>
                    </div>

                    {/* Response */}
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
                          响应
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 text-xs"
                          onClick={() => copyToClipboard(log.response)}
                        >
                          复制
                        </Button>
                      </div>
                      <pre className="text-xs bg-gray-100 dark:bg-gray-900 p-2 rounded overflow-auto max-h-40 text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                        {log.response}
                      </pre>
                    </div>

                    {/* Error */}
                    {log.error && (
                      <div className="bg-red-100 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-2">
                        <div className="text-xs font-medium text-red-600 dark:text-red-400 mb-1">
                          错误
                        </div>
                        <pre className="text-xs text-red-700 dark:text-red-300 whitespace-pre-wrap">
                          {log.error}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
