/** Problem Guidance Card Component
 * 
 * Displays interactive problem guidance with:
 * 1. Visual problem presentation
 * 2. Step-by-step actionable suggestions
 * 3. Request for user input to resolve issues
 */

import { useState } from 'react';

export interface ProblemGuidanceData {
  title: string;
  description: string;
  error_type?: string;
  severity?: 'low' | 'medium' | 'high' | 'critical';
  suggestions?: Array<{
    step: number;
    action: string;
    command?: string;
    completed?: boolean;
  }>;
  requests?: Array<{
    id: string;
    question: string;
    placeholder?: string;
    required?: boolean;
  }>;
  metadata?: Record<string, any>;
}

interface ProblemGuidanceCardProps {
  data: ProblemGuidanceData;
  onCopyCommand?: (command: string) => void;
  onProvideInfo?: (requestId: string, value: string) => void;
}

export function ProblemGuidanceCard({ 
  data, 
  onCopyCommand,
  onProvideInfo 
}: ProblemGuidanceCardProps) {
  const [copiedStep, setCopiedStep] = useState<number | null>(null);
  const [userInputs, setUserInputs] = useState<Record<string, string>>({});

  // Severity color mapping
  const severityColors = {
    low: 'from-blue-500 to-cyan-600',
    medium: 'from-yellow-500 to-orange-600',
    high: 'from-orange-500 to-red-600',
    critical: 'from-red-500 to-purple-600',
  };

  const severityIcons = {
    low: '💡',
    medium: '⚠️',
    high: '🚨',
    critical: '❌',
  };

  const severity = data.severity || 'medium';
  const gradientClass = severityColors[severity];
  const icon = severityIcons[severity];

  // Copy command to clipboard
  const handleCopyCommand = async (command: string, stepIndex: number) => {
    try {
      await navigator.clipboard.writeText(command);
      setCopiedStep(stepIndex);
      onCopyCommand?.(command);
      setTimeout(() => setCopiedStep(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  // Handle user input submission
  const handleInputChange = (requestId: string, value: string) => {
    setUserInputs(prev => ({ ...prev, [requestId]: value }));
  };

  const handleSubmitInput = (requestId: string) => {
    const value = userInputs[requestId];
    if (value) {
      onProvideInfo?.(requestId, value);
      setUserInputs(prev => {
        const newState = { ...prev };
        delete newState[requestId];
        return newState;
      });
    }
  };

  return (
    <div className="w-full bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      {/* Header with severity indicator */}
      <div className={`bg-gradient-to-r ${gradientClass} px-4 py-3 text-white`}>
        <div className="flex items-center gap-2">
          <span className="text-xl">{icon}</span>
          <h3 className="font-semibold text-lg">{data.title}</h3>
        </div>
        {data.description && (
          <p className="mt-1 text-sm opacity-90">{data.description}</p>
        )}
        {data.error_type && (
          <p className="mt-1 text-xs opacity-75 font-mono">Error: {data.error_type}</p>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Suggestions Section */}
        {data.suggestions && data.suggestions.length > 0 && (
          <div className="space-y-2">
            <h4 className="font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <span>📋</span>
              建议操作步骤
            </h4>
            
            <div className="space-y-2">
              {data.suggestions.map((suggestion, index) => (
                <div
                  key={index}
                  className={`p-3 rounded-lg border-l-4 ${
                    suggestion.completed
                      ? 'bg-green-50 dark:bg-green-900/20 border-green-500'
                      : 'bg-gray-50 dark:bg-gray-700/50 border-gray-300 dark:border-gray-600'
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <span className="flex-shrink-0 w-5 h-5 rounded-full bg-gray-200 dark:bg-gray-600 text-xs flex items-center justify-center font-medium">
                      {suggestion.completed ? '✓' : suggestion.step}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm text-gray-900 dark:text-gray-100">
                        {suggestion.action}
                      </p>
                      
                      {/* Command display */}
                      {suggestion.command && (
                        <div className="mt-2">
                          <div className="flex items-center gap-2">
                            <code className="flex-1 bg-black/10 dark:bg-white/10 px-2 py-1 rounded text-xs font-mono text-gray-800 dark:text-gray-200">
                              {suggestion.command}
                            </code>
                            <button
                              onClick={() => handleCopyCommand(suggestion.command!, index)}
                              className="px-2 py-1 text-xs bg-blue-500 hover:bg-blue-600 text-white rounded transition-colors"
                              title="复制命令"
                            >
                              {copiedStep === index ? '✓' : '📋'}
                            </button>
                          </div>
                          {copiedStep === index && (
                            <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                              已复制到剪贴板!
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* User Input Requests Section */}
        {data.requests && data.requests.length > 0 && (
          <div className="space-y-3">
            <h4 className="font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <span>🤔</span>
              需要您的帮助
            </h4>
            
            <div className="space-y-3">
              {data.requests.map((request) => (
                <div
                  key={request.id}
                  className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800"
                >
                  <p className="text-sm text-gray-900 dark:text-gray-100 mb-2">
                    {request.question}
                    {request.required && (
                      <span className="text-red-500 ml-1">*</span>
                    )}
                  </p>
                  
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder={request.placeholder || '请输入...'}
                      value={userInputs[request.id] || ''}
                      onChange={(e) => handleInputChange(request.id, e.target.value)}
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') {
                          handleSubmitInput(request.id);
                        }
                      }}
                      className="flex-1 px-3 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 dark:text-gray-100"
                    />
                    <button
                      onClick={() => handleSubmitInput(request.id)}
                      disabled={!userInputs[request.id]}
                      className="px-4 py-2 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white rounded text-sm font-medium transition-colors disabled:cursor-not-allowed"
                    >
                      提交
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Metadata Section (if available) */}
        {data.metadata && Object.keys(data.metadata).length > 0 && (
          <details className="mt-4">
            <summary className="cursor-pointer text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
              🔍 查看详细诊断信息
            </summary>
            <pre className="mt-2 p-3 bg-black/10 dark:bg-white/5 rounded text-xs font-mono whitespace-pre-wrap break-all text-gray-800 dark:text-gray-200">
              {JSON.stringify(data.metadata, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

// Component and type are already exported above
