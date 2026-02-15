/** Prompt Tester Component - Test prompts directly with LLM */

import { useState, useCallback } from 'react';
import { Button } from '../ui/Button';
import { Spinner } from '../ui/Spinner';
import { testPrompt, testPromptStream } from '@/services/api';
import type { PromptTestRequest, PromptTestStreamChunk } from '@/types';

interface PromptTesterProps {
  onError?: (error: string) => void;
}

export function PromptTester({ onError }: PromptTesterProps) {
  const [systemPrompt, setSystemPrompt] = useState('');
  const [userPrompt, setUserPrompt] = useState('');
  const [response, setResponse] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [useStream, setUseStream] = useState(true);
  const [metadata, setMetadata] = useState<{
    model: string;
    provider: string;
    latencyMs: number;
    tokenUsage: { prompt: number; completion: number; total: number } | null;
  } | null>(null);

  // Reserved for future abort functionality
  // const abortControllerRef = useRef<AbortController | null>(null);

  const handleTest = useCallback(async () => {
    if (!userPrompt.trim()) {
      onError?.('请输入用户提示词');
      return;
    }

    setIsLoading(true);
    setResponse('');
    setMetadata(null);

    const request: PromptTestRequest = {
      messages: [{ role: 'user', content: userPrompt }],
      stream: useStream,
      system_prompt: systemPrompt || undefined,
    };

    try {
      if (useStream) {
        setIsStreaming(true);
        let fullContent = '';

        await testPromptStream(
          request,
          (chunk: PromptTestStreamChunk) => {
            if (chunk.type === 'chunk' && chunk.content) {
              fullContent += chunk.content;
              setResponse(fullContent);
            } else if (chunk.type === 'done') {
              setIsStreaming(false);
              setMetadata({
                model: chunk.model || 'unknown',
                provider: chunk.provider || 'unknown',
                latencyMs: chunk.latency_ms || 0,
                tokenUsage: null, // Stream doesn't provide token usage
              });
            } else if (chunk.type === 'error') {
              setIsStreaming(false);
              onError?.(chunk.error || 'Stream error');
            }
          },
          (error) => {
            setIsStreaming(false);
            onError?.(error.message);
          }
        );
      } else {
        const result = await testPrompt(request);
        setResponse(result.content);
        setMetadata({
          model: result.model,
          provider: result.provider,
          latencyMs: result.latency_ms,
          tokenUsage: result.token_usage
            ? {
                prompt: result.token_usage.prompt_tokens,
                completion: result.token_usage.completion_tokens,
                total: result.token_usage.total_tokens,
              }
            : null,
        });
      }
    } catch (err) {
      onError?.(err instanceof Error ? err.message : 'Test failed');
    } finally {
      setIsLoading(false);
      setIsStreaming(false);
    }
  }, [userPrompt, systemPrompt, useStream, onError]);

  const handleClear = () => {
    setSystemPrompt('');
    setUserPrompt('');
    setResponse('');
    setMetadata(null);
  };

  const copyResponse = () => {
    if (response) {
      navigator.clipboard.writeText(response);
    }
  };

  return (
    <div className="flex flex-col h-full p-4 space-y-4">
      {/* System Prompt Input */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          系统提示词 (可选)
        </label>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          placeholder="输入系统提示词，例如：你是一个有用的助手..."
          className="w-full h-20 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md 
                     bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100
                     focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
      </div>

      {/* User Prompt Input */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          用户提示词 <span className="text-red-500">*</span>
        </label>
        <textarea
          value={userPrompt}
          onChange={(e) => setUserPrompt(e.target.value)}
          placeholder="输入要测试的用户提示词..."
          className="w-full h-24 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md 
                     bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100
                     focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={useStream}
              onChange={(e) => setUseStream(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            流式响应
          </label>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={handleClear} disabled={isLoading}>
            清空
          </Button>
          <Button
            onClick={handleTest}
            disabled={isLoading || !userPrompt.trim()}
            className="min-w-[80px]"
          >
            {isLoading ? <Spinner size="sm" /> : '发送'}
          </Button>
        </div>
      </div>

      {/* Response Area */}
      <div className="flex-1 min-h-0 flex flex-col space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
            响应结果
            {isStreaming && (
              <span className="ml-2 text-xs text-blue-500 animate-pulse">接收中...</span>
            )}
          </label>
          {response && (
            <Button variant="ghost" size="sm" onClick={copyResponse}>
              复制
            </Button>
          )}
        </div>

        <div className="flex-1 relative">
          <textarea
            value={response}
            readOnly
            placeholder="响应将显示在这里..."
            className="w-full h-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md 
                       bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100
                       focus:outline-none resize-none font-mono leading-relaxed"
          />
        </div>

        {/* Metadata */}
        {metadata && (
          <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 p-2 rounded">
            <span>
              模型: <span className="font-mono text-gray-700 dark:text-gray-300">{metadata.model}</span>
            </span>
            <span>
              提供商: <span className="font-mono text-gray-700 dark:text-gray-300">{metadata.provider}</span>
            </span>
            <span>
              延迟: <span className="font-mono text-gray-700 dark:text-gray-300">{metadata.latencyMs}ms</span>
            </span>
            {metadata.tokenUsage && (
              <span>
                Tokens:{' '}
                <span className="font-mono text-gray-700 dark:text-gray-300">
                  {metadata.tokenUsage.prompt} → {metadata.tokenUsage.completion} ({metadata.tokenUsage.total})
                </span>
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
