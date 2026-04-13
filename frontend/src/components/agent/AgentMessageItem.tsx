/**
 * Agent 消息项组件
 * 
 * 显示单条 Agent 消息，包括用户消息和助手消息。
 */

import { useState } from 'react';

import { AgentMessage } from '../../hooks/useAgent';
import { AgentToolCallCard } from './AgentToolCallCard';
import { ImageLightbox } from './ImageLightbox';

interface AgentMessageItemProps {
    message: AgentMessage;
    isStreaming?: boolean;
}

type MessageSegment =
    | { type: 'text'; content: string }
    | { type: 'image'; alt: string; url: string };

function parseAssistantMessage(content: string): MessageSegment[] {
    const imagePattern = /!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g;
    const segments: MessageSegment[] = [];
    let cursor = 0;

    for (const match of content.matchAll(imagePattern)) {
        const matchedText = match[0];
        const alt = match[1] ?? '';
        const url = match[2] ?? '';
        const start = match.index ?? 0;

        if (start > cursor) {
            segments.push({
                type: 'text',
                content: content.slice(cursor, start),
            });
        }

        segments.push({
            type: 'image',
            alt,
            url,
        });
        cursor = start + matchedText.length;
    }

    if (cursor < content.length) {
        segments.push({
            type: 'text',
            content: content.slice(cursor),
        });
    }

    return segments.length > 0 ? segments : [{ type: 'text', content }];
}

// AI 图标
function AIIcon() {
    return (
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/25">
            <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="3" fill="currentColor" />
                <circle cx="12" cy="5" r="1.5" />
                <circle cx="12" cy="19" r="1.5" />
                <circle cx="5" cy="12" r="1.5" />
                <circle cx="19" cy="12" r="1.5" />
                <circle cx="7" cy="7" r="1.5" />
                <circle cx="17" cy="7" r="1.5" />
                <circle cx="7" cy="17" r="1.5" />
                <circle cx="17" cy="17" r="1.5" />
                <path d="M12 5v4M12 15v4M5 12h4M15 12h4M7 7l3 3M14 14l3 3M7 17l3-3M14 10l3-3" opacity="0.6" />
            </svg>
        </div>
    );
}

// 用户图标
function UserIcon() {
    return (
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/25">
            <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="8" r="4" fill="currentColor" />
                <path d="M4 20c0-4 3.5-7 8-7s8 3 8 7" stroke="currentColor" strokeLinecap="round" />
                <path d="M12 16v3M9 18l3 2 3-2" opacity="0.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
        </div>
    );
}

