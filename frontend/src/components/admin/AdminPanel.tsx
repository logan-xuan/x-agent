/** 管理后台面板 — 查看和管理 User / Agent / Channel / Session */

import { useEffect, useState, useCallback } from 'react';
import { Button } from '../ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Spinner } from '../ui/Spinner';

const API_BASE = '/api/v1';
const ADMIN_TOKEN_KEY = 'x-agent-admin-token';

type TabKey = 'users' | 'agents' | 'channels' | 'sessions';

interface User {
  user_id: string;
  name: string;
  create_time: string | null;
}

interface Agent {
  agent_id: string;
  agent_name: string;
  agent_type: string;
  agent_persona: string;
  user_id: string;
  workspace: string;
  feature: string;
  create_time?: string | null;  // 配置驱动下可能不存在
}

interface Channel {
  channel_id: string;
  channel_type: string;
  channel_protocol: string;
  user_id: string;
  agent_id: string;
  create_time?: string | null;  // 配置驱动下可能不存在
}

interface Session {
  session_id: string;
  session_name: string;
  user_id: string;
  agent_id: string;
  channel_id: string;
  status: string;
  create_time: string | null;
  updated_at: string | null;
}

interface AdminPanelProps {
  onClose?: () => void;
}

function getToken(): string | null {
  return localStorage.getItem(ADMIN_TOKEN_KEY);
}

async function adminFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': token || '',
      ...options.headers,
    },
  });
}

// ---------------------------------------------------------------------------
// 登录表单
// ---------------------------------------------------------------------------

