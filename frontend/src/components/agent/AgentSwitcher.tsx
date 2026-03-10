/**
 * Agent 切换器组件
 *
 * 在顶部 Header 中展示当前 Agent，点击后弹出下拉面板，
 * 列出所有可用 Agent 供用户切换。
 */

import { useEffect, useRef, useState } from 'react';
import { AgentInfo, listAgents } from '@/services/api';

/** 根据 agent_type 返回对应的颜色方案 */
function getAgentColorScheme(agentType: string, agentId: string): {
  avatarBg: string;
  avatarText: string;
  typeBadgeBg: string;
  typeBadgeText: string;
  activeRing: string;
} {
  // 用 agent_id 的字符生成一个稳定的色相索引
  const colorPalettes = [
    { avatarBg: 'bg-violet-600', avatarText: 'text-white', typeBadgeBg: 'bg-violet-100 dark:bg-violet-900/40', typeBadgeText: 'text-violet-700 dark:text-violet-300', activeRing: 'ring-violet-500' },
    { avatarBg: 'bg-blue-600', avatarText: 'text-white', typeBadgeBg: 'bg-blue-100 dark:bg-blue-900/40', typeBadgeText: 'text-blue-700 dark:text-blue-300', activeRing: 'ring-blue-500' },
    { avatarBg: 'bg-emerald-600', avatarText: 'text-white', typeBadgeBg: 'bg-emerald-100 dark:bg-emerald-900/40', typeBadgeText: 'text-emerald-700 dark:text-emerald-300', activeRing: 'ring-emerald-500' },
    { avatarBg: 'bg-orange-500', avatarText: 'text-white', typeBadgeBg: 'bg-orange-100 dark:bg-orange-900/40', typeBadgeText: 'text-orange-700 dark:text-orange-300', activeRing: 'ring-orange-500' },
    { avatarBg: 'bg-pink-600', avatarText: 'text-white', typeBadgeBg: 'bg-pink-100 dark:bg-pink-900/40', typeBadgeText: 'text-pink-700 dark:text-pink-300', activeRing: 'ring-pink-500' },
    { avatarBg: 'bg-cyan-600', avatarText: 'text-white', typeBadgeBg: 'bg-cyan-100 dark:bg-cyan-900/40', typeBadgeText: 'text-cyan-700 dark:text-cyan-300', activeRing: 'ring-cyan-500' },
  ];

  // main 类型固定用紫色，specialized 按 id 哈希选色
  if (agentType === 'main') {
    return colorPalettes[0];
  }

  const hashIndex = agentId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colorPalettes[(hashIndex % (colorPalettes.length - 1)) + 1];
}

/** 从 agent_name 取首字母作为头像文字 */
function getAvatarInitials(agentName: string): string {
  const words = agentName.trim().split(/[\s_-]+/);
  if (words.length >= 2) {
    return (words[0][0] + words[1][0]).toUpperCase();
  }
  return agentName.slice(0, 2).toUpperCase();
}

interface AgentSwitcherProps {
  currentAgentId: string | null;
  onAgentChange: (agent: AgentInfo) => void;
}

