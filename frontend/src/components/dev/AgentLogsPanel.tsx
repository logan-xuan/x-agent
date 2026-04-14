/**
 * Agent Logs Panel - Agent Core 日志调试面板
 * 
 * 展示 Agent Core 的日志、LLM 调用、工具调用等信息。
 * 采用三栏布局：左侧 Trace 列表 | 中间日志时间线 | 右侧详情
 */

import { useState, useEffect, useCallback } from 'react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

// ============================================================
// Types
// ============================================================

interface LogEntry {
    id: string;
    trace_id: string | null;
    level: string;
    category: string;
    event: string;
    message: string;
    data: Record<string, unknown>;
    timestamp: string;
    duration_ms: number | null;
    error: string | null;
}

interface LLMCall {
    call_id: string;
    trace_id: string | null;
    model: string;
    provider: string | null;
    status: string;
    start_time: string;
    end_time: string | null;
    duration_ms: number | null;
    message_count: number;
    estimated_tokens: number | null;
    usage: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null;
    stop_reason: string | null;
    error: string | null;
    system_prompt?: string;
    messages?: Array<{ role: string; content: unknown }>;
    tools?: Array<{ type: string; function: { name: string; description: string; parameters?: unknown } }>;
    response_content?: unknown;
}

interface ToolCall {
    call_id: string;
    trace_id: string | null;
    llm_call_id: string | null;
    tool_name: string;
    tool_call_id: string | null;
    status: string;
    start_time: string;
    end_time: string | null;
    duration_ms: number | null;
    arguments: Record<string, unknown>;
    result: unknown;
    is_error: boolean;
    error: string | null;
}

interface TraceOverview {
    trace_id: string;
    first_event: string;
    last_event: string;
    log_count: number;
    llm_call_count: number;
    tool_call_count: number;
    total_duration_ms: number | null;
    has_error: boolean;
}

interface TraceDetail {
    trace_id: string;
    logs: LogEntry[];
    llm_calls: LLMCall[];
    tool_calls: ToolCall[];
}

interface AgentLogsPanelProps {
    onError?: (error: string) => void;
}

// ============================================================
// API Functions
// ============================================================

const API_BASE = '/api/v1/agent';

async function fetchTraces(): Promise<TraceOverview[]> {
    const res = await fetch(`${API_BASE}/traces?limit=30`);
    if (!res.ok) throw new Error(`Failed to fetch traces: ${res.statusText}`);
    return res.json();
}

async function fetchTraceDetail(traceId: string): Promise<TraceDetail> {
    const res = await fetch(`${API_BASE}/traces/${traceId}`);
    if (!res.ok) throw new Error(`Failed to fetch trace: ${res.statusText}`);
    return res.json();
}

async function fetchStats(): Promise<{ log_count: number; llm_call_count: number; tool_call_count: number }> {
    const res = await fetch(`${API_BASE}/stats`);
    if (!res.ok) throw new Error(`Failed to fetch stats: ${res.statusText}`);
    return res.json();
}

// ============================================================
// Helper Functions
// ============================================================

function formatTime(isoString: string): string {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleTimeString('zh-CN', { hour12: false });
}