function LoginForm({ onLogin }: { onLogin: (token: string) => void }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_BASE}/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      const data = await response.json();
      if (data.success && data.token) {
        localStorage.setItem(ADMIN_TOKEN_KEY, data.token);
        onLogin(data.token);
      } else {
        setError(data.message || '登录失败');
      }
    } catch {
      setError('网络错误');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>🔐 管理后台登录</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="请输入管理密码"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              autoFocus
            />
            {error && (
              <p className="text-sm text-red-500">{error}</p>
            )}
            <Button type="submit" className="w-full" disabled={loading || !password}>
              {loading ? <><Spinner size="sm" className="mr-2" />登录中...</> : '登录'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 数据表格
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function DataTable<T extends { [key: string]: any }>({
  columns,
  data,
  actions,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  columns: { key: string; label: string; render?: (value: any, row: T) => React.ReactNode }[];
  data: T[];
  actions?: (row: T) => React.ReactNode;
}) {
  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-gray-400">暂无数据</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            {columns.map((col) => (
              <th key={col.key} className="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">
                {col.label}
              </th>
            ))}
            {actions && <th className="px-3 py-2 font-medium text-gray-500 dark:text-gray-400">操作</th>}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => (
            <tr key={index} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
              {columns.map((col) => {
                const rawValue = String(row[col.key] ?? '');
                return (
                  <td key={col.key} className="max-w-[200px] truncate px-3 py-2 text-gray-700 dark:text-gray-300" title={rawValue}>
                    {col.render ? col.render(row[col.key], row) : rawValue || '-'}
                  </td>
                );
              })}
              {actions && <td className="px-3 py-2">{actions(row)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 编辑弹窗
// ---------------------------------------------------------------------------

function EditModal({
  title,
  fields,
  values,
  onSave,
  onCancel,
}: {
  title: string;
  fields: { key: string; label: string; type?: string }[];
  values: Record<string, string>;
  onSave: (updated: Record<string, string>) => void;
  onCancel: () => void;
}) {
  const [formData, setFormData] = useState(values);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onSave(formData);
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {fields.map((field) => (
            <div key={field.key}>
              <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                {field.label}
              </label>
              {field.type === 'textarea' ? (
                <textarea
                  value={formData[field.key] || ''}
                  onChange={(event) => setFormData({ ...formData, [field.key]: event.target.value })}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  rows={3}
                />
              ) : (
                <input
                  type="text"
                  value={formData[field.key] || ''}
                  onChange={(event) => setFormData({ ...formData, [field.key]: event.target.value })}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                />
              )}
            </div>
          ))}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onCancel}>取消</Button>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? '保存中...' : '保存'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 主面板
// ---------------------------------------------------------------------------

export function AdminPanel({ onClose }: AdminPanelProps) {
  const [token, setToken] = useState<string | null>(getToken);
  const [activeTab, setActiveTab] = useState<TabKey>('users');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 数据
  const [users, setUsers] = useState<User[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);

  // 编辑状态
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [editingSession, setEditingSession] = useState<Session | null>(null);

  const showSuccess = (message: string) => {
    setSuccess(message);
    setTimeout(() => setSuccess(null), 2000);
  };

  // 加载数据
  const fetchTabData = useCallback(async (tab: TabKey) => {
    setLoading(true);
    setError(null);
    try {
      const response = await adminFetch(`/admin/${tab}`);
      if (response.status === 401) {
        localStorage.removeItem(ADMIN_TOKEN_KEY);
        setToken(null);
        return;
      }
      if (!response.ok) throw new Error('加载失败');
      const data = await response.json();
      switch (tab) {
        case 'users': setUsers(data); break;
        case 'agents': setAgents(data); break;
        case 'channels': setChannels(data); break;
        case 'sessions': setSessions(data); break;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '未知错误');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) fetchTabData(activeTab);
  }, [token, activeTab, fetchTabData]);

  // 删除操作
  const handleDelete = async (tab: TabKey, entityId: string) => {
    if (!confirm('确定要删除吗？此操作不可恢复。')) return;
    try {
      const response = await adminFetch(`/admin/${tab}/${entityId}`, { method: 'DELETE' });
      if (!response.ok) throw new Error('删除失败');
      showSuccess('删除成功');
      fetchTabData(activeTab);
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  // 更新用户
  const handleUpdateUser = async (updated: Record<string, string>) => {
    if (!editingUser) return;
    try {
      const response = await adminFetch(`/admin/users/${editingUser.user_id}`, {
        method: 'PUT',
        body: JSON.stringify({ name: updated.name }),
      });
      if (!response.ok) throw new Error('更新失败');
      setEditingUser(null);
      showSuccess('更新成功');
      fetchTabData('users');
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新失败');
    }
  };

  // 更新 Agent
  const handleUpdateAgent = async (updated: Record<string, string>) => {
    if (!editingAgent) return;
    try {
      const response = await adminFetch(`/admin/agents/${editingAgent.agent_id}`, {
        method: 'PUT',
        body: JSON.stringify({
          agent_name: updated.agent_name,
          agent_persona: updated.agent_persona,
        }),
      });
      if (!response.ok) throw new Error('更新失败');
      setEditingAgent(null);
      showSuccess('更新成功');
      fetchTabData('agents');
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新失败');
    }
  };

  // 更新会话状态
  const handleUpdateSessionStatus = async (updated: Record<string, string>) => {
    if (!editingSession) return;
    try {
      const response = await adminFetch(`/admin/sessions/${editingSession.session_id}/status`, {
        method: 'PUT',
        body: JSON.stringify({ status: updated.status }),
      });
      if (!response.ok) throw new Error('更新失败');
      setEditingSession(null);
      showSuccess('更新成功');
      fetchTabData('sessions');
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新失败');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    setToken(null);
  };

  // 未登录 → 显示登录表单
  if (!token) {
    return <LoginForm onLogin={setToken} />;
  }

  const tabs: { key: TabKey; label: string; icon: string }[] = [
    { key: 'users', label: '用户', icon: '👤' },
    { key: 'agents', label: 'Agent', icon: '🤖' },
    { key: 'channels', label: '渠道', icon: '📡' },
    { key: 'sessions', label: '会话', icon: '💬' },
  ];

  const formatTime = (time: string | null) => {
    if (!time) return '-';
    return new Date(time).toLocaleString('zh-CN');
  };

  const statusBadge = (status: string) => {
    const colors: Record<string, string> = {
      active: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
      closed: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
      archived: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    };
    return (
      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || 'bg-gray-100'}`}>
        {status}
      </span>
    );
  };

  return (
    <div className="fixed inset-0 flex flex-col bg-white dark:bg-gray-900">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3">
        <div className="flex items-center justify-between max-w-5xl mx-auto">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
            🛠️ 管理后台
          </h1>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={handleLogout}>退出登录</Button>
            {onClose && (
              <Button variant="outline" size="sm" onClick={onClose}>返回聊天</Button>
            )}
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-5xl mx-auto flex">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === tab.key
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                }`}
            >
              {tab.icon} {tab.label}
              {activeTab === tab.key && (
                <span className="ml-1.5 rounded-full bg-blue-100 px-1.5 py-0.5 text-xs text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
                  {tab.key === 'users' ? users.length :
                    tab.key === 'agents' ? agents.length :
                      tab.key === 'channels' ? channels.length :
                        sessions.length}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto p-4">
          {/* Alerts */}
          {error && (
            <div className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
              {error}
            </div>
          )}
          {success && (
            <div className="mb-3 rounded-lg bg-green-50 p-3 text-sm text-green-600 dark:bg-green-900/20 dark:text-green-400">
              ✅ {success}
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Spinner size="lg" />
            </div>
          ) : (
            <Card>
              <CardContent className="pt-4">
                {/* Users Tab */}
                {activeTab === 'users' && (
                  <DataTable<User>
                    columns={[
                      { key: 'user_id', label: 'ID', render: (value) => <code className="text-xs">{String(value).slice(0, 12)}...</code> },
                      { key: 'name', label: '名称' },
                      { key: 'create_time', label: '创建时间', render: (value) => formatTime(value as string | null) },
                    ]}
                    data={users}
                    actions={(row) => (
                      <div className="flex gap-1">
                        <Button variant="ghost" size="sm" onClick={() => setEditingUser(row)}>编辑</Button>
                        <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDelete('users', row.user_id)}>删除</Button>
                      </div>
                    )}
                  />
                )}

                {/* Agents Tab */}
                {activeTab === 'agents' && (
                  <DataTable<Agent>
                    columns={[
                      { key: 'agent_id', label: 'ID', render: (value) => <code className="text-xs">{String(value).slice(0, 12)}...</code> },
                      { key: 'agent_name', label: '名称' },
                      { key: 'agent_type', label: '类型' },
                      { key: 'workspace', label: '工作空间', render: (value) => <span className="text-xs text-gray-500">{String(value || '-')}</span> },
                      { key: 'feature', label: '特性', render: (value) => <span className="text-xs">{String(value || '-').slice(0, 20)}</span> },
                    ]}
                    data={agents}
                    actions={(row) => (
                      <div className="flex gap-1">
                        <Button variant="ghost" size="sm" onClick={() => setEditingAgent(row)}>编辑</Button>
                        <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDelete('agents', row.agent_id)}>删除</Button>
                      </div>
                    )}
                  />
                )}

                {/* Channels Tab */}
                {activeTab === 'channels' && (
                  <DataTable<Channel>
                    columns={[
                      { key: 'channel_id', label: 'ID', render: (value) => <code className="text-xs">{String(value).slice(0, 12)}...</code> },
                      { key: 'channel_type', label: '类型' },
                      { key: 'channel_protocol', label: '协议' },
                      { key: 'agent_id', label: 'Agent ID', render: (value) => <code className="text-xs">{String(value).slice(0, 12)}...</code> },
                    ]}
                    data={channels}
                    actions={(row) => (
                      <div className="flex gap-1">
                        <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDelete('channels', row.channel_id)}>删除</Button>
                      </div>
                    )}
                  />
                )}

                {/* Sessions Tab */}
                {activeTab === 'sessions' && (
                  <DataTable<Session>
                    columns={[
                      { key: 'session_id', label: 'ID', render: (value) => <code className="text-xs">{String(value).slice(0, 12)}...</code> },
                      { key: 'session_name', label: '名称', render: (value) => String(value || '未命名') },
                      { key: 'status', label: '状态', render: (value) => statusBadge(String(value)) },
                      { key: 'updated_at', label: '最后活跃', render: (value) => formatTime(value as string | null) },
                      { key: 'create_time', label: '创建时间', render: (value) => formatTime(value as string | null) },
                    ]}
                    data={sessions}
                    actions={(row) => (
                      <div className="flex gap-1">
                        <Button variant="ghost" size="sm" onClick={() => setEditingSession(row)}>状态</Button>
                        <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDelete('sessions', row.session_id)}>删除</Button>
                      </div>
                    )}
                  />
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Edit Modals */}
      {editingUser && (
        <EditModal
          title="编辑用户"
          fields={[{ key: 'name', label: '用户名称' }]}
          values={{ name: editingUser.name }}
          onSave={handleUpdateUser}
          onCancel={() => setEditingUser(null)}
        />
      )}
      {editingAgent && (
        <EditModal
          title="编辑 Agent"
          fields={[
            { key: 'agent_name', label: 'Agent 名称' },
            { key: 'agent_persona', label: '人设描述', type: 'textarea' },
          ]}
          values={{
            agent_name: editingAgent.agent_name,
            agent_persona: editingAgent.agent_persona,
          }}
          onSave={handleUpdateAgent}
          onCancel={() => setEditingAgent(null)}
        />
      )}
      {editingSession && (
        <EditModal
          title="修改会话状态"
          fields={[{ key: 'status', label: '状态（active / closed / archived）' }]}
          values={{ status: editingSession.status }}
          onSave={handleUpdateSessionStatus}
          onCancel={() => setEditingSession(null)}
        />
      )}
    </div>
  );
}
