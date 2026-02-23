/** Aliyun OpenSearch Web Search debugger component for developer mode */
import { useState } from 'react';
import type { FormEvent } from 'react';

interface WebSearchResult {
  title: string;
  snippet: string;
  url: string;
}

interface AliyunWebSearchResponse {
  success: boolean;
  query: string;
  results: WebSearchResult[];
  output?: string | null;
  error?: string | null;
  metadata?: Record<string, any> | null;
  usage?: Record<string, any> | null;
}

interface AliyunWebSearchDebuggerProps {
  onError?: (error: string) => void;
}

export function AliyunWebSearchDebugger({ onError }: AliyunWebSearchDebuggerProps) {
  const [query, setQuery] = useState('');
  const [maxResults, setMaxResults] = useState(5);
  const [contentType, setContentType] = useState<'snippet' | 'full'>('snippet');
  const [searchResponse, setSearchResponse] = useState<AliyunWebSearchResponse | null>(null);
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
      const response = await fetch('/api/v1/dev/aliyun-web-search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: query,
          max_results: maxResults,
          content_type: contentType,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || '搜索失败');
      }

      const data: AliyunWebSearchResponse = await response.json();
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
      <h3 className="text-lg font-semibold mb-4">🔍 阿里云 OpenSearch 调试器</h3>

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
            placeholder="例如：北京今天天气怎么样？"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
            disabled={isLoading}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              结果数量
            </label>
            <select
              value={maxResults}
              onChange={(e) => setMaxResults(Number(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
              disabled={isLoading}
            >
              <option value={3}>3 条</option>
              <option value={5}>5 条</option>
              <option value={10}>10 条</option>
              <option value={15}>15 条</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              内容类型
            </label>
            <select
              value={contentType}
              onChange={(e) => setContentType(e.target.value as 'snippet' | 'full')}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
              disabled={isLoading}
            >
              <option value="snippet">摘要（更快）</option>
              <option value="full">完整内容（更详细）</option>
            </select>
          </div>
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium rounded-md shadow transition-colors"
        >
          {isLoading ? '搜索中...' : '开始搜索'}
        </button>
      </form>

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
          <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
        </div>
      )}

      {/* Results */}
      {searchResponse && searchResponse.success && (
        <div className="flex-1 overflow-auto">
          <div className="mb-4 flex items-center justify-between">
            <h4 className="font-medium text-gray-900 dark:text-gray-100">
              搜索结果 ({searchResponse.results.length} 条)
            </h4>
            <button
              onClick={() => setShowRawOutput(!showRawOutput)}
              className="text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400"
            >
              {showRawOutput ? '查看结构化结果' : '查看原始输出'}
            </button>
          </div>

          {showRawOutput ? (
            <pre className="p-3 bg-gray-50 dark:bg-gray-800 rounded-md overflow-x-auto text-xs text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
              {searchResponse.output || '无输出'}
            </pre>
          ) : (
            <div className="space-y-4">
              {searchResponse.results.map((result, index) => (
                <div
                  key={index}
                  className="p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-sm"
                >
                  <h5 className="font-medium text-blue-600 dark:text-blue-400 mb-1">
                    {result.title}
                  </h5>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                    {result.snippet}
                  </p>
                  <a
                    href={result.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-gray-500 dark:text-gray-500 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    {formatUrl(result.url)}
                  </a>
                </div>
              ))}
            </div>
          )}

          {/* Token Usage Info */}
          {searchResponse.usage && (
            <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md">
              <h5 className="font-medium text-blue-900 dark:text-blue-100 mb-2">
                💡 Token 使用情况
              </h5>
              <dl className="grid grid-cols-2 gap-2 text-sm">
                {searchResponse.usage.search_count !== undefined && (
                  <div>
                    <dt className="text-gray-600 dark:text-gray-400">搜索次数:</dt>
                    <dd className="font-medium text-gray-900 dark:text-gray-100">
                      {searchResponse.usage.search_count}
                    </dd>
                  </div>
                )}
                {searchResponse.usage.rewrite_tokens !== undefined && (
                  <div>
                    <dt className="text-gray-600 dark:text-gray-400">重写模型 Token:</dt>
                    <dd className="font-medium text-gray-900 dark:text-gray-100">
                      {searchResponse.usage.rewrite_tokens}
                    </dd>
                  </div>
                )}
                {searchResponse.usage.filter_tokens !== undefined && (
                  <div>
                    <dt className="text-gray-600 dark:text-gray-400">过滤模型 Token:</dt>
                    <dd className="font-medium text-gray-900 dark:text-gray-100">
                      {searchResponse.usage.filter_tokens}
                    </dd>
                  </div>
                )}
                {searchResponse.usage.total_tokens !== undefined && (
                  <div>
                    <dt className="text-gray-600 dark:text-gray-400">总 Token:</dt>
                    <dd className="font-medium text-gray-900 dark:text-gray-100">
                      {searchResponse.usage.total_tokens}
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {!searchResponse && !isLoading && (
        <div className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400">
          <p>输入搜索关键词开始测试阿里云 OpenSearch</p>
        </div>
      )}
    </div>
  );
}
