/** TraceTimeline - Timeline view for trace visualization */
import { useState } from 'react';
import type { TraceRawDataResponse, XAgentLogEntry, PromptLLMLogEntry } from '@/types';

interface TraceTimelineProps {
  traceData: TraceRawDataResponse;
  onEventSelect?: (event: any, type: 'x-agent' | 'prompt-llm') => void;
}

// Define event types for categorization
type EventType =
  | 'api'
  | 'agent'
  | 'llm'
  | 'tool'
  | 'skill'
  | 'command'
  | 'memory'
  | 'memory_store'
  | 'memory_query'
  | 'react_loop'
  | 'plan_mode'
  | 'middleware'
  | 'service'
  | 'error'
  | 'info'
  | 'unknown';

interface TimelineEvent {
  id: string;
  timestamp: string;
  eventType: EventType;
  module: string;
  message: string;
  level: string;
  source: 'x-agent' | 'prompt-llm';
  data: any;
  durationMs?: number;
}

function getEventTypeFromEvent(event: any, source: 'x-agent' | 'prompt-llm'): EventType {
  if (source === 'prompt-llm') {
    return 'llm';
  }

  const module = event.module?.toLowerCase() || '';
  const eventMsg = event.event?.toLowerCase() || event.message?.toLowerCase() || '';
  const data = event.data || {};

  // Check for specific operation types first
  if (data.operation_type) {
    switch (data.operation_type) {
      case 'tool_call':
        return 'tool';
      case 'skill_call':
        return 'skill';
      case 'command':
        return 'command';
      case 'memory_store':
        return 'memory_store';
      case 'memory_query':
        return 'memory_query';
      case 'react_loop':
        return 'react_loop';
      case 'plan_mode':
        return 'plan_mode';
      default:
        break;
    }
  }

  // Then check based on module and event
  if (module.includes('api')) return 'api';
  if (module.includes('agent')) return 'agent';
  if (module.includes('tool')) return 'tool';
  if (module.includes('skill')) return 'skill';
  if (module.includes('command') || module.includes('terminal')) return 'command';
  if (module.includes('memory') || module.includes('vector_store')) return 'memory';
  if (module.includes('react') || module.includes('reasoning')) return 'react_loop';
  if (module.includes('plan') || module.includes('planner')) return 'plan_mode';
  if (module.includes('middleware')) return 'middleware';
  if (module.includes('service')) return 'service';

  // Check event message content
  if (eventMsg.includes('tool') || eventMsg.includes('call')) return 'tool';
  if (eventMsg.includes('skill')) return 'skill';
  if (eventMsg.includes('command') || eventMsg.includes('execute')) return 'command';
  if (eventMsg.includes('memory') || eventMsg.includes('store') || eventMsg.includes('query')) return 'memory';
  if (eventMsg.includes('react') || eventMsg.includes('think') || eventMsg.includes('act') || eventMsg.includes('observe')) return 'react_loop';
  if (eventMsg.includes('plan')) return 'plan_mode';

  // Check data content
  if (data.tool_name) return 'tool';
  if (data.skill_name) return 'skill';
  if (data.command) return 'command';
  if (data.memory_type || data.query) return 'memory';

  // Default based on level
  if (event.level === 'error') return 'error';
  if (event.level === 'info') return 'info';

  return 'unknown';
}

function getEventIcon(eventType: EventType) {
  switch (eventType) {
    case 'api':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
          <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
          <line x1="8" y1="6" x2="16" y2="6"></line>
          <line x1="8" y1="18" x2="12" y2="18"></line>
        </svg>
      );
    case 'llm':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon>
        </svg>
      );
    case 'tool':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
          <line x1="8" y1="21" x2="16" y2="21"></line>
          <line x1="12" y1="17" x2="12" y2="21"></line>
        </svg>
      );
    case 'skill':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M8 12h8"></path>
          <path d="M12 8h0"></path>
        </svg>
      );
    case 'command':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="16 18 22 12 16 6"></polyline>
          <polyline points="8 6 2 12 8 18"></polyline>
        </svg>
      );
    case 'memory':
    case 'memory_store':
    case 'memory_query':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="6" width="20" height="12" rx="2"></rect>
          <path d="M12 12h.01"></path>
          <path d="M8 12h.01"></path>
          <path d="M16 12h.01"></path>
        </svg>
      );
    case 'react_loop':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.3 20v-6M13.7 14v6M16.5 12.5a4.5 4.5 0 0 0-9 0"></path>
          <path d="M18 3.5a4.5 4.5 0 0 0-9 0"></path>
          <path d="M20 20a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2"></path>
        </svg>
      );
    case 'plan_mode':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
          <line x1="16" y1="2" x2="16" y2="6"></line>
          <line x1="8" y1="2" x2="8" y2="6"></line>
          <line x1="3" y1="10" x2="21" y2="10"></line>
        </svg>
      );
    case 'error':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="15" y1="9" x2="9" y2="15"></line>
          <line x1="9" y1="9" x2="15" y2="15"></line>
        </svg>
      );
    default:
      return (
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="8" x2="12" y2="12"></line>
          <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
      );
  }
}

