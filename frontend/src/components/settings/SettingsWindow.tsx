/** Settings window component */

import { useEffect, useState } from 'react';
import { Button } from '../ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Spinner } from '../ui/Spinner';
import { ModelEditor } from './ModelEditor';
import { ProviderStatusCard } from './ProviderStatusCard';

interface ProviderStatus {
  name: string;
  model_id: string;
  is_primary: boolean;
  is_healthy: boolean;
  circuit_state: 'closed' | 'open' | 'half_open';
  stats: {
    total_requests: number;
    successful_requests: number;
    failed_requests: number;
    consecutive_failures: number;
    last_failure_time: string | null;
    last_success_time: string | null;
    success_rate?: number;
    avg_latency_ms?: number;
  };
}

interface EditableModel {
  name: string;
  provider: string;
  base_url: string;
  api_key_masked: string;
  model_id: string;
  is_primary: boolean;
  timeout: number;
  max_retries: number;
  priority: number;
}

interface ConfigStatus {
  providers: ProviderStatus[];
  circuit_breakers: Record<string, unknown>;
}

interface EditableConfig {
  models: EditableModel[];
  config_path: string;
}

interface AggregatedStats {
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  success_rate: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  avg_latency_ms: number;
  max_latency_ms: number;
  min_latency_ms: number;
}

interface ProviderStats {
  provider_name: string;
  model_id: string;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  success_rate: number;
  avg_latency_ms: number;
}

interface ErrorRecord {
  id: string;
  provider_name: string;
  model_id: string;
  error_message: string;
  created_at: string;
}

interface DailyStats {
  date: string;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  success_rate: number;
  total_tokens: number;
}

interface SettingsWindowProps {
  onClose?: () => void;
}

const API_BASE = '/api/v1';

// Format number with units (K, M, B)
function formatNumber(num: number): string {
  if (num >= 1_000_000_000) {
    return (num / 1_000_000_000).toFixed(1) + 'B';
  }
  if (num >= 1_000_000) {
    return (num / 1_000_000).toFixed(1) + 'M';
  }
  if (num >= 1_000) {
    return (num / 1_000).toFixed(1) + 'K';
  }
  return num.toString();
}

