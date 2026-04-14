/** Cron task manager component */

import { useCallback, useEffect, useState } from 'react';
import { Button } from '../ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
const API_BASE = '/api/v1';

// Type definitions
interface Schedule {
  id: string;
  task_id: string;
  trigger: {
    type: string;
    args: Record<string, unknown>;
  };
  next_fire_time: string | null;
  last_fire_time: string | null;
  coalesce: string;
  conflict_policy: string;
  paused: boolean;
  func_path: string | null;
  task_name: string | null;
  task_description: string | null;
  metadata: Record<string, unknown>;
}

type TriggerType = 'interval' | 'cron' | 'date';
type CoalescePolicy = 'latest' | 'earliest' | 'all';
type ConflictPolicy = 'replace' | 'do_nothing' | 'exception';

interface Job {
  id: string;
  task_id: string;
  schedule_id: string | null;
  trigger: 'manual' | 'scheduled' | string;
  state: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | string;
  created_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  result: unknown;
  exception: string | null;
}

interface SchedulerStatus {
  running: boolean;
  timezone: string;
  data_store: string;
  schedule_count: number;
  job_count: number;
}

const triggerTypeLabels: Record<string, string> = {
  interval: '间隔触发',
  cron: 'Cron表达式',
  date: '定时触发',
};

const jobStateLabels: Record<string, { text: string; color: string }> = {
  pending: { text: '等待中', color: 'text-yellow-600 dark:text-yellow-400' },
  running: { text: '运行中', color: 'text-blue-600 dark:text-blue-400' },
  completed: { text: '已完成', color: 'text-green-600 dark:text-green-400' },
  success: { text: '成功', color: 'text-green-600 dark:text-green-400' },
  failed: { text: '失败', color: 'text-red-600 dark:text-red-400' },
  cancelled: { text: '已取消', color: 'text-gray-600 dark:text-gray-400' },
  unknown: { text: '未知', color: 'text-gray-600 dark:text-gray-400' },
};

interface Task {
  id: string;
  func: string | null;
  job_executor: string | null;
  max_running_jobs: number | null;
  misfire_grace_time: number | null;
  running_jobs: number;
}

