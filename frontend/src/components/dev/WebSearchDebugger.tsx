/** Web Search debugger component for developer mode (Aliyun OpenSearch) */
import { useState } from 'react';
import type { FormEvent } from 'react';

interface WebSearchResult {
  title: string;
  snippet: string;
  url: string;
}

interface WebSearchResponse {
  success: boolean;
  query: string;
  results: WebSearchResult[];
  output?: string | null;
  error?: string | null;
  metadata?: Record<string, any> | null;
}

interface WebSearchDebuggerProps {
  onError?: (error: string) => void;
}

export function WebSearchDebugger({ onError }: WebSearchDebuggerProps) {
  const [query, setQuery] = useState('');
  const [maxResults, setMaxResults] = useState(5);
  const [searchResponse, setSearchResponse] = useState<WebSearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRawOutput, setShowRawOutput] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) {
      setError('请输入搜索查询');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/v1/dev/web-search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: query,
          max_results: maxResults,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || '搜索失败');
      }

      const data: WebSearchResponse = await response.json();
      setSearchResponse(data);
      
      if (!data.success) {
        setError(data.error || '搜索返回失败状态');
        onError?.(data.error || '搜索失败');
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '搜索失败';
      setError(errorMessage);
      onError?.(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleSearch();
  };

  const formatUrl = (url: string) => {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname;
    } catch {
      return url;
    }
  };

  return (
    <div className="flex flex-col h-full p-4">
      <h3 className="text-lg font-semibold mb-4">🔍 Web Search 调试器 (Aliyun OpenSearch)</h3>

      {/* Search Form */}
      <form onSubmit={handleSubmit} className="mb-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            搜索查询 *
          </label>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入搜索关键词，例如：Python programming language..."
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            disabled={isLoading}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="md:col-span-3">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              最大结果数
            </label>
            <input
              type="number"
              min="1"
              max="20"
              value={maxResults}
              onChange={(e) => setMaxResults(parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              disabled={isLoading}
            />
          </div>

          <div className="flex items-end">
            <button
              type="submit"
              disabled={isLoading || !query.trim()}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? '搜索中...' : '搜索'}
            </button>
          </div>
        </div>
      </form>

      {/* Info Banner */}
      <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md">
        <p className="text-sm text-blue-800 dark:text-blue-300">
          <strong>说明：</strong>使用阿里云 OpenSearch 进行高质量网络搜索。
          支持中英文查询，提供实时、权威的信息检索结果。
          适用于需要最新信息的各类查询场景。
        </p>
      </div>

      {/* Error Display */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
          <p className="text-red-600 dark:text-red-400 text-sm">{error}</p>
        </div>
      )}

      {/* Search Results */}
      {searchResponse && (
        <div className="flex-1 overflow-hidden flex flex-col">
          {/* Response Header */}
          <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-md">
            <div className="flex justify-between items-center">
              <div>
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  搜索查询："{searchResponse.query}"
                </p>
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                  状态：{searchResponse.success ? (
                    <span className="text-green-600 dark:text-green-400">成功</span>
                  ) : (
                    <span className="text-red-600 dark:text-red-400">失败</span>
                  )}
                  {searchResponse.metadata && (
                    <span className="ml-2">
                      · 结果数：{searchResponse.metadata.results_count || searchResponse.results.length}
                    </span>
                  )}
                </p>
              </div>

              {/* Toggle Raw Output */}
              {searchResponse.output && (
                <button
                  onClick={() => setShowRawOutput(!showRawOutput)}
                  className="px-3 py-1.5 text-xs bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                >
                  {showRawOutput ? '查看解析结果' : '查看原始输出'}
                </button>
              )}
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto">
            {showRawOutput && searchResponse.output ? (
              /* Raw Output View */
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  原始格式化输出
                </h4>
                <pre className="text-xs bg-gray-100 dark:bg-gray-900 p-3 rounded-md overflow-auto max-h-[600px] whitespace-pre-wrap text-gray-700 dark:text-gray-300">
                  {searchResponse.output}
                </pre>
              </div>
            ) : (
              /* Parsed Results View */
              <div className="space-y-3">
                {searchResponse.results.length > 0 ? (
                  searchResponse.results.map((result, index) => (
                    <div
                      key={`${result.url}-${index}`}
                      className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-800 hover:border-blue-300 dark:hover:border-blue-700 transition-colors"
                    >
                      {/* Index and Title */}
                      <div className="flex items-start gap-2 mb-2">
                        <span className="flex-shrink-0 w-6 h-6 flex items-center justify-center bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-full text-xs font-medium">
                          {index + 1}
                        </span>
                        <div className="flex-1">
                          <h4 className="font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
                            {result.title}
                          </h4>
                          
                          {/* URL */}
                          {result.url && (
                            <a
                              href={result.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-blue-600 dark:text-blue-400 hover:underline block mt-1 truncate"
                            >
                              {formatUrl(result.url)}
                            </a>
                          )}
                        </div>
                      </div>

                      {/* Snippet */}
                      {result.snippet && (
                        <p className="text-sm text-gray-700 dark:text-gray-300 mt-2 ml-8 leading-relaxed line-clamp-3">
                          {result.snippet}
                        </p>
                      )}
                    </div>
                  ))
                ) : (
                  /* No Results */
                  searchResponse.success && (
                    <div className="flex items-center justify-center h-32 text-gray-500 dark:text-gray-400">
                      <p>未找到搜索结果（可能是 API 限制或查询问题）</p>
                    </div>
                  )
                )}

                {/* Error from API */}
                {!searchResponse.success && searchResponse.error && (
                  <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md">
                    <p className="text-sm text-yellow-800 dark:text-yellow-300">
                      <strong>API 错误：</strong>{searchResponse.error}
                    </p>
                    <p className="text-xs text-yellow-700 dark:text-yellow-400 mt-2">
                      提示：DuckDuckGo Instant Answer API 可能无法返回所有查询的结果。
                      尝试更具体的查询或使用网页浏览器进行完整搜索。
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!searchResponse && !isLoading && !error && (
        <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
          <div className="text-center">
            <svg
              className="w-16 h-16 mx-auto mb-4 opacity-50"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <p className="text-sm">输入搜索查询开始调试 Web Search 功能</p>
          </div>
        </div>
      )}
    </div>
  );
}