export function AgentSwitcher({ currentAgentId, onAgentChange }: AgentSwitcherProps) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 加载 agent 列表
  const loadAgents = async () => {
    try {
      setIsLoading(true);
      setLoadError(false);
      const agentList = await listAgents();
      setAgents(agentList);
    } catch (error) {
      console.error('Failed to load agents:', error);
      setLoadError(true);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAgents();
  }, []);

  // 点击外部关闭下拉
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentAgent = agents.find(agent => agent.agent_id === currentAgentId) ?? agents[0] ?? null;

  function handleSelectAgent(agent: AgentInfo) {
    setIsOpen(false);
    if (agent.agent_id !== currentAgentId) {
      onAgentChange(agent);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 animate-pulse">
        <div className="w-6 h-6 rounded-full bg-gray-300 dark:bg-gray-600" />
        <div className="w-20 h-3 rounded bg-gray-300 dark:bg-gray-600" />
      </div>
    );
  }

  if (loadError || agents.length === 0) {
    return (
      <button
        onClick={loadAgents}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
        title={loadError ? '加载 Agent 列表失败，点击重试' : '暂无 Agent'}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {loadError ? '重试加载 Agent' : '无 Agent'}
      </button>
    );
  }

  return (
    <div className="relative" ref={dropdownRef}>
      {/* 触发按钮：当前 Agent */}
      <button
        onClick={() => setIsOpen(prev => !prev)}
        className={`
          flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all duration-150
          bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700
          border border-transparent hover:border-gray-300 dark:hover:border-gray-600
          ${isOpen ? 'border-gray-300 dark:border-gray-600 bg-gray-200 dark:bg-gray-700' : ''}
        `}
        title="切换 Agent"
      >
        {currentAgent ? (
          <>
            <AgentAvatar agent={currentAgent} size="sm" />
            <span className="text-sm font-medium text-gray-800 dark:text-gray-200 max-w-[120px] truncate">
              {currentAgent.agent_name}
            </span>
            {currentAgent.agent_type === 'main' && (
              <span className="hidden sm:inline-block text-xs px-1.5 py-0.5 rounded-full bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300 font-medium">
                主
              </span>
            )}
          </>
        ) : (
          <span className="text-sm text-gray-500">选择 Agent</span>
        )}
        <svg
          className={`w-3.5 h-3.5 text-gray-400 transition-transform duration-150 ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* 下拉面板 */}
      {isOpen && (
        <div className="
          absolute top-full left-0 mt-2 z-50
          w-72 rounded-xl shadow-xl
          bg-white dark:bg-gray-900
          border border-gray-200 dark:border-gray-700
          overflow-hidden
          animate-in fade-in slide-in-from-top-2 duration-150
        ">
          {/* 面板标题 */}
          <div className="px-4 py-2.5 border-b border-gray-100 dark:border-gray-800">
            <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
              切换 Agent
            </p>
          </div>

          {/* Agent 列表 */}
          <div className="py-1.5 max-h-80 overflow-y-auto">
            {agents.map(agent => {
              const isActive = agent.agent_id === (currentAgent?.agent_id);
              const colorScheme = getAgentColorScheme(agent.agent_type, agent.agent_id);
              const features = agent.feature
                ? agent.feature.split(',').map(f => f.trim()).filter(Boolean)
                : [];

              return (
                <button
                  key={agent.agent_id}
                  onClick={() => handleSelectAgent(agent)}
                  className={`
                    w-full flex items-start gap-3 px-4 py-3 text-left transition-colors duration-100
                    hover:bg-gray-50 dark:hover:bg-gray-800/60
                    ${isActive ? 'bg-gray-50 dark:bg-gray-800/60' : ''}
                  `}
                >
                  {/* 头像 */}
                  <div className="flex-shrink-0 relative mt-0.5">
                    <AgentAvatar agent={agent} size="md" />
                    {isActive && (
                      <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-green-500 border-2 border-white dark:border-gray-900" />
                    )}
                  </div>

                  {/* 信息 */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-semibold truncate ${isActive ? 'text-gray-900 dark:text-white' : 'text-gray-700 dark:text-gray-300'}`}>
                        {agent.agent_name}
                      </span>
                      <span className={`flex-shrink-0 text-xs px-1.5 py-0.5 rounded-full font-medium ${colorScheme.typeBadgeBg} ${colorScheme.typeBadgeText}`}>
                        {agent.agent_type === 'main' ? '主 Agent' : '专用'}
                      </span>
                    </div>

                    {/* ID */}
                    <p className="text-xs text-gray-400 dark:text-gray-500 font-mono mt-0.5 truncate">
                      {agent.agent_id}
                    </p>

                    {/* 特性标签 */}
                    {features.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {features.slice(0, 3).map(feature => (
                          <span
                            key={feature}
                            className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400"
                          >
                            {feature}
                          </span>
                        ))}
                        {features.length > 3 && (
                          <span className="text-xs text-gray-400">+{features.length - 3}</span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* 选中勾 */}
                  {isActive && (
                    <svg className="flex-shrink-0 w-4 h-4 text-violet-500 mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>

          {/* 底部提示 */}
          <div className="px-4 py-2 border-t border-gray-100 dark:border-gray-800">
            <p className="text-xs text-gray-400 dark:text-gray-500">
              共 {agents.length} 个 Agent · 切换后将开启新会话
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/** Agent 头像子组件 */
function AgentAvatar({ agent, size }: { agent: AgentInfo; size: 'sm' | 'md' }) {
  const colorScheme = getAgentColorScheme(agent.agent_type, agent.agent_id);
  const initials = getAvatarInitials(agent.agent_name);
  const sizeClass = size === 'sm' ? 'w-6 h-6 text-xs' : 'w-8 h-8 text-sm';

  return (
    <div className={`${sizeClass} ${colorScheme.avatarBg} ${colorScheme.avatarText} rounded-full flex items-center justify-center font-bold flex-shrink-0`}>
      {initials}
    </div>
  );
}