export function AgentMessageItem({ message, isStreaming = false }: AgentMessageItemProps) {
    const [selectedImage, setSelectedImage] = useState<{ alt: string; url: string } | null>(null);
    const isUser = message.role === 'user';
    const hasToolCalls = message.toolCalls && message.toolCalls.length > 0;
    const parsedSegments = !isUser ? parseAssistantMessage(message.content) : null;
    const audioUrl = message.audio?.publicUrl;

    return (
        <div
            className={`flex w-full mb-4 gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
        >
            {/* 头像 */}
            <div className="flex-shrink-0 mt-1">
                {isUser ? <UserIcon /> : <AIIcon />}
            </div>

            {/* 消息气泡 */}
            <div
                className={`max-w-[75%] rounded-2xl px-4 py-3 ${isUser
                    ? 'bg-gradient-to-br from-cyan-500 to-blue-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700'
                    }`}
            >
                {/* 角色标识 */}
                <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-medium ${isUser ? 'text-cyan-100' : 'text-gray-500 dark:text-gray-400'}`}>
                        {isUser ? 'YOU' : 'AGENT'}
                    </span>
                    {message.model && (
                        <span className={`text-xs ${isUser ? 'text-cyan-200/70' : 'text-gray-400 dark:text-gray-500'}`}>
                            · {message.model}
                        </span>
                    )}
                </div>

                {/* 思考内容 (如果有) */}
                {message.thinking && (
                    <details className="mb-2">
                        <summary className="cursor-pointer text-xs text-purple-600 dark:text-purple-400">
                            💭 思考过程
                        </summary>
                        <div className="mt-1 p-2 bg-purple-50 dark:bg-purple-900/20 rounded text-xs text-purple-700 dark:text-purple-300 whitespace-pre-wrap">
                            {message.thinking}
                        </div>
                    </details>
                )}

                {message.transcript && (
                    <div className={`mb-3 rounded-xl px-3 py-2 text-xs ${isUser ? 'bg-cyan-400/20 text-cyan-50' : 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200'}`}>
                        <div className="font-medium">语音转写</div>
                        <div className="mt-1 whitespace-pre-wrap break-words">{message.transcript.text}</div>
                        {(message.transcript.provider || message.transcript.language) && (
                            <div className={`mt-1 ${isUser ? 'text-cyan-100/80' : 'text-gray-500 dark:text-gray-400'}`}>
                                {[message.transcript.provider, message.transcript.language].filter(Boolean).join(' · ')}
                            </div>
                        )}
                    </div>
                )}

                {message.voiceError && (
                    <div className={`mb-3 rounded-xl border px-3 py-2 text-xs ${
                        isUser
                            ? 'border-amber-300/40 bg-amber-400/20 text-amber-50'
                            : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200'
                    }`}>
                        <div className="font-medium">
                            {message.voiceError.stage === 'asr' ? '语音转写失败' : '语音回复失败'}
                        </div>
                        <div className="mt-1 whitespace-pre-wrap break-words">{message.voiceError.message}</div>
                    </div>
                )}

                {message.voiceState && (
                    <div className={`mb-3 inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${
                        isUser
                            ? 'bg-cyan-400/20 text-cyan-50'
                            : 'bg-sky-100 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300'
                    }`}>
                        <span>{message.voiceState.label}</span>
                        {message.voiceState.durationMs && (
                            <span className={isUser ? 'text-cyan-100/80' : 'text-sky-600 dark:text-sky-400'}>
                                {formatVoiceDuration(message.voiceState.durationMs)}
                            </span>
                        )}
                    </div>
                )}

                {/* 消息内容 */}
                <div className="whitespace-pre-wrap break-words leading-relaxed">
                    {parsedSegments ? (
                        parsedSegments.map((segment, index) => {
                            if (segment.type === 'text') {
                                return (
                                    <span key={`text-${index}`} className="whitespace-pre-wrap">
                                        {segment.content}
                                    </span>
                                );
                            }

                            return (
                                <img
                                    key={`image-${index}`}
                                    src={segment.url}
                                    alt={segment.alt || '生成图片'}
                                    className="mt-3 max-h-[28rem] w-full cursor-zoom-in rounded-xl border border-gray-200 object-contain shadow-sm dark:border-gray-700"
                                    onClick={() => setSelectedImage({ alt: segment.alt || '生成图片', url: segment.url })}
                                />
                            );
                        })
                    ) : (
                        message.content
                    )}
                    {isStreaming && (
                        <span className="inline-block w-2 h-4 ml-1 bg-current animate-pulse rounded-sm" />
                    )}
                </div>

                {audioUrl && (
                    <div className="mt-3">
                        <audio
                            controls
                            preload="none"
                            className="w-full max-w-sm"
                            src={audioUrl}
                        >
                            当前浏览器不支持音频播放。
                        </audio>
                        <div className={`mt-1 text-xs ${isUser ? 'text-cyan-100/70' : 'text-gray-500 dark:text-gray-400'}`}>
                            {[
                                message.audio?.provider,
                                message.audio?.voice,
                                message.audio?.format,
                            ].filter(Boolean).join(' · ')}
                        </div>
                    </div>
                )}

                {/* 工具调用 */}
                {hasToolCalls && (
                    <div className="mt-3 space-y-2">
                        {message.toolCalls?.map((toolCall) => (
                            <AgentToolCallCard key={toolCall.id} toolCall={toolCall} />
                        ))}
                    </div>
                )}

                {/* 时间戳 */}
                <div className={`text-xs mt-2 ${isUser ? 'text-cyan-100/60' : 'text-gray-400 dark:text-gray-500'}`}>
                    {new Date(message.createdAt).toLocaleTimeString('zh-CN', {
                        hour: '2-digit',
                        minute: '2-digit',
                    })}
                </div>
            </div>

            {selectedImage && (
                <ImageLightbox
                    imageUrl={selectedImage.url}
                    alt={selectedImage.alt}
                    onClose={() => setSelectedImage(null)}
                />
            )}
        </div>
    );
}

function formatVoiceDuration(durationMs: number): string {
    if (durationMs < 1000) {
        return '1.0 秒';
    }
    return `${(durationMs / 1000).toFixed(1)} 秒`;
}