export function SettingsWindow({ onClose }: SettingsWindowProps) {
  const [status, setStatus] = useState<ConfigStatus | null>(null);
  const [editableConfig, setEditableConfig] = useState<EditableConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isReloading, setIsReloading] = useState(false);
  const [isUpdating, setIsUpdating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'status' | 'edit' | 'stats'>('status');
  
  // Stats state
  const [aggregatedStats, setAggregatedStats] = useState<AggregatedStats | null>(null);
  const [providerStats, setProviderStats] = useState<ProviderStats[]>([]);
  const [recentErrors, setRecentErrors] = useState<ErrorRecord[]>([]);
  const [dailyStats, setDailyStats] = useState<DailyStats[]>([]);
  const [statsTimeRange, setStatsTimeRange] = useState<'1' | '7' | '30'>('7');
  const [isLoadingStats, setIsLoadingStats] = useState(false);
  
  const fetchData = async () => {
    try {
      const [statusRes, configRes] = await Promise.all([
        fetch(`${API_BASE}/config/status`),
        fetch(`${API_BASE}/config/edit`),
      ]);
      
      if (!statusRes.ok || !configRes.ok) throw new Error('Failed to fetch data');
      
      const statusData = await statusRes.json();
      const configData = await configRes.json();
      
      setStatus(statusData);
      setEditableConfig(configData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  };
  
  const fetchStats = async () => {
    setIsLoadingStats(true);
    try {
      const days = statsTimeRange;
      const [aggregatedRes, providerRes, errorsRes, dailyRes] = await Promise.all([
        fetch(`${API_BASE}/stats/aggregated?days=${days}`),
        fetch(`${API_BASE}/stats/by-provider?days=${days}`),
        fetch(`${API_BASE}/stats/recent-errors?limit=5`),
        fetch(`${API_BASE}/stats/daily?days=${days}`),
      ]);
      
      if (aggregatedRes.ok) setAggregatedStats(await aggregatedRes.json());
      if (providerRes.ok) setProviderStats(await providerRes.json());
      if (errorsRes.ok) setRecentErrors(await errorsRes.json());
      if (dailyRes.ok) setDailyStats(await dailyRes.json());
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    } finally {
      setIsLoadingStats(false);
    }
  };
  
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);
  
  useEffect(() => {
    if (activeTab === 'stats') {
      fetchStats();
    }
  }, [activeTab, statsTimeRange]);
  
  const handleReload = async () => {
    setIsReloading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/config/reload`, { method: 'POST' });
      if (!response.ok) throw new Error('Failed to reload');
      await fetchData();
      setSuccess('配置已重新加载');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reload failed');
    } finally {
      setIsReloading(false);
    }
  };
  
  const handleResetCircuit = async (providerName: string) => {
    try {
      const response = await fetch(
        `${API_BASE}/config/circuit-breaker/${providerName}/reset`,
        { method: 'POST' }
      );
      if (!response.ok) throw new Error('Failed to reset');
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed');
    }
  };
  
  const handleResetAll = async () => {
    try {
      const response = await fetch(
        `${API_BASE}/config/circuit-breaker/reset-all`,
        { method: 'POST' }
      );
      if (!response.ok) throw new Error('Failed to reset all');
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset all failed');
    }
  };
  
  const handleUpdateModel = async (name: string, updates: Partial<EditableModel>) => {
    setIsUpdating(name);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/config/models/${name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Update failed');
      }
      
      await fetchData();
      setSuccess('配置已更新');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed');
    } finally {
      setIsUpdating(null);
    }
  };
  
  return (
    <div className="fixed inset-0 flex flex-col bg-white dark:bg-gray-900">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3">
        <div className="flex items-center justify-between max-w-3xl mx-auto">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
            设置
          </h1>
          {onClose && (
            <Button
              variant="outline"
              size="sm"
              onClick={onClose}
              className="border-gray-300 text-gray-700 hover:bg-gray-100 hover:text-gray-900 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-white"
            >
              返回聊天
            </Button>
          )}
        </div>
      </header>
      
      {/* Tabs */}
      <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-3xl mx-auto flex">
          <button
            onClick={() => setActiveTab('status')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'status'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            状态监控
          </button>
          <button
            onClick={() => setActiveTab('stats')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'stats'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            统计分析
          </button>
          <button
            onClick={() => setActiveTab('edit')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'edit'
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            配置编辑
          </button>
        </div>
      </div>
      
      {/* Messages */}
      {error && (
        <div className="max-w-3xl mx-auto w-full px-4 pt-4">
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3 text-red-600 dark:text-red-400">
            {error}
            <button onClick={() => setError(null)} className="ml-2 text-sm underline">关闭</button>
          </div>
        </div>
      )}
      
      {success && (
        <div className="max-w-3xl mx-auto w-full px-4 pt-4">
          <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg px-4 py-3 text-green-600 dark:text-green-400">
            {success}
          </div>
        </div>
      )}
      
      {/* Content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto px-4 py-4">
          {isLoading ? (
            <div className="flex items-center justify-center h-40">
              <Spinner size="lg" />
            </div>
          ) : activeTab === 'status' ? (
            <>
              {/* Actions */}
              <Card className="mb-3">
                <CardHeader className="pb-2">
                  <CardTitle>配置管理</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex gap-3">
                    <Button onClick={handleReload} disabled={isReloading}>
                      {isReloading ? (
                        <>
                          <Spinner size="sm" className="mr-2" />
                          重载中...
                        </>
                      ) : (
                        '重载配置'
                      )}
                    </Button>
                    <Button variant="outline" onClick={handleResetAll}>
                      重置所有熔断器
                    </Button>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">
                    配置文件: <span className="font-mono">{editableConfig?.config_path}</span>
                  </p>
                </CardContent>
              </Card>
              
              {/* Providers */}
              <div>
                <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-3">
                  模型提供商
                </h2>
                {status?.providers.map((provider) => (
                  <ProviderStatusCard
                    key={provider.name}
                    provider={provider}
                    onResetCircuit={handleResetCircuit}
                  />
                ))}
              </div>
            </>
          ) : activeTab === 'stats' ? (
            <>
              {/* Time Range Selector */}
              <Card className="mb-3">
                <CardContent className="pt-4">
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-gray-600 dark:text-gray-300">统计周期：</span>
                    <div className="flex gap-2">
                      {(['1', '7', '30'] as const).map((days) => (
                        <button
                          key={days}
                          onClick={() => setStatsTimeRange(days)}
                          className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                            statsTimeRange === days
                              ? 'bg-blue-500 text-white'
                              : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                          }`}
                        >
                          {days === '1' ? '今天' : `最近 ${days} 天`}
                        </button>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
              
              {isLoadingStats ? (
                <div className="flex items-center justify-center h-40">
                  <Spinner size="lg" />
                </div>
              ) : (
                <>
                  {/* Aggregated Stats */}
                  <Card className="mb-3">
                    <CardHeader className="pb-2">
                      <CardTitle>总体统计</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                        <div>
                          <p className="text-sm text-gray-600 dark:text-gray-400">总请求</p>
                          <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                            {formatNumber(aggregatedStats?.total_requests || 0)}
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-600 dark:text-gray-400">成功率</p>
                          <p className="text-2xl font-semibold text-green-600 dark:text-green-400">
                            {aggregatedStats?.success_rate?.toFixed(1) || 0}%
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-600 dark:text-gray-400">平均延迟</p>
                          <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                            {Math.round(aggregatedStats?.avg_latency_ms || 0)}ms
                          </p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-600 dark:text-gray-400">总Token</p>
                          <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                            {formatNumber(aggregatedStats?.total_tokens || 0)}
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                  
                  {/* Provider Stats */}
                  <Card className="mb-3">
                    <CardHeader className="pb-2">
                      <CardTitle>按提供商统计</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {providerStats.length === 0 ? (
                        <p className="text-sm text-gray-500 dark:text-gray-400">暂无数据</p>
                      ) : (
                        <div className="space-y-3">
                          {providerStats.map((ps) => (
                            <div key={ps.provider_name} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                              <div>
                                <p className="font-medium text-gray-900 dark:text-white">{ps.provider_name}</p>
                                <p className="text-sm text-gray-500 dark:text-gray-400">{ps.model_id}</p>
                              </div>
                              <div className="text-right">
                                <p className="text-sm">
                                  <span className="text-gray-600 dark:text-gray-300">请求: {formatNumber(ps.total_requests)}</span>
                                  <span className="mx-2">|</span>
                                  <span className="text-green-600 dark:text-green-400">{ps.success_rate.toFixed(1)}%</span>
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                  平均延迟: {Math.round(ps.avg_latency_ms)}ms
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                  
                  {/* Recent Errors */}
                  <Card className="mb-3">
                    <CardHeader className="pb-2">
                      <CardTitle>最近错误</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {recentErrors.length === 0 ? (
                        <p className="text-sm text-green-600 dark:text-green-400">🎉 无错误记录</p>
                      ) : (
                        <div className="space-y-2">
                          {recentErrors.map((err) => (
                            <div key={err.id} className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                              <div className="flex justify-between items-start">
                                <p className="text-sm font-medium text-red-600 dark:text-red-400">{err.provider_name}</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                  {new Date(err.created_at).toLocaleString('zh-CN')}
                                </p>
                              </div>
                              <p className="text-sm text-red-500 dark:text-red-300 mt-1 line-clamp-2">
                                {err.error_message}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                  
                  {/* Daily Stats */}
                  <Card className="mb-3">
                    <CardHeader className="pb-2">
                      <CardTitle>每日统计</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {dailyStats.length === 0 ? (
                        <p className="text-sm text-gray-500 dark:text-gray-400">暂无数据</p>
                      ) : (
                        <div className="space-y-2">
                          {dailyStats.map((ds) => (
                            <div key={ds.date} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                              <span className="font-mono text-sm text-gray-900 dark:text-white">{ds.date}</span>
                              <div className="flex items-center gap-4 text-sm">
                                <span className="text-gray-600 dark:text-gray-300">
                                  {formatNumber(ds.total_requests)} 请求
                                </span>
                                <span className="text-green-600 dark:text-green-400">
                                  {ds.success_rate.toFixed(1)}%
                                </span>
                                <span className="text-gray-500 dark:text-gray-400">
                                  {formatNumber(ds.total_tokens)} tokens
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </>
              )}
            </>
          ) : (
            <>
              <div className="mb-3">
                <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-1">
                  模型配置
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  编辑模型配置后，更改会自动保存到配置文件并重新加载
                </p>
              </div>
              
              {editableConfig?.models.map((model) => (
                <ModelEditor
                  key={model.name}
                  model={model}
                  onUpdate={handleUpdateModel}
                  isUpdating={isUpdating === model.name}
                />
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