function getEventColor(eventType: EventType) {
  switch (eventType) {
    case 'api': return 'bg-blue-100 text-blue-800 border-blue-200';
    case 'llm': return 'bg-amber-100 text-amber-800 border-amber-200';
    case 'tool': return 'bg-orange-100 text-orange-800 border-orange-200';
    case 'skill': return 'bg-purple-100 text-purple-800 border-purple-200';
    case 'command': return 'bg-cyan-100 text-cyan-800 border-cyan-200';
    case 'memory':
    case 'memory_store':
    case 'memory_query': return 'bg-green-100 text-green-800 border-green-200';
    case 'react_loop': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    case 'plan_mode': return 'bg-pink-100 text-pink-800 border-pink-200';
    case 'error': return 'bg-red-100 text-red-800 border-red-200';
    case 'info': return 'bg-gray-100 text-gray-800 border-gray-200';
    default: return 'bg-gray-100 text-gray-800 border-gray-200';
  }
}

function formatTimestamp(timestamp: string) {
  try {
    const date = new Date(timestamp);
    return date.toLocaleString();
  } catch {
    return timestamp;
  }
}

function TraceTimeline({ traceData, onEventSelect }: TraceTimelineProps) {
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<EventType | 'all'>('all');

  // Combine and sort all events by timestamp
  const allEvents: TimelineEvent[] = [];

  // Process x-agent logs
  traceData.x_agent_logs.forEach((log: XAgentLogEntry, index: number) => {
    const eventType = getEventTypeFromEvent(log, 'x-agent');
    if (filter !== 'all' && filter !== eventType) return;

    allEvents.push({
      id: `x-agent-${index}-${log.timestamp || index}`,
      timestamp: log.timestamp || '',
      eventType,
      module: log.module,
      message: log.message,
      level: log.level || 'info',
      source: 'x-agent',
      data: log.data,
    });
  });

  // Process prompt logs
  traceData.prompt_llm_logs.forEach((log: PromptLLMLogEntry, index: number) => {
    const eventType: EventType = 'llm';
    if (filter !== 'all' && filter !== eventType) return;

    allEvents.push({
      id: `prompt-${index}-${log.timestamp}`,
      timestamp: log.timestamp,
      eventType,
      module: 'llm',
      message: 'LLM Request/Response',
      level: 'info',
      source: 'prompt-llm',
      data: log,
    });
  });

  // Sort events by timestamp
  allEvents.sort((a, b) => {
    if (a.timestamp < b.timestamp) return -1;
    if (a.timestamp > b.timestamp) return 1;
    return 0;
  });

  // Calculate durations between consecutive events
  for (let i = 1; i < allEvents.length; i++) {
    const prevEvent = allEvents[i - 1];
    const currEvent = allEvents[i];

    try {
      const prevTime = new Date(prevEvent.timestamp).getTime();
      const currTime = new Date(currEvent.timestamp).getTime();
      const duration = currTime - prevTime;

      if (duration >= 0) {
        currEvent.durationMs = duration;
      }
    } catch (e) {
      // If parsing fails, skip duration calculation
    }
  }

  const toggleEventExpansion = (eventId: string) => {
    setExpandedEvents(prev => {
      const newSet = new Set(prev);
      if (newSet.has(eventId)) {
        newSet.delete(eventId);
      } else {
        newSet.add(eventId);
      }
      return newSet;
    });
  };

  const eventTypeCounts = allEvents.reduce((acc, event) => {
    acc[event.eventType] = (acc[event.eventType] || 0) + 1;
    return acc;
  }, {} as Record<EventType, number>);

  return (
    <div className="h-full flex flex-col">
      {/* Filters */}
      <div className="p-4 bg-gray-50 border-b border-gray-200">
        <div className="flex flex-wrap gap-2">
          <button
            className={`px-3 py-1.5 rounded-full text-sm ${filter === 'all' ? 'bg-blue-500 text-white' : 'bg-white text-gray-700 border border-gray-300'}`}
            onClick={() => setFilter('all')}
          >
            全部 ({allEvents.length})
          </button>

          {(['api', 'llm', 'tool', 'skill', 'command', 'memory', 'react_loop', 'plan_mode', 'error'] as EventType[]).map(type => (
            eventTypeCounts[type] > 0 && (
              <button
                key={type}
                className={`px-3 py-1.5 rounded-full text-sm flex items-center gap-1 ${
                  filter === type
                    ? `${getEventColor(type)} border-2`
                    : `bg-white text-gray-700 border ${getEventColor(type).split(' ')[2]}`
                }`}
                onClick={() => setFilter(type)}
              >
                {getEventIcon(type)}
                {type} ({eventTypeCounts[type]})
              </button>
            )
          ))}
        </div>
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {allEvents.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            没有找到匹配的事件
          </div>
        ) : (
          allEvents.map((event, index) => {
            const isExpanded = expandedEvents.has(event.id);
            const eventColorClass = getEventColor(event.eventType);

            return (
              <div
                key={event.id}
                className="bg-white border border-gray-200 rounded-lg overflow-hidden transition-all duration-200"
              >
                <div
                  className={`p-4 cursor-pointer hover:bg-gray-50 flex items-start gap-3 ${isExpanded ? 'bg-blue-50' : ''}`}
                  onClick={() => {
                    toggleEventExpansion(event.id);
                    if (onEventSelect) {
                      onEventSelect(event, event.source);
                    }
                  }}
                >
                  <div className={`p-2 rounded-full ${eventColorClass}`}>
                    {getEventIcon(event.eventType)}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-medium text-gray-900">
                          {event.message || event.eventType}
                        </div>
                        <div className="text-xs text-gray-500 mt-1 flex items-center gap-2">
                          <span>{formatTimestamp(event.timestamp)}</span>
                          <span className="text-gray-300">•</span>
                          <span className="font-mono">{event.module}</span>
                          {event.durationMs !== undefined && event.durationMs > 0 && (
                            <>
                              <span className="text-gray-300">•</span>
                              <span className="text-green-600 font-mono">{event.durationMs}ms</span>
                            </>
                          )}
                        </div>
                      </div>

                      <div className={`px-2 py-1 rounded-full text-xs ${eventColorClass}`}>
                        {event.eventType.toUpperCase()}
                      </div>
                    </div>
                  </div>

                  <div className="text-gray-400">
                    {isExpanded ? '▲' : '▼'}
                  </div>
                </div>

                {isExpanded && (
                  <div className="border-t border-gray-100 bg-gray-50 p-4 text-sm">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <h4 className="font-medium text-gray-700 mb-2">事件详情</h4>
                        <div className="space-y-2">
                          <div>
                            <span className="text-gray-500">ID:</span>
                            <span className="ml-2 font-mono text-xs break-all">{event.id}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">来源:</span>
                            <span className="ml-2 font-medium">{event.source}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">级别:</span>
                            <span className="ml-2 font-medium">{event.level}</span>
                          </div>
                          {event.durationMs !== undefined && event.durationMs > 0 && (
                            <div>
                              <span className="text-gray-500">间隔:</span>
                              <span className="ml-2 font-medium text-green-600">{event.durationMs}ms</span>
                            </div>
                          )}
                        </div>
                      </div>

                      <div>
                        <h4 className="font-medium text-gray-700 mb-2">数据详情</h4>
                        <pre className="bg-white p-3 rounded text-xs overflow-auto max-h-40">
                          {JSON.stringify(event.data, null, 2)}
                        </pre>
                      </div>
                    </div>

                    {event.source === 'prompt-llm' && (
                      <div className="mt-4 pt-4 border-t border-gray-200">
                        <h4 className="font-medium text-gray-700 mb-2">LLM 请求/响应详情</h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <h5 className="text-sm font-medium text-gray-600 mb-1">请求</h5>
                            <pre className="bg-white p-3 rounded text-xs overflow-auto max-h-40">
                              {JSON.stringify((event.data as PromptLLMLogEntry).request, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <h5 className="text-sm font-medium text-gray-600 mb-1">响应</h5>
                            <pre className="bg-white p-3 rounded text-xs overflow-auto max-h-40">
                              {typeof (event.data as PromptLLMLogEntry).response === 'string'
                                ? (event.data as PromptLLMLogEntry).response
                                : JSON.stringify((event.data as PromptLLMLogEntry).response, null, 2)}
                            </pre>
                          </div>
                        </div>
                        <div className="mt-3 text-sm">
                          <div className="flex gap-4">
                            <div>
                              <span className="text-gray-500">模型:</span>
                              <span className="ml-2">{(event.data as PromptLLMLogEntry).model}</span>
                            </div>
                            <div>
                              <span className="text-gray-500">提供商:</span>
                              <span className="ml-2">{(event.data as PromptLLMLogEntry).provider}</span>
                            </div>
                            <div>
                              <span className="text-gray-500">延迟:</span>
                              <span className="ml-2 text-green-600">{(event.data as PromptLLMLogEntry).latency_ms}ms</span>
                            </div>
                          </div>
                        </div>
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

export default TraceTimeline;