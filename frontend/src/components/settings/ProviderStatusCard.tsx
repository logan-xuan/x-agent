/** Provider status card component */

import { Badge } from '../ui/Badge';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';

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

interface ProviderStatusCardProps {
  provider: ProviderStatus;
  onResetCircuit?: (name: string) => void;
}

export function ProviderStatusCard({ provider, onResetCircuit }: ProviderStatusCardProps) {
  // Use pre-calculated success_rate from backend if available
  const successRate = provider.stats.success_rate !== undefined
    ? provider.stats.success_rate.toFixed(1)
    : provider.stats.total_requests > 0
      ? ((provider.stats.successful_requests / provider.stats.total_requests) * 100).toFixed(1)
      : '0.0';
  
  const circuitStateColor = {
    closed: 'success',
    open: 'destructive',
    half_open: 'warning',
  } as const;
  
  const circuitStateLabel = {
    closed: '正常',
    open: '熔断',
    half_open: '恢复中',
  };
  
  return (
    <Card className="mb-3">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            {provider.name}
            {provider.is_primary && (
              <Badge variant="default">主模型</Badge>
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${provider.is_healthy ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-sm text-gray-600 dark:text-gray-300">
              {provider.is_healthy ? '健康' : '异常'}
            </span>
          </div>
        </div>
      </CardHeader>
      
      <CardContent>
        <div className="space-y-3">
          {/* Model ID */}
          <div className="flex justify-between text-sm">
            <span className="text-gray-600 dark:text-gray-400">模型</span>
            <span className="font-mono text-gray-900 dark:text-white">{provider.model_id}</span>
          </div>
          
          {/* Circuit State */}
          <div className="flex justify-between items-center text-sm">
            <span className="text-gray-600 dark:text-gray-400">熔断器状态</span>
            <Badge variant={circuitStateColor[provider.circuit_state]}>
              {circuitStateLabel[provider.circuit_state]}
            </Badge>
          </div>
          
          {/* Stats */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-600 dark:text-gray-400">总请求</span>
              <p className="font-medium text-gray-900 dark:text-white">{provider.stats.total_requests}</p>
            </div>
            <div>
              <span className="text-gray-600 dark:text-gray-400">成功率</span>
              <p className="font-medium text-gray-900 dark:text-white">{successRate}%</p>
            </div>
            <div>
              <span className="text-gray-600 dark:text-gray-400">失败次数</span>
              <p className="font-medium text-red-500">{provider.stats.failed_requests}</p>
            </div>
            <div>
              <span className="text-gray-600 dark:text-gray-400">平均延迟</span>
              <p className="font-medium text-gray-900 dark:text-white">
                {provider.stats.avg_latency_ms ? `${Math.round(provider.stats.avg_latency_ms)}ms` : '-'}
              </p>
            </div>
          </div>
          
          {/* Reset button for open circuits */}
          {provider.circuit_state === 'open' && onResetCircuit && (
            <button
              onClick={() => onResetCircuit(provider.name)}
              className="mt-2 w-full py-2 px-4 text-sm bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 dark:text-white rounded-lg transition-colors"
            >
              重置熔断器
            </button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