function formatDuration(ms: number | null): string {
    if (ms === null || ms === undefined) return '-';
    if (ms < 1000) return `${ms.toFixed(0)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
}

function getLevelColor(level: string): string {
    switch (level) {
        case 'error': return 'text-red-500';
        case 'warn': return 'text-yellow-500';
        case 'info': return 'text-blue-500';
        case 'debug': return 'text-gray-400';
        default: return 'text-gray-500';
    }
}

function getStatusBadge(status: string): { color: 'default' | 'success' | 'warning' | 'destructive'; text: string } {
    switch (status) {
        case 'completed': return { color: 'success', text: '完成' };
        case 'pending': return { color: 'warning', text: '进行中' };
        case 'executing': return { color: 'warning', text: '执行中' };
        case 'error': return { color: 'destructive', text: '错误' };
        default: return { color: 'default', text: status };
    }
}

// ============================================================
// Components
// ============================================================

/** Trace 列表项 */
function TraceItem({
    trace,
    isSelected,
    onClick
}: {
    trace: TraceOverview;
    isSelected: boolean;
    onClick: () => void;
}) {
    return (
        <div
            className={`p-3 cursor-pointer border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 ${isSelected ? 'bg-blue-50 dark:bg-blue-900/20 border-l-2 border-l-blue-500' : ''
                }`}
            onClick={onClick}
        >
            <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-mono text-gray-600 dark:text-gray-400 truncate max-w-[120px]">
                    {trace.trace_id}
                </span>
                {trace.has_error && (
                    <span className="w-2 h-2 rounded-full bg-red-500" title="包含错误" />
                )}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-500">
                {formatTime(trace.last_event)}
            </div>
            <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                <span title="LLM 调用">{trace.llm_call_count} LLM</span>
                <span title="工具调用">{trace.tool_call_count} Tool</span>
                {trace.total_duration_ms && (
                    <span title="总耗时">{formatDuration(trace.total_duration_ms)}</span>
                )}
            </div>
        </div>
    );
}

/** Prompt 预览组件 */
function PromptPreview({ systemPrompt, messages }: { systemPrompt?: string; messages?: Array<{ role: string; content: unknown }> }) {
    const [showFullPrompt, setShowFullPrompt] = useState(false);

    // 构建完整 prompt 预览
    const fullPromptLines: string[] = [];
    if (systemPrompt) {
        fullPromptLines.push(`[SYSTEM]`);
        fullPromptLines.push(systemPrompt);
        fullPromptLines.push('');
    }
    if (messages && messages.length > 0) {
        messages.forEach((msg) => {
            const content = typeof msg.content === 'string'
                ? msg.content
                : JSON.stringify(msg.content, null, 2);
            fullPromptLines.push(`[${msg.role.toUpperCase()}]`);
            fullPromptLines.push(content.slice(0, 500) + (content.length > 500 ? '...' : ''));
            fullPromptLines.push('');
        });
    }

    const previewText = fullPromptLines.join('\n');

    return (
        <div className="border border-gray-200 dark:border-gray-700 rounded overflow-hidden">
            <div
                className="px-3 py-2 bg-gray-50 dark:bg-gray-800 flex items-center justify-between cursor-pointer"
                onClick={() => setShowFullPrompt(!showFullPrompt)}
            >
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">完整 Prompt</span>
                <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">
                        {systemPrompt ? `System: ${systemPrompt.length} chars` : 'No System Prompt'}
                        {messages && ` | ${messages.length} messages`}
                    </span>
                    <span className="text-gray-400">{showFullPrompt ? '▼' : '▶'}</span>
                </div>
            </div>
            {showFullPrompt && (
                <div className="p-3 text-xs overflow-auto max-h-96 bg-gray-900 text-green-400 whitespace-pre-wrap font-mono">
                    {previewText || '(空)'}
                </div>
            )}
        </div>
    );
}

/** Tools 预览组件 - 展示传给 LLM 的可用工具列表 */
function ToolsPreview({ tools }: { tools: Array<{ type: string; function: { name: string; description: string; parameters?: unknown } }> }) {
    const [expanded, setExpanded] = useState(false);
    const [expandedTool, setExpandedTool] = useState<string | null>(null);

    return (
        <div className="border border-gray-200 dark:border-gray-700 rounded overflow-hidden">
            <div
                className="px-3 py-2 bg-gray-50 dark:bg-gray-800 flex items-center justify-between cursor-pointer"
                onClick={() => setExpanded(!expanded)}
            >
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    🔧 可用工具
                </span>
                <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">{tools.length} 个工具</span>
                    <span className="text-gray-400">{expanded ? '▼' : '▶'}</span>
                </div>
            </div>
            {expanded && (
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                    {tools.map((tool) => {
                        const funcName = tool.function?.name || 'unknown';
                        const funcDesc = tool.function?.description || '';
                        const isToolExpanded = expandedTool === funcName;

                        return (
                            <div key={funcName} className="px-3 py-2">
                                <div
                                    className="flex items-center gap-2 cursor-pointer"
                                    onClick={() => setExpandedTool(isToolExpanded ? null : funcName)}
                                >
                                    <span className="text-xs text-gray-400">{isToolExpanded ? '▼' : '▶'}</span>
                                    <code className="text-sm font-mono text-blue-600 dark:text-blue-400">{funcName}</code>
                                    <span className="text-xs text-gray-400 truncate flex-1">
                                        {funcDesc.slice(0, 80)}{funcDesc.length > 80 ? '...' : ''}
                                    </span>
                                </div>
                                {isToolExpanded && (
                                    <div className="mt-2 ml-5 p-2 bg-gray-900 rounded text-xs text-green-400 font-mono whitespace-pre-wrap overflow-auto max-h-48">
                                        {JSON.stringify(tool, null, 2)}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

/** 时间线事件项 */
function TimelineItem({
    item,
    type,
    isSelected,
    onClick,
}: {
    item: LogEntry | LLMCall | ToolCall;
    type: 'log' | 'llm' | 'tool';
    isSelected: boolean;
    onClick: () => void;
}) {
    const getIcon = () => {
        if (type === 'llm') return '🤖';
        if (type === 'tool') return '🔧';
        return '📝';
    };

    const getTitle = () => {
        if (type === 'llm') return (item as LLMCall).model;
        if (type === 'tool') return (item as ToolCall).tool_name;
        return (item as LogEntry).event;
    };

    const getTime = () => {
        if (type === 'log') return (item as LogEntry).timestamp;
        return (item as LLMCall | ToolCall).start_time;
    };

    const getStatus = () => {
        if (type === 'log') return (item as LogEntry).level;
        return (item as LLMCall | ToolCall).status;
    };

    const getDuration = () => {
        if (type === 'log') return (item as LogEntry).duration_ms;
        return (item as LLMCall | ToolCall).duration_ms;
    };

    const getItemTraceId = () => {
        return (item as LogEntry | LLMCall | ToolCall).trace_id;
    };

    return (
        <div
            className={`flex items-start gap-2 p-2 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded ${isSelected ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                }`}
            onClick={onClick}
        >
            <span className="text-sm">{getIcon()}</span>
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{getTitle()}</span>
                    {type !== 'log' && (
                        <Badge variant={getStatusBadge(getStatus()).color} className="text-xs">
                            {getStatusBadge(getStatus()).text}
                        </Badge>
                    )}
                    {type === 'log' && (
                        <span className={`text-xs ${getLevelColor(getStatus())}`}>
                            {getStatus().toUpperCase()}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2 text-xs text-gray-500 mt-0.5">
                    <span>{formatTime(getTime())}</span>
                    {getDuration() !== null && <span>{formatDuration(getDuration())}</span>}
                    {/* 显示 trace_id */}
                    {getItemTraceId() && (
                        <span className="font-mono text-gray-400 truncate max-w-[80px]" title={`Trace: ${getItemTraceId()}`}>
                            📍{getItemTraceId()}
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}

/** JSON 查看器 */
function JsonViewer({ data, title }: { data: unknown; title?: string }) {
    const [isExpanded, setIsExpanded] = useState(true);

    // 计算内容长度用于显示
    const contentStr = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
    const contentLength = contentStr.length;

    return (
        <div className="border border-gray-200 dark:border-gray-700 rounded overflow-hidden">
            {title && (
                <div
                    className="px-3 py-2 bg-gray-50 dark:bg-gray-800 flex items-center justify-between cursor-pointer"
                    onClick={() => setIsExpanded(!isExpanded)}
                >
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{title}</span>
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-400">{contentLength} chars</span>
                        <span className="text-gray-400">{isExpanded ? '▼' : '▶'}</span>
                    </div>
                </div>
            )}
            {isExpanded && (
                <pre className="p-3 text-xs overflow-auto max-h-64 bg-gray-900 text-green-400 whitespace-pre-wrap">
                    {typeof data === 'string' ? data : JSON.stringify(data, null, 2)}
                </pre>
            )}
        </div>
    );
}

/** 详情面板 */
function DetailPanel({
    selectedItem,
    selectedType
}: {
    selectedItem: LogEntry | LLMCall | ToolCall | null;
    selectedType: 'log' | 'llm' | 'tool' | null;
}) {
    if (!selectedItem || !selectedType) {
        return (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                选择一个事件查看详情
            </div>
        );
    }

    if (selectedType === 'log') {
        const log = selectedItem as LogEntry;
        return (
            <div className="p-4 space-y-4 overflow-auto h-full">
                <div>
                    <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">{log.event}</h3>
                    <p className="text-sm text-gray-500 mt-1">{log.message}</p>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span className="text-gray-500">级别</span>
                        <span className={`ml-2 ${getLevelColor(log.level)}`}>{log.level.toUpperCase()}</span>
                    </div>
                    <div>
                        <span className="text-gray-500">分类</span>
                        <span className="ml-2 text-gray-700 dark:text-gray-300">{log.category}</span>
                    </div>
                    <div>
                        <span className="text-gray-500">时间</span>
                        <span className="ml-2 text-gray-700 dark:text-gray-300">{formatTime(log.timestamp)}</span>
                    </div>
                    {log.duration_ms !== null && (
                        <div>
                            <span className="text-gray-500">耗时</span>
                            <span className="ml-2 text-gray-700 dark:text-gray-300">{formatDuration(log.duration_ms)}</span>
                        </div>
                    )}
                </div>

                {log.error && (
                    <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded border border-red-200 dark:border-red-800">
                        <span className="text-sm text-red-600 dark:text-red-400">{log.error}</span>
                    </div>
                )}

                {Object.keys(log.data || {}).length > 0 && (
                    <JsonViewer data={log.data} title="附加数据" />
                )}
            </div>
        );
    }

    if (selectedType === 'llm') {
        const llm = selectedItem as LLMCall;
        return (
            <div className="p-4 space-y-4 overflow-auto h-full">
                <div>
                    <div className="flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">LLM 调用</h3>
                        {llm.trace_id && (
                            <span className="text-xs font-mono text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded" title="Trace ID">
                                Trace: {llm.trace_id}
                            </span>
                        )}
                    </div>
                    <p className="text-sm text-gray-500 mt-1">{llm.model} ({llm.provider})</p>
                    <p className="text-xs text-gray-400 font-mono mt-1">Call ID: {llm.call_id}</p>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span className="text-gray-500">状态</span>
                        <Badge variant={getStatusBadge(llm.status).color} className="ml-2">
                            {getStatusBadge(llm.status).text}
                        </Badge>
                    </div>
                    <div>
                        <span className="text-gray-500">耗时</span>
                        <span className="ml-2 text-gray-700 dark:text-gray-300">{formatDuration(llm.duration_ms)}</span>
                    </div>
                    <div>
                        <span className="text-gray-500">消息数</span>
                        <span className="ml-2 text-gray-700 dark:text-gray-300">{llm.message_count}</span>
                    </div>
                    {llm.stop_reason && (
                        <div>
                            <span className="text-gray-500">停止原因</span>
                            <span className="ml-2 text-gray-700 dark:text-gray-300">{llm.stop_reason}</span>
                        </div>
                    )}
                </div>

                {llm.usage && (
                    <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                        <div className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Token 使用</div>
                        <div className="grid grid-cols-3 gap-2 text-sm">
                            <div>
                                <span className="text-gray-500">输入</span>
                                <span className="ml-2">{llm.usage.prompt_tokens ?? '-'}</span>
                            </div>
                            <div>
                                <span className="text-gray-500">输出</span>
                                <span className="ml-2">{llm.usage.completion_tokens ?? '-'}</span>
                            </div>
                            <div>
                                <span className="text-gray-500">总计</span>
                                <span className="ml-2">{llm.usage.total_tokens ?? '-'}</span>
                            </div>
                        </div>
                    </div>
                )}

                {/* Tools 列表 - 传给 LLM 的可用工具 */}
                {llm.tools && llm.tools.length > 0 && (
                    <ToolsPreview tools={llm.tools} />
                )}

                {llm.error && (
                    <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded border border-red-200 dark:border-red-800">
                        <span className="text-sm text-red-600 dark:text-red-400">{llm.error}</span>
                    </div>
                )}

                {/* 完整 Prompt 预览 - 包含 System Prompt */}
                {(llm.system_prompt || (llm.messages && llm.messages.length > 0)) && (
                    <PromptPreview systemPrompt={llm.system_prompt} messages={llm.messages} />
                )}

                {/* System Prompt 独立显示 */}
                {llm.system_prompt && (
                    <JsonViewer data={llm.system_prompt} title="System Prompt (原始)" />
                )}

                {llm.messages && llm.messages.length > 0 && (
                    <JsonViewer data={llm.messages} title="请求消息 (JSON)" />
                )}

                {llm.response_content !== null && llm.response_content !== undefined && (
                    <JsonViewer data={llm.response_content} title="响应内容" />
                )}
            </div>
        );
    }

    if (selectedType === 'tool') {
        const tool = selectedItem as ToolCall;
        return (
            <div className="p-4 space-y-4 overflow-auto h-full">
                <div>
                    <div className="flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">{tool.tool_name}</h3>
                        {tool.trace_id && (
                            <span className="text-xs font-mono text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded" title="Trace ID">
                                Trace: {tool.trace_id}
                            </span>
                        )}
                    </div>
                    <p className="text-xs text-gray-500 font-mono mt-1">Call ID: {tool.call_id}</p>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span className="text-gray-500">状态</span>
                        <Badge variant={getStatusBadge(tool.status).color} className="ml-2">
                            {getStatusBadge(tool.status).text}
                        </Badge>
                    </div>
                    <div>
                        <span className="text-gray-500">耗时</span>
                        <span className="ml-2 text-gray-700 dark:text-gray-300">{formatDuration(tool.duration_ms)}</span>
                    </div>
                </div>

                {tool.error && (
                    <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded border border-red-200 dark:border-red-800">
                        <span className="text-sm text-red-600 dark:text-red-400">{tool.error}</span>
                    </div>
                )}

                <JsonViewer data={tool.arguments} title="输入参数" />

                {tool.result !== null && tool.result !== undefined && (
                    <JsonViewer data={tool.result} title="执行结果" />
                )}
            </div>
        );
    }

    return null;
}

// ============================================================
// Main Component
// ============================================================

export function AgentLogsPanel({ onError }: AgentLogsPanelProps) {
    const [traces, setTraces] = useState<TraceOverview[]>([]);
    const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
    const [traceDetail, setTraceDetail] = useState<TraceDetail | null>(null);
    const [selectedItem, setSelectedItem] = useState<LogEntry | LLMCall | ToolCall | null>(null);
    const [selectedType, setSelectedType] = useState<'log' | 'llm' | 'tool' | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [stats, setStats] = useState<{ log_count: number; llm_call_count: number; tool_call_count: number } | null>(null);
    const [autoRefresh, setAutoRefresh] = useState(false);

    // 加载 trace 列表
    const loadTraces = useCallback(async () => {
        try {
            const data = await fetchTraces();
            setTraces(data);

            // 同时加载统计信息
            const statsData = await fetchStats();
            setStats(statsData);
        } catch (err) {
            onError?.(err instanceof Error ? err.message : 'Failed to load traces');
        }
    }, [onError]);

    // 加载 trace 详情
    const loadTraceDetail = useCallback(async (traceId: string) => {
        setIsLoading(true);
        try {
            const data = await fetchTraceDetail(traceId);
            setTraceDetail(data);
        } catch (err) {
            onError?.(err instanceof Error ? err.message : 'Failed to load trace detail');
        } finally {
            setIsLoading(false);
        }
    }, [onError]);

    // 初始加载
    useEffect(() => {
        loadTraces();
    }, [loadTraces]);

    // 自动刷新
    useEffect(() => {
        if (!autoRefresh) return;

        const interval = setInterval(() => {
            loadTraces();
            if (selectedTraceId) {
                loadTraceDetail(selectedTraceId);
            }
        }, 3000);

        return () => clearInterval(interval);
    }, [autoRefresh, selectedTraceId, loadTraces, loadTraceDetail]);

    // 选择 trace
    const handleSelectTrace = (traceId: string) => {
        setSelectedTraceId(traceId);
        setSelectedItem(null);
        setSelectedType(null);
        loadTraceDetail(traceId);
    };

    // 构建时间线（合并 logs, llm_calls, tool_calls 并按时间排序）
    const timelineItems = traceDetail ? [
        ...traceDetail.logs.map(l => ({ item: l, type: 'log' as const, time: l.timestamp })),
        ...traceDetail.llm_calls.map(l => ({ item: l, type: 'llm' as const, time: l.start_time })),
        ...traceDetail.tool_calls.map(t => ({ item: t, type: 'tool' as const, time: t.start_time })),
    ].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime()) : [];

    return (
        <div className="flex h-full">
            {/* 左侧 Trace 列表 */}
            <div className="w-52 border-r border-gray-200 dark:border-gray-700 flex flex-col">
                <div className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Traces</span>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setAutoRefresh(!autoRefresh)}
                            className={`p-1 rounded ${autoRefresh ? 'text-blue-500' : 'text-gray-400'}`}
                            title={autoRefresh ? '自动刷新: 开启' : '自动刷新: 关闭'}
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                        </button>
                        <Button variant="ghost" size="sm" onClick={loadTraces} className="p-1">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                        </Button>
                    </div>
                </div>

                {/* 统计信息 */}
                {stats && (
                    <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700 text-xs text-gray-500 flex gap-3">
                        <span>{stats.log_count} logs</span>
                        <span>{stats.llm_call_count} LLM</span>
                        <span>{stats.tool_call_count} tools</span>
                    </div>
                )}

                <div className="flex-1 overflow-auto">
                    {traces.length === 0 ? (
                        <div className="p-4 text-sm text-gray-400 text-center">
                            暂无日志
                        </div>
                    ) : (
                        traces.map(trace => (
                            <TraceItem
                                key={trace.trace_id}
                                trace={trace}
                                isSelected={trace.trace_id === selectedTraceId}
                                onClick={() => handleSelectTrace(trace.trace_id)}
                            />
                        ))
                    )}
                </div>
            </div>

            {/* 中间时间线 */}
            <div className="w-80 border-r border-gray-200 dark:border-gray-700 flex flex-col">
                <div className="p-3 border-b border-gray-200 dark:border-gray-700">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        {selectedTraceId ? `事件时间线` : '选择一个 Trace'}
                    </span>
                    {traceDetail && (
                        <span className="text-xs text-gray-400 ml-2">
                            ({timelineItems.length} 个事件)
                        </span>
                    )}
                </div>

                <div className="flex-1 overflow-auto">
                    {isLoading ? (
                        <div className="p-4 text-sm text-gray-400 text-center">加载中...</div>
                    ) : !traceDetail ? (
                        <div className="p-4 text-sm text-gray-400 text-center">
                            选择左侧 Trace 查看详情
                        </div>
                    ) : timelineItems.length === 0 ? (
                        <div className="p-4 text-sm text-gray-400 text-center">
                            无事件
                        </div>
                    ) : (
                        <div className="p-2">
                            {timelineItems.map((entry, idx) => (
                                <TimelineItem
                                    key={`${entry.type}-${idx}`}
                                    item={entry.item}
                                    type={entry.type}
                                    isSelected={selectedItem === entry.item}
                                    onClick={() => {
                                        setSelectedItem(entry.item);
                                        setSelectedType(entry.type);
                                    }}
                                />
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* 右侧详情 */}
            <div className="flex-1 overflow-hidden">
                <DetailPanel selectedItem={selectedItem} selectedType={selectedType} />
            </div>
        </div>
    );
}
