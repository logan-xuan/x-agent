/** Interactive Problem Guidance Component.
 * 
 * Displays structured problem diagnosis with:
 * 1. Visual problem representation
 * 2. Step-by-step interactive guidance
 * 3. Auto-fix suggestions
 * 4. User information requests
 */

import { useState } from 'react';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';

export interface GuidanceStep {
  step: number;
  title: string;
  description: string;
  command?: string;
  user_action_required?: boolean;
}

export interface ProblemGuidanceData {
  type: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  title: string;
  description: string;
  context?: Record<string, any>;
  steps: GuidanceStep[];
  auto_fixes: string[];
  user_info_needed: string[];
}

interface ProblemGuidanceCardProps {
  data: ProblemGuidanceData;
  onCopyCommand?: (command: string) => void;
  onProvideInfo?: (request: string, value: string) => void;
}

export function ProblemGuidanceCard({ 
  data, 
  onCopyCommand,
  onProvideInfo,
}: ProblemGuidanceCardProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set([1]));
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());

  const severityConfig = {
    critical: { color: 'red', icon: '🚨', label: '严重' },
    high: { color: 'orange', icon: '⚠️', label: '高' },
    medium: { color: 'yellow', icon: '⚡', label: '中' },
    low: { color: 'blue', icon: 'ℹ️', label: '低' },
  };

  const config = severityConfig[data.severity];

  const toggleStep = (stepNum: number) => {
    const newExpanded = new Set(expandedSteps);
    if (newExpanded.has(stepNum)) {
      newExpanded.delete(stepNum);
    } else {
      newExpanded.add(stepNum);
    }
    setExpandedSteps(newExpanded);
  };

  const markStepComplete = (stepNum: number) => {
    const newCompleted = new Set(completedSteps);
    newCompleted.add(stepNum);
    setCompletedSteps(newCompleted);
    // Auto-expand next step
    if (stepNum < data.steps.length) {
      setExpandedSteps(prev => new Set([...prev, stepNum + 1]));
    }
  };

  const handleCopyCommand = (command: string) => {
    navigator.clipboard.writeText(command);
    onCopyCommand?.(command);
  };

  return (
    <div className="my-4 space-y-4">
      {/* Problem Header */}
      <Card className="border-l-4 border-l-red-500 bg-gradient-to-r from-red-50 to-orange-50 dark:from-red-900/20 dark:to-orange-900/20">
        <div className="p-4">
          <div className="flex items-start gap-3">
            <span className="text-3xl">{config.icon}</span>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                  {data.title}
                </h3>
                <Badge variant="destructive">
                  {config.label}
                </Badge>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                {data.description}
              </p>
            </div>
          </div>
        </div>
      </Card>

      {/* Context Information */}
      {data.context && Object.keys(data.context).length > 0 && (
        <Card className="bg-gray-50 dark:bg-gray-800/50">
          <div className="p-3">
            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              🔍 上下文信息
            </h4>
            <div className="space-y-1">
              {Object.entries(data.context).map(([key, value]) => (
                <div key={key} className="text-xs font-mono">
                  <span className="text-gray-500 dark:text-gray-400">{key}:</span>
                  <span className="ml-2 text-gray-900 dark:text-white bg-white dark:bg-gray-700 px-2 py-1 rounded">
                    {String(value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* Interactive Steps */}
      {data.steps.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
            <span>🎯</span> 交互式引导步骤
          </h4>
          
          {data.steps.map((step) => (
            <Card 
              key={step.step}
              className={`transition-all ${
                completedSteps.has(step.step)
                  ? 'bg-green-50 dark:bg-green-900/20 border-green-300'
                  : expandedSteps.has(step.step)
                  ? 'bg-white dark:bg-gray-800 border-blue-300'
                  : 'bg-gray-50 dark:bg-gray-800/50 opacity-70'
              }`}
            >
              <div className="p-3">
                <button
                  onClick={() => toggleStep(step.step)}
                  className="w-full flex items-center justify-between text-left"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center text-sm font-bold ${
                      completedSteps.has(step.step)
                        ? 'bg-green-500 text-white'
                        : expandedSteps.has(step.step)
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-300 dark:bg-gray-600 text-gray-600 dark:text-gray-300'
                    }`}>
                      {completedSteps.has(step.step) ? '✓' : step.step}
                    </div>
                    <div>
                      <h5 className="text-sm font-semibold text-gray-900 dark:text-white">
                        {step.title}
                      </h5>
                      {step.user_action_required && (
                        <Badge variant="warning" className="text-xs mt-1">
                          需要操作
                        </Badge>
                      )}
                    </div>
                  </div>
                  <svg 
                    className={`w-5 h-5 text-gray-500 transition-transform ${
                      expandedSteps.has(step.step) ? 'rotate-180' : ''
                    }`}
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {expandedSteps.has(step.step) && (
                  <div className="mt-3 pl-9 space-y-3">
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                      {step.description}
                    </p>
                    
                    {step.command && (
                      <div className="bg-black/90 dark:bg-gray-900 rounded-lg p-3 font-mono text-xs text-green-400 overflow-x-auto">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-gray-500">$ Command</span>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleCopyCommand(step.command!)}
                            className="text-xs text-gray-400 hover:text-white"
                          >
                            📋 复制
                          </Button>
                        </div>
                        <code>{step.command}</code>
                      </div>
                    )}

                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={() => markStepComplete(step.step)}
                        className="bg-green-600 hover:bg-green-700 text-white"
                      >
                        ✓ 已完成
                      </Button>
                      {step.command && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => step.command && navigator.clipboard.writeText(step.command)}
                          className="text-gray-700 dark:text-gray-300"
                        >
                          ▶️ 执行命令
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Auto-Fix Suggestions */}
      {data.auto_fixes.length > 0 && (
        <Card className="bg-blue-50 dark:bg-blue-900/20 border-blue-200">
          <div className="p-3">
            <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-100 flex items-center gap-2 mb-2">
              <span>🔧</span> 自动修正建议
            </h4>
            <ul className="space-y-2">
              {data.auto_fixes.map((fix, index) => (
                <li key={index} className="text-sm text-blue-800 dark:text-blue-200 flex items-start gap-2">
                  <span className="text-blue-500 mt-1">•</span>
                  <span>{fix}</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}

      {/* User Info Requests */}
      {data.user_info_needed.length > 0 && (
        <Card className="bg-purple-50 dark:bg-purple-900/20 border-purple-200">
          <div className="p-3">
            <h4 className="text-sm font-semibold text-purple-900 dark:text-purple-100 flex items-center gap-2 mb-2">
              <span>💬</span> 需要你补充的信息
            </h4>
            <div className="space-y-2">
              {data.user_info_needed.map((request, index) => (
                <div key={index} className="flex items-start gap-2">
                  <span className="text-purple-500 mt-1">❓</span>
                  <div className="flex-1">
                    <p className="text-sm text-purple-800 dark:text-purple-200">
                      {request}
                    </p>
                    {onProvideInfo && (
                      <input
                        type="text"
                        placeholder="输入信息..."
                        className="mt-1 w-full px-3 py-2 text-sm border border-purple-300 dark:border-purple-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                        onBlur={(e) => {
                          if (e.target.value) {
                            onProvideInfo(request, e.target.value);
                            e.target.value = '';
                          }
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && e.currentTarget.value) {
                            onProvideInfo(request, e.currentTarget.value);
                            e.currentTarget.value = '';
                          }
                        }}
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
