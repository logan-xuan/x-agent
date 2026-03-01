/**
 * Agent 聊天窗口组件
 * 
 * 基于 agent_core 的聊天界面，使用新的 WebSocket 端点 /ws/agent。
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { AgentMessage } from '../../hooks/useAgent';
import { ConnectionStatus } from '../../hooks/useWebSocket';
import { AgentMessageList } from './AgentMessageList';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { DevModeWindow } from '../dev/DevModeWindow';
import { SkillMenu } from '../skills/SkillMenu';
import { Skill, listSkills } from '@/services/api';

interface AgentChatWindowProps {
    sessionId: string | null;
    messages: AgentMessage[];
    streamingContent: string;
    streamingThinking: string;
    isLoading: boolean;
    isConnecting?: boolean;
    connectionStatus: ConnectionStatus;
    onSendMessage: (content: string) => void;
    onAbort: () => void;
    onClearMessages: () => void;
    onOpenSettings?: () => void;
    onNewSession?: () => void;
}

export function AgentChatWindow({
    sessionId,
    messages,
    streamingContent,
    streamingThinking,
    isLoading,
    isConnecting,
    connectionStatus,
    onSendMessage,
    onAbort,
    onClearMessages,
    onOpenSettings,
    onNewSession,
}: AgentChatWindowProps) {
    const [inputValue, setInputValue] = useState('');
    const [isDevModeOpen, setIsDevModeOpen] = useState(false);

    // Skills state
    const [skills, setSkills] = useState<Skill[]>([]);
    const [isLoadingSkills, setIsLoadingSkills] = useState(true);
    const [showSkillMenu, setShowSkillMenu] = useState(false);
    const [menuPosition, setMenuPosition] = useState<{ x: number; y: number } | undefined>();
    const [isComposing, setIsComposing] = useState(false); // Track IME composition state
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Load skills on mount
    useEffect(() => {
        async function loadSkills() {
            try {
                setIsLoadingSkills(true);
                const loadedSkills = await listSkills();
                setSkills(loadedSkills);
            } catch (error) {
                console.error('Failed to load skills:', error);
            } finally {
                setIsLoadingSkills(false);
            }
        }

        loadSkills();
    }, []);

    // Handle skill selection
    const handleSkillSelect = useCallback((skillName: string) => {
        const currentText = inputValue;
        const lastSlashIndex = currentText.lastIndexOf('/');

        let newMessage: string;
        if (lastSlashIndex !== -1) {
            // Replace the text after last /
            newMessage = currentText.substring(0, lastSlashIndex + 1) + skillName + ' ';
        } else {
            newMessage = `/${skillName} `;
        }

        setInputValue(newMessage);
        setShowSkillMenu(false);
        textareaRef.current?.focus();
    }, [inputValue]);

    // Check for / trigger
    const checkForSkillTrigger = useCallback(() => {
        const cursorPosition = textareaRef.current?.selectionStart || 0;
        const textBeforeCursor = inputValue.substring(0, cursorPosition);

        // Check if the last non-space character is /
        const trimmed = textBeforeCursor.trimEnd();
        if (trimmed.endsWith('/')) {
            // Show menu when / is typed
            const textarea = textareaRef.current;
            if (textarea) {
                const rect = textarea.getBoundingClientRect();
                setMenuPosition({
                    x: rect.left,
                    y: rect.top - 300, // Show above input
                });
                setShowSkillMenu(true);
            }
            return;
        }

        // Check if typing a skill name after /
        const lastSlashIndex = textBeforeCursor.lastIndexOf('/');
        if (lastSlashIndex !== -1) {
            const afterSlash = textBeforeCursor.substring(lastSlashIndex + 1);
            // Show menu if typing skill name (letters, numbers, underscore, hyphen)
            if (/^[a-zA-Z0-9_-]+$/.test(afterSlash)) {
                const textarea = textareaRef.current;
                if (textarea) {
                    const rect = textarea.getBoundingClientRect();
                    setMenuPosition({
                        x: rect.left,
                        y: rect.top - 300,
                    });
                    setShowSkillMenu(true);
                }
                return;
            }
        }

        // Hide menu if no / or invalid pattern
        setShowSkillMenu(false);
    }, [inputValue]);

    // 发送消息
    const handleSend = useCallback(() => {
        if (inputValue.trim()) {
            onSendMessage(inputValue);
            setInputValue('');
        }
    }, [inputValue, onSendMessage]);

    // 键盘事件
    const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        // Close menu on Escape
        if (e.key === 'Escape' && showSkillMenu) {
            setShowSkillMenu(false);
            return;
        }

        // Handle Enter key
        if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
            // If skill menu is open, prevent send - user should select skill first
            if (showSkillMenu) {
                e.preventDefault();
                // Don't close menu automatically - let user navigate with arrows or click
                return;
            }

            // Normal send behavior when menu is closed
            e.preventDefault();
            handleSend();
        }
    }, [handleSend, showSkillMenu, isComposing]);

    // 连接状态配置
    const getStatusConfig = () => {
        if (isConnecting) {
            return { variant: 'warning' as const, label: '初始化...', dotClass: 'bg-yellow-500 animate-pulse' };
        }
        switch (connectionStatus) {
            case 'connected':
                return { variant: 'success' as const, label: '已连接', dotClass: 'bg-green-500' };
            case 'connecting':
                return { variant: 'warning' as const, label: '连接中...', dotClass: 'bg-yellow-500 animate-pulse' };
            case 'disconnected':
                return { variant: 'destructive' as const, label: '已断开', dotClass: 'bg-red-500' };
        }
    };

    const statusConfig = getStatusConfig();

    return (
        <div className="flex flex-col h-screen bg-white dark:bg-gray-900">
            {/* Header */}
            <header className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3">
                <div className="flex items-center justify-between max-w-3xl mx-auto">
                    <div className="flex items-center gap-3">
                        <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
                            Agent Core
                        </h1>
                        {sessionId && (
                            <span className="text-xs text-gray-400 font-mono">
                                {sessionId.slice(0, 8)}...
                            </span>
                        )}
                    </div>

                    {/* 状态和按钮 */}
                    <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${statusConfig.dotClass}`} />
                            <Badge variant={statusConfig.variant}>{statusConfig.label}</Badge>
                        </div>

                        {/* 中止按钮 */}
                        {isLoading && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={onAbort}
                                className="text-red-500 hover:text-red-700"
                                title="中止"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </Button>
                        )}

                        {/* 开发者模式按钮 */}
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setIsDevModeOpen(true)}
                            className="text-gray-600 hover:text-gray-900 dark:text-gray-300"
                            title="开发者模式"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                            </svg>
                        </Button>

                        {/* 新建会话 */}
                        {onNewSession && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={onNewSession}
                                className="text-gray-600 hover:text-gray-900 dark:text-gray-300"
                                title="新建会话"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                </svg>
                            </Button>
                        )}

                        {/* 设置 */}
                        {onOpenSettings && (
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={onOpenSettings}
                                className="text-gray-600 hover:text-gray-900 dark:text-gray-300"
                                title="设置"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                            </Button>
                        )}
                    </div>
                </div>
            </header>

            {/* 断开连接遮罩 */}
            {connectionStatus === 'disconnected' && sessionId && !isConnecting && (
                <div className="absolute inset-0 top-14 bg-white/80 dark:bg-gray-900/80 flex items-center justify-center z-10">
                    <div className="flex flex-col items-center gap-4 text-center">
                        <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                            <svg className="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072" />
                            </svg>
                        </div>
                        <div>
                            <p className="font-medium text-gray-900 dark:text-white">连接已断开</p>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">正在尝试重新连接...</p>
                        </div>
                    </div>
                </div>
            )}

            {/* 消息列表 */}
            <div className="flex-1 min-h-0 overflow-y-auto">
                <div className="h-full max-w-3xl mx-auto flex flex-col">
                    <AgentMessageList
                        messages={messages}
                        streamingContent={streamingContent}
                        streamingThinking={streamingThinking}
                        streamingModel=""
                        isLoading={isLoading}
                    />
                </div>
            </div>

            {/* 输入区域 */}
            <div className="flex-shrink-0 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
                <div className="max-w-3xl mx-auto">
                    <div className="flex gap-2">
                        <div className="flex-1 relative">
                            <textarea
                                ref={textareaRef}
                                value={inputValue}
                                onChange={(e) => {
                                    setInputValue(e.target.value);
                                    checkForSkillTrigger();
                                }}
                                onKeyDown={handleKeyDown}
                                onCompositionStart={() => setIsComposing(true)}
                                onCompositionEnd={() => setIsComposing(false)}
                                placeholder={
                                    isConnecting
                                        ? '正在初始化...'
                                        : connectionStatus !== 'connected'
                                            ? '等待连接...'
                                            : isLoading
                                                ? 'Agent 正在处理...'
                                                : isLoadingSkills
                                                    ? '加载技能...'
                                                    : '输入消息... (输入 / 显示技能菜单, Enter 发送, Shift+Enter 换行)'
                                }
                                disabled={isConnecting || connectionStatus !== 'connected' || isLoading}
                                className="w-full resize-none rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-2 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-violet-500 disabled:opacity-50"
                                rows={2}
                            />

                            {/* Skill menu */}
                            {showSkillMenu && skills.length > 0 && (
                                <SkillMenu
                                    skills={skills}
                                    onSelect={handleSkillSelect}
                                    onClose={() => setShowSkillMenu(false)}
                                    anchorPosition={menuPosition}
                                    searchQuery={(() => {
                                        // Extract text after last /
                                        const lastSlashIndex = inputValue.lastIndexOf('/');
                                        if (lastSlashIndex !== -1) {
                                            return inputValue.substring(lastSlashIndex + 1).trim();
                                        }
                                        return '';
                                    })()}
                                />
                            )}
                        </div>
                        {isLoading ? (
                            <Button
                                onClick={onAbort}
                                variant="destructive"
                                className="px-6"
                                title="中止"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </Button>
                        ) : (
                            <Button
                                onClick={handleSend}
                                disabled={isConnecting || connectionStatus !== 'connected' || !inputValue.trim()}
                                className="px-6"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                                </svg>
                            </Button>
                        )}
                    </div>
                </div>
            </div>

            {/* 开发者模式窗口 */}
            <DevModeWindow isOpen={isDevModeOpen} onClose={() => setIsDevModeOpen(false)} />
        </div>
    );
}