export function CronManager() {
  const [activeTab, setActiveTab] = useState<'schedules' | 'jobs' | 'tasks' | 'status'>('schedules');
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [lastLoadedTab, setLastLoadedTab] = useState<string | null>(null);

  // Modal states
  const [showAddModal, setShowAddModal] = useState(false);
  const [showJobDetail, setShowJobDetail] = useState<Job | null>(null);
  const [newSchedule, setNewSchedule] = useState({
    id: '',
    task_id: '',
    trigger_type: 'interval' as TriggerType,
    trigger_args: JSON.stringify({ minutes: 5 }),
    coalesce: 'latest' as CoalescePolicy,
    conflict_policy: 'replace' as ConflictPolicy,
  });

  // Fetch data with useCallback to prevent re-creation on each render
  const fetchSchedules = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/cron/list_schedules`);
      if (!response.ok) throw new Error('Failed to fetch schedules');
      const data = await response.json();
      setSchedules(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  }, []);

  const fetchJobs = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/cron/jobs`);
      if (!response.ok) throw new Error('Failed to fetch jobs');
      const data: Job[] = await response.json();
      // 按创建时间倒序排列，最新的在最上面
      data.sort((a, b) => {
        const timeA = a.created_at ?? '';
        const timeB = b.created_at ?? '';
        return timeB.localeCompare(timeA);
      });
      setJobs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  }, []);

  const fetchTasks = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/cron/tasks`);
      if (!response.ok) throw new Error('Failed to fetch tasks');
      const data = await response.json();
      // API returns list of tasks directly
      setTasks(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/cron/status`);
      if (!response.ok) throw new Error('Failed to fetch status');
      const data = await response.json();
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  }, []);

  // Actions
  const handleAddSchedule = async () => {
    try {
      const triggerArgs = JSON.parse(newSchedule.trigger_args);
      const response = await fetch(`${API_BASE}/cron/schedules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: newSchedule.id,
          func: newSchedule.task_id, // Use task_id directly as func path
          trigger_type: newSchedule.trigger_type,
          trigger_args: triggerArgs,
          coalesce: newSchedule.coalesce,
          conflict_policy: newSchedule.conflict_policy,
          enabled: true,
          max_running_jobs: 1,
          misfire_grace_time: 3600,
          metadata: {},
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to add schedule');
      }

      setShowAddModal(false);
      setSuccess('调度添加成功');
      setTimeout(() => setSuccess(null), 3000);
      fetchSchedules();

      setNewSchedule({
        id: '',
        task_id: '',
        trigger_type: 'interval',
        trigger_args: JSON.stringify({ minutes: 5 }),
        coalesce: 'latest',
        conflict_policy: 'replace',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add schedule');
    }
  };

  const handleDeleteSchedule = async (id: string) => {
    if (!confirm('确定要删除这个调度吗？')) return;

    try {
      const response = await fetch(`${API_BASE}/cron/schedules/${id}`, {
        method: 'DELETE',
      });

      if (!response.ok) throw new Error('Failed to delete schedule');

      setSuccess('调度删除成功');
      setTimeout(() => setSuccess(null), 3000);
      fetchSchedules();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete schedule');
    }
  };

  const handlePauseSchedule = async (id: string) => {
    try {
      const response = await fetch(`${API_BASE}/cron/schedules/${id}/pause`, {
        method: 'POST',
      });

      if (!response.ok) throw new Error('Failed to pause schedule');

      setSuccess('调度已暂停');
      setTimeout(() => setSuccess(null), 3000);
      fetchSchedules();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to pause schedule');
    }
  };

  const handleResumeSchedule = async (id: string) => {
    try {
      const response = await fetch(`${API_BASE}/cron/schedules/${id}/resume`, {
        method: 'POST',
      });

      if (!response.ok) throw new Error('Failed to resume schedule');

      setSuccess('调度已恢复');
      setTimeout(() => setSuccess(null), 3000);
      fetchSchedules();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resume schedule');
    }
  };

  const handleRunTask = async (taskId: string) => {
    try {
      const response = await fetch(`${API_BASE}/cron/tasks/${taskId}/run`, {
        method: 'POST',
      });

      if (!response.ok) throw new Error('Failed to run task');

      setSuccess('任务已触发执行');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run task');
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!confirm(`确定要删除任务定义 "${taskId}" 吗？\n注意：删除后该任务的调度也将无法执行。`)) return;
    try {
      const response = await fetch(`${API_BASE}/cron/tasks/${taskId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete task');
      setSuccess('任务定义已删除');
      setTimeout(() => setSuccess(null), 3000);
      fetchTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete task');
    }
  };

  // Load data on tab change
  useEffect(() => {
    const loadData = async () => {
      // Prevent duplicate loads for the same tab (helps with React Strict Mode)
      if (lastLoadedTab === activeTab) {
        return;
      }
      setLastLoadedTab(activeTab);

      if (activeTab === 'schedules') {
        await fetchSchedules();
      } else if (activeTab === 'jobs') {
        await fetchJobs();
      } else if (activeTab === 'tasks') {
        await fetchTasks();
      } else if (activeTab === 'status') {
        await fetchStatus();
      }
    };

    loadData();
  }, [activeTab, fetchSchedules, fetchJobs, fetchTasks, fetchStatus, lastLoadedTab]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString('zh-CN');
  };

  return (
    <div className="space-y-4">
      {/* Messages */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3 text-red-600 dark:text-red-400">
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-sm underline">关闭</button>
        </div>
      )}

      {success && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg px-4 py-3 text-green-600 dark:text-green-400">
          {success}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setActiveTab('schedules')}
          className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === 'schedules'
            ? 'text-blue-600 border-b-2 border-blue-600'
            : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
        >
          调度管理
        </button>
        <button
          onClick={() => setActiveTab('jobs')}
          className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === 'jobs'
            ? 'text-blue-600 border-b-2 border-blue-600'
            : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
        >
          执行记录
        </button>
        <button
          onClick={() => setActiveTab('tasks')}
          className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === 'tasks'
            ? 'text-blue-600 border-b-2 border-blue-600'
            : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
        >
          任务定义
        </button>
        <button
          onClick={() => setActiveTab('status')}
          className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === 'status'
            ? 'text-blue-600 border-b-2 border-blue-600'
            : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
        >
          状态监控
        </button>
      </div>

      {/* Content */}
      {activeTab === 'schedules' ? (
        <>
          {/* Add Schedule Button */}
          <div className="flex justify-end">
            <Button onClick={() => setShowAddModal(true)}>
              + 新增调度
            </Button>
          </div>

          {/* Schedules List */}
          {schedules.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-gray-500 dark:text-gray-400">
                暂无调度任务
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {schedules.map((schedule) => (
                <Card key={schedule.id}>
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <div className="font-medium text-gray-900 dark:text-white">{schedule.task_name || schedule.task_id}</div>
                          {schedule.task_name && (
                            <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">({schedule.task_id})</span>
                          )}
                          <span className={`px-2 py-0.5 text-xs rounded-full ${schedule.paused
                            ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300'
                            : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
                            }`}>
                            {schedule.paused ? '已暂停' : '运行中'}
                          </span>
                          <span className="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
                            {triggerTypeLabels[schedule.trigger.type] || schedule.trigger.type}
                          </span>
                        </div>
                        {schedule.task_description && (
                          <p className="text-sm text-gray-400 dark:text-gray-500 mt-0.5">
                            {schedule.task_description}
                          </p>
                        )}
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 font-mono">
                          {schedule.func_path || schedule.task_id}
                        </p>
                        <div className="mt-2 text-sm text-gray-600 dark:text-gray-300 space-y-1">
                          <p>触发参数: {JSON.stringify(schedule.trigger.args)}</p>
                          <div className="flex gap-4 flex-wrap">
                            <span>合并策略: <span className="font-medium text-gray-800 dark:text-gray-200">{schedule.coalesce}</span></span>
                            <span>冲突策略: <span className="font-medium text-gray-800 dark:text-gray-200">{schedule.conflict_policy}</span></span>
                          </div>
                          <p>下次执行: {formatDate(schedule.next_fire_time)}</p>
                          <p>上次执行: {formatDate(schedule.last_fire_time)}</p>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleRunTask(schedule.task_id)}
                        >
                          立即执行
                        </Button>
                        {schedule.paused ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleResumeSchedule(schedule.id)}
                          >
                            恢复
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handlePauseSchedule(schedule.id)}
                          >
                            暂停
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleDeleteSchedule(schedule.id)}
                        >
                          删除
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      ) : activeTab === 'jobs' ? (
        <>
          {/* Jobs List */}
          {jobs.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-gray-500 dark:text-gray-400">
                暂无执行记录
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {jobs.map((job) => {
                const stateInfo = jobStateLabels[job.state] || { text: job.state, color: 'text-gray-600 dark:text-gray-400' };
                return (
                  <Card key={job.id} className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50" onClick={() => setShowJobDetail(job)}>
                    <CardContent className="pt-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm text-gray-600 dark:text-gray-400">
                              {job.id.slice(0, 8)}...
                            </span>
                            <span className={`px-2 py-0.5 text-xs rounded-full ${stateInfo.color.replace('text-', 'bg-').replace('dark:text-', 'dark:bg-').replace('600', '100').replace('400', '900/30')}`}>
                              {stateInfo.text}
                            </span>
                            <span className={`px-2 py-0.5 text-xs rounded-full ${job.trigger === 'manual' ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300' : 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300'}`}>
                              {job.trigger === 'manual' ? '手动' : '自动'}
                            </span>
                          </div>
                          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                            任务: {job.task_id}
                          </p>
                        </div>
                        <div className="text-right text-sm text-gray-500 dark:text-gray-400">
                          <p>创建: {formatDate(job.created_at)}</p>
                          {job.ended_at && <p>结束: {formatDate(job.ended_at)}</p>}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </>
      ) : activeTab === 'tasks' ? (
        <>
          <div className="flex justify-between items-center">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              任务定义存储在数据库中，即使删除调度后任务定义仍会保留。
            </p>
            <Button variant="outline" size="sm" onClick={fetchTasks}>
              刷新
            </Button>
          </div>

          {tasks.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-gray-500 dark:text-gray-400">
                暂无任务定义
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {tasks.map((task) => (
                <Card key={task.id}>
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-semibold text-gray-900 dark:text-white">
                            {task.id}
                          </h3>
                          {task.running_jobs > 0 && (
                            <span className="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
                              运行中 {task.running_jobs} 个
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 truncate">
                          函数: {task.func ?? '-'}
                        </p>
                        <div className="mt-1 flex gap-4 text-xs text-gray-500 dark:text-gray-400">
                          <span>执行器: {task.job_executor ?? '-'}</span>
                          <span>最大并发: {task.max_running_jobs ?? '无限制'}</span>
                          {task.misfire_grace_time != null && (
                            <span>容错时间: {task.misfire_grace_time}s</span>
                          )}
                        </div>
                      </div>
                      <div className="flex gap-2 ml-4 shrink-0">
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleDeleteTask(task.id)}
                        >
                          删除
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      ) : (
        /* Status Tab */
        <Card>
          <CardHeader>
            <CardTitle>调度器状态</CardTitle>
          </CardHeader>
          <CardContent>
            {status ? (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">运行状态</p>
                  <p className={`text-lg font-semibold ${status.running ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    {status.running ? '运行中' : '已停止'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">时区</p>
                  <p className="text-lg font-semibold text-gray-900 dark:text-white">{status.timezone}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">存储类型</p>
                  <p className="text-lg font-semibold text-gray-900 dark:text-white">{status.data_store}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">调度数量</p>
                  <p className="text-lg font-semibold text-gray-900 dark:text-white">{status.schedule_count}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">任务数量</p>
                  <p className="text-lg font-semibold text-gray-900 dark:text-white">{status.job_count}</p>
                </div>
              </div>
            ) : (
              <p className="text-gray-500 dark:text-gray-400">无法获取状态</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Add Schedule Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-lg max-h-[90vh] overflow-auto">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              新增调度
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  调度 ID *
                </label>
                <input
                  type="text"
                  value={newSchedule.id}
                  onChange={(e) => setNewSchedule({ ...newSchedule, id: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white font-mono text-sm"
                  placeholder="例如：daily-backup"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  调度的唯一标识符，用于后续的删除、暂停、恢复等操作
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  执行脚本函数 *
                </label>
                <input
                  type="text"
                  value={newSchedule.task_id}
                  onChange={(e) => setNewSchedule({ ...newSchedule, task_id: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white font-mono text-sm"
                  placeholder="workspace:scripts/hello_cron.py:main"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  支持格式：workspace:scripts/hello_cron.py:main | workspace:jobs/task.py:run | /path/to/script.py:main
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  触发类型
                </label>
                <select
                  value={newSchedule.trigger_type}
                  onChange={(e) =>
                    setNewSchedule({ ...newSchedule, trigger_type: e.target.value as TriggerType })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                >
                  <option value="interval">间隔触发 (interval)</option>
                  <option value="cron">Cron表达式 (cron)</option>
                  <option value="date">定时触发 (date)</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  触发参数 (JSON)
                </label>
                <textarea
                  value={newSchedule.trigger_args}
                  onChange={(e) => setNewSchedule({ ...newSchedule, trigger_args: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white font-mono text-sm"
                  rows={3}
                  placeholder='{"minutes": 5}'
                  title="间隔触发: {minutes: 5} | {hours: 2}
Cron触发: {hour: 3, minute: 0} | {day_of_week: 'mon', hour: 9}
日期触发: {run_date: '2024-01-01T00:00:00'}"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  间隔: {`{"minutes": 5}`} | Cron: {`{"hour": 3, "minute": 0}`} | 日期: {`{"run_date": "2024-01-01T00:00:00"}`}
                </p>
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                  💡 鼠标悬停在输入框上查看更多示例
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  合并策略
                </label>
                <select
                  value={newSchedule.coalesce}
                  onChange={(e) =>
                    setNewSchedule({ ...newSchedule, coalesce: e.target.value as CoalescePolicy })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                >
                  <option value="latest">latest - 只执行最新</option>
                  <option value="earliest">earliest - 只执行最早</option>
                  <option value="all">all - 全部执行</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  冲突策略
                </label>
                <select
                  value={newSchedule.conflict_policy}
                  onChange={(e) =>
                    setNewSchedule({
                      ...newSchedule,
                      conflict_policy: e.target.value as ConflictPolicy,
                    })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                >
                  <option value="replace">replace - 替换现有</option>
                  <option value="do_nothing">do_nothing - 忽略</option>
                  <option value="exception">exception - 抛出异常</option>
                </select>
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <Button onClick={handleAddSchedule} className="flex-1">
                确认添加
              </Button>
              <Button variant="outline" onClick={() => setShowAddModal(false)} className="flex-1">
                取消
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Job Detail Modal */}
      {showJobDetail && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-xl p-6 w-full max-w-lg max-h-[90vh] overflow-auto">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              任务详情
            </h2>

            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-3 gap-2">
                <span className="text-gray-500 dark:text-gray-400">执行ID (job_id):</span>
                <span className="col-span-2 font-mono text-gray-900 dark:text-white">{showJobDetail.id}</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <span className="text-gray-500 dark:text-gray-400">任务ID (task_id):</span>
                <span className="col-span-2 text-gray-900 dark:text-white">{showJobDetail.task_id}</span>
              </div>
              {showJobDetail.schedule_id && (
                <div className="grid grid-cols-3 gap-2">
                  <span className="text-gray-500 dark:text-gray-400">调度ID (schedule_id):</span>
                  <span className="col-span-2 text-gray-900 dark:text-white">{showJobDetail.schedule_id}</span>
                </div>
              )}
              <div className="grid grid-cols-3 gap-2">
                <span className="text-gray-500 dark:text-gray-400">状态:</span>
                <span className={`col-span-2 ${(jobStateLabels[showJobDetail.state] || { color: 'text-gray-600 dark:text-gray-400' }).color}`}>
                  {(jobStateLabels[showJobDetail.state] || { text: showJobDetail.state }).text}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <span className="text-gray-500 dark:text-gray-400">创建时间:</span>
                <span className="col-span-2 text-gray-900 dark:text-white">{formatDate(showJobDetail.created_at)}</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <span className="text-gray-500 dark:text-gray-400">开始时间:</span>
                <span className="col-span-2 text-gray-900 dark:text-white">{formatDate(showJobDetail.started_at)}</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <span className="text-gray-500 dark:text-gray-400">结束时间:</span>
                <span className="col-span-2 text-gray-900 dark:text-white">{formatDate(showJobDetail.ended_at)}</span>
              </div>

              {showJobDetail.result !== null && (
                <div>
                  <span className="text-gray-500 dark:text-gray-400">执行结果:</span>
                  <pre className="mt-1 p-2 bg-gray-100 dark:bg-gray-800 rounded text-xs overflow-auto max-h-40">
                    {JSON.stringify(showJobDetail.result, null, 2)}
                  </pre>
                </div>
              )}

              {showJobDetail.exception && (
                <div>
                  <span className="text-gray-500 dark:text-gray-400">错误信息:</span>
                  <pre className="mt-1 p-2 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded text-xs overflow-auto max-h-40">
                    {showJobDetail.exception}
                  </pre>
                </div>
              )}
            </div>

            <div className="mt-6">
              <Button onClick={() => setShowJobDetail(null)} className="w-full">
                关闭
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
