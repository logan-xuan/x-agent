/** Compression Record Query - View compression history and details */

import { useState, useEffect } from 'react';
import { Button } from '../ui/Button';
import { queryCompressionRecords, type CompressionRecordQueryResponse } from '../../services/api';

interface CompressionRecord {
  id: string;
  sessionId: string;
  originalMessageCount: number;
  compressedMessageCount: number;
  originalTokenCount: number;
  compressedTokenCount: number;
  compressionRatio: number;
  compressionTime: string;
  originalMessages: Array<{
    role: string;
    content: string;
    timestamp?: string;
  }>;
  compressedMessages: Array<{
    role: string;
    content: string;
    timestamp?: string;
  }>;
}

interface CompressionRecordQueryProps {
  onError?: (error: string) => void;
}

export function CompressionRecordQuery({ onError }: CompressionRecordQueryProps) {
  const [records, setRecords] = useState<CompressionRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<CompressionRecord | null>(null);
  const [expandedView, setExpandedView] = useState<'original' | 'compressed' | null>(null);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0
  });

  // Load compression records on mount
  useEffect(() => {
    loadCompressionRecords();
  }, [pagination.page]);

  const loadCompressionRecords = async () => {
    try {
      setIsLoading(true);
      const response = await queryCompressionRecords({
        limit: pagination.limit,
        offset: (pagination.page - 1) * pagination.limit
      });

      setRecords(response.records as CompressionRecord[]);
      setPagination(prev => ({
        ...prev,
        total: response.total
      }));
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '加载压缩记录失败';
      onError?.(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString('zh-CN');
  };

  const formatTokenCount = (count: number) => {
    return count.toLocaleString();
  };

  const totalPages = Math.ceil(pagination.total / pagination.limit);

  const goToPage = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      setPagination(prev => ({ ...prev, page }));
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
        <div>
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            压缩记录查询
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            查看上下文压缩的历史记录及详情
          </p>
        </div>
        <Button
          onClick={loadCompressionRecords}
          disabled={isLoading}
          className="text-xs"
        >
          {isLoading ? (
            <>
              <svg className="animate-spin -ml-1 mr-2 h-3 w-3" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              加载中...
            </>
          ) : (
            '刷新'
          )}
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Records List */}
        <div className="w-80 border-r border-gray-200 dark:border-gray-700 overflow-y-auto">
          {isLoading ? (
            <div className="p-4 text-center text-sm text-gray-500">
              加载中...
            </div>
          ) : records.length === 0 ? (
            <div className="p-4 text-center text-sm text-gray-500">
              暂无压缩记录
            </div>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {records.map((record) => (
                <div
                  key={record.id}
                  className={`p-4 cursor-pointer transition-colors ${
                    selectedRecord?.id === record.id
                      ? 'bg-blue-50 dark:bg-blue-900/20'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                  }`}
                  onClick={() => setSelectedRecord(record)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                        会话: {record.sessionId}
                      </h4>
                      <div className="mt-1 grid grid-cols-2 gap-1 text-xs text-gray-500 dark:text-gray-400">
                        <div>原始: {record.originalMessageCount === -1 ? '?' : record.originalMessageCount}条</div>
                        <div>压缩: {record.compressedMessageCount}条</div>
                        <div>原Token: {formatTokenCount(record.originalTokenCount)}</div>
                        <div>压Token: {formatTokenCount(record.compressedTokenCount)}</div>
                      </div>
                      <div className="mt-2 flex items-center gap-2">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                          压缩率 {(record.compressionRatio * 100).toFixed(1)}%
                        </span>
                        <span className="text-xs text-gray-400">
                          {formatTimestamp(record.compressionTime)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="border-t border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  第 {pagination.page}/{totalPages} 页
                </span>
                <div className="flex space-x-2">
                  <Button
                    onClick={() => goToPage(pagination.page - 1)}
                    disabled={pagination.page === 1}
                    variant="outline"
                    size="sm"
                    className="text-xs"
                  >
                    上一页
                  </Button>
                  <span className="flex items-center px-2 text-sm text-gray-700 dark:text-gray-300">
                    {pagination.page}
                  </span>
                  <Button
                    onClick={() => goToPage(pagination.page + 1)}
                    disabled={pagination.page >= totalPages}
                    variant="outline"
                    size="sm"
                    className="text-xs"
                  >
                    下一页
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Record Detail View */}
        <div className="flex-1 flex flex-col bg-white dark:bg-gray-900 overflow-hidden">
          {selectedRecord ? (
            <>
              <div className="border-b border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-medium text-gray-900 dark:text-gray-100">
                      压缩记录详情: {selectedRecord.id}
                    </h4>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      会话ID: {selectedRecord.sessionId}
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                      注: 显示的是压缩操作的统计信息。由于系统设计，压缩前后的实际消息内容并未持久化存储，仅显示压缩过程说明。
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
                      原始: {selectedRecord.originalMessageCount === -1 ? '?' : selectedRecord.originalMessageCount}条消息
                    </span>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                      压缩: {selectedRecord.compressedMessageCount}条消息
                    </span>
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-4 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">原始Token:</span>
                    <span className="ml-1 font-medium">{formatTokenCount(selectedRecord.originalTokenCount)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">压缩Token:</span>
                    <span className="ml-1 font-medium">{formatTokenCount(selectedRecord.compressedTokenCount)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">压缩率:</span>
                    <span className="ml-1 font-medium">{(selectedRecord.compressionRatio * 100).toFixed(1)}%</span>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">时间:</span>
                    <span className="ml-1 font-medium">{formatTimestamp(selectedRecord.compressionTime)}</span>
                  </div>
                </div>
              </div>

              {/* Tabs for Original vs Compressed */}
              <div className="border-b border-gray-200 dark:border-gray-700">
                <nav className="flex space-x-4 px-4" aria-label="Tabs">
                  <button
                    onClick={() => setExpandedView(expandedView === 'original' ? null : 'original')}
                    className={`py-2 px-1 text-sm font-medium border-b-2 ${
                      expandedView === 'original'
                        ? 'border-blue-500 text-blue-600 dark:text-blue-400 dark:border-blue-400'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
                    }`}
                  >
                    原始对话 ({selectedRecord.originalMessageCount === -1 ? '?' : selectedRecord.originalMessageCount})
                  </button>
                  <button
                    onClick={() => setExpandedView(expandedView === 'compressed' ? null : 'compressed')}
                    className={`py-2 px-1 text-sm font-medium border-b-2 ${
                      expandedView === 'compressed'
                        ? 'border-blue-500 text-blue-600 dark:text-blue-400 dark:border-blue-400'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
                    }`}
                  >
                    压缩后对话 ({selectedRecord.compressedMessageCount})
                  </button>
                </nav>
              </div>

              <div className="flex-1 overflow-auto">
                {expandedView === 'original' && (
                  <div className="p-4 space-y-4">
                    <h5 className="font-medium text-gray-900 dark:text-gray-100">原始对话记录</h5>
                    {selectedRecord.originalMessages.map((msg, idx) => (
                      <div key={idx} className={`p-3 rounded-lg ${msg.role === 'user' ? 'bg-blue-50 dark:bg-blue-900/20' : 'bg-gray-50 dark:bg-gray-800'}`}>
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            msg.role === 'user'
                              ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
                              : 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                          }`}>
                            {msg.role === 'user' ? '用户' : '助手'}
                          </span>
                          {msg.timestamp && (
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              {formatTimestamp(msg.timestamp)}
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                          {msg.content}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {expandedView === 'compressed' && (
                  <div className="p-4 space-y-4">
                    <h5 className="font-medium text-gray-900 dark:text-gray-100">压缩后对话</h5>
                    {selectedRecord.compressedMessages.map((msg, idx) => (
                      <div key={idx} className={`p-3 rounded-lg ${msg.role === 'user' ? 'bg-green-50 dark:bg-green-900/20' : 'bg-gray-50 dark:bg-gray-800'}`}>
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            msg.role === 'user'
                              ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                              : 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                          }`}>
                            {msg.role === 'user' ? '用户' : '助手'}
                          </span>
                          {msg.timestamp && (
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              {formatTimestamp(msg.timestamp)}
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                          {msg.content}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {!expandedView && (
                  <div className="p-8 text-center text-gray-500 dark:text-gray-400">
                    <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                    <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">选择查看方式</h3>
                    <p className="mt-1 text-sm">点击上方标签查看原始对话或压缩后对话详情</p>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center p-8 text-gray-500 dark:text-gray-400">
              <div className="text-center">
                <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">未选择记录</h3>
                <p className="mt-1 text-sm">从左侧列表中选择一个压缩记录查看详情</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}