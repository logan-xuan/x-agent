/** Memory search debugger component for developer mode */
import { useState } from 'react';
import { searchMemory } from '../../services/api';
import type { SearchResponse, SearchParams } from '../../types';

interface MemorySearchDebuggerProps {
  onError?: (error: string) => void;
}

export function MemorySearchDebugger({ onError }: MemorySearchDebuggerProps) {
  const [searchParams, setSearchParams] = useState<SearchParams>({
    query: '',
    limit: 10,
    offset: 0,
    min_score: 0.0,
  });
  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!searchParams.query.trim()) {
      setError('请输入搜索查询');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await searchMemory(searchParams);
      setSearchResults(response);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '搜索失败';
      setError(errorMessage);
      onError?.(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputChange = (field: keyof SearchParams, value: string | number) => {
    setSearchParams(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch();
  };

  return (
    <div className="flex flex-col h-full p-4">
      <h3 className="text-lg font-semibold mb-4">记忆搜索调试</h3>

      {/* Search Form */}
      <form onSubmit={handleSubmit} className="mb-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              搜索查询 *
            </label>
            <input
              type="text"
              value={searchParams.query}
              onChange={(e) => handleInputChange('query', e.target.value)}
              placeholder="输入搜索关键词..."
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              disabled={isLoading}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              内容类型 (可选)
            </label>
            <select
              value={searchParams.content_type || ''}
              onChange={(e) => handleInputChange('content_type', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              disabled={isLoading}
            >
              <option value="">全部类型</option>
              <option value="conversation">对话</option>
              <option value="decision">决策</option>
              <option value="knowledge">知识</option>
              <option value="task">任务</option>
              <option value="note">笔记</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              限制数量
            </label>
            <input
              type="number"
              min="1"
              max="100"
              value={searchParams.limit}
              onChange={(e) => handleInputChange('limit', parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              disabled={isLoading}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              偏移量
            </label>
            <input
              type="number"
              min="0"
              value={searchParams.offset}
              onChange={(e) => handleInputChange('offset', parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              disabled={isLoading}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              最小分数
            </label>
            <input
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={searchParams.min_score}
              onChange={(e) => handleInputChange('min_score', parseFloat(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              disabled={isLoading}
            />
          </div>

          <div className="flex items-end">
            <button
              type="submit"
              disabled={isLoading || !searchParams.query.trim()}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? '搜索中...' : '搜索'}
            </button>
          </div>
        </div>
      </form>

      {/* Error Display */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
          <p className="text-red-600 dark:text-red-400 text-sm">{error}</p>
        </div>
      )}

      {/* Search Results */}
      {searchResults && (
        <div className="flex-1 overflow-hidden flex flex-col">
          <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-md">
            <div className="flex justify-between items-center">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                搜索查询: "{searchResults.query}"
              </p>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                结果数量: {searchResults.items.length} / {searchResults.total}
              </p>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto space-y-4">
            {searchResults.items.map((result, index) => (
              <div
                key={`${result.entry.id}-${index}`}
                className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-800"
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="flex-1">
                    <h4 className="font-medium text-gray-900 dark:text-gray-100">
                      {result.entry.title || `条目 ${index + 1}`}
                    </h4>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="inline-block px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 rounded text-gray-600 dark:text-gray-400">
                        {result.entry.content_type}
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        重要性: {result.entry.importance}
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {new Date(result.entry.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>

                  {/* Score breakdown */}
                  <div className="text-right ml-4">
                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      综合评分: {result.score.toFixed(3)}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      <div>向量: {result.vector_score.toFixed(3)}</div>
                      <div>文本: {result.text_score.toFixed(3)}</div>
                    </div>
                  </div>
                </div>

                {/* Content preview */}
                <div className="mt-3 text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                  {result.entry.content.substring(0, 300)}
                  {result.entry.content.length > 300 && '...'}
                </div>

                {/* Tags */}
                {result.entry.tags && result.entry.tags.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1">
                    {result.entry.tags.map((tag, tagIndex) => (
                      <span
                        key={tagIndex}
                        className="inline-block px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 rounded"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {searchResults.items.length === 0 && (
              <div className="flex items-center justify-center h-32 text-gray-500 dark:text-gray-400">
                <p>未找到匹配的记忆条目</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}