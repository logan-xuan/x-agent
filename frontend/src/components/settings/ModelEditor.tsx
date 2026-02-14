/** Model configuration editor component */

import { useState } from 'react';
import { Button } from '../ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';

interface EditableModel {
  name: string;
  provider: string;
  base_url: string;
  api_key_masked: string;
  model_id: string;
  is_primary: boolean;
  timeout: number;
  max_retries: number;
  priority: number;
}

interface ModelEditorProps {
  model: EditableModel;
  onUpdate: (name: string, updates: Partial<EditableModel>) => Promise<void>;
  isUpdating: boolean;
}

export function ModelEditor({ model, onUpdate, isUpdating }: ModelEditorProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({
    model_id: model.model_id,
    api_key: '',
    timeout: model.timeout,
    max_retries: model.max_retries,
    priority: model.priority,
  });
  const [showApiKey, setShowApiKey] = useState(false);
  
  const handleSave = async () => {
    const updates: Record<string, unknown> = {};
    
    if (formData.model_id !== model.model_id) {
      updates.model_id = formData.model_id;
    }
    if (formData.api_key && formData.api_key !== '***') {
      updates.api_key = formData.api_key;
    }
    if (formData.timeout !== model.timeout) {
      updates.timeout = formData.timeout;
    }
    if (formData.max_retries !== model.max_retries) {
      updates.max_retries = formData.max_retries;
    }
    if (formData.priority !== model.priority) {
      updates.priority = formData.priority;
    }
    
    if (Object.keys(updates).length > 0) {
      await onUpdate(model.name, updates);
    }
    
    setIsEditing(false);
    setFormData(prev => ({ ...prev, api_key: '' }));
  };
  
  const handleCancel = () => {
    setFormData({
      model_id: model.model_id,
      api_key: '',
      timeout: model.timeout,
      max_retries: model.max_retries,
      priority: model.priority,
    });
    setIsEditing(false);
  };
  
  return (
    <Card className="mb-3">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            {model.name}
            {model.is_primary && (
              <span className="text-xs bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 px-2 py-0.5 rounded">
                主模型
              </span>
            )}
          </CardTitle>
          {!isEditing && (
            <Button variant="outline" size="sm" onClick={() => setIsEditing(true)}>
              编辑
            </Button>
          )}
        </div>
      </CardHeader>
      
      <CardContent>
        {isEditing ? (
          <div className="space-y-4">
            {/* Provider (read-only) */}
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-300 mb-1">提供商</label>
              <input
                type="text"
                value={model.provider}
                disabled
                className="w-full px-3 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg text-gray-600 dark:text-gray-400"
              />
            </div>
            
            {/* Model ID */}
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-300 mb-1">模型 ID</label>
              <input
                type="text"
                value={formData.model_id}
                onChange={(e) => setFormData(prev => ({ ...prev, model_id: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
            
            {/* API Key */}
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-300 mb-1">
                API Key (当前: {model.api_key_masked})
              </label>
              <div className="relative">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={formData.api_key}
                  onChange={(e) => setFormData(prev => ({ ...prev, api_key: e.target.value }))}
                  placeholder="输入新的 API Key 以更新"
                  className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400"
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                >
                  {showApiKey ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">留空则保持当前密钥不变</p>
            </div>
            
            {/* Timeout */}
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-300 mb-1">超时时间 (秒)</label>
              <input
                type="number"
                min={5}
                max={300}
                value={formData.timeout}
                onChange={(e) => setFormData(prev => ({ ...prev, timeout: parseFloat(e.target.value) }))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
            
            {/* Max Retries */}
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-300 mb-1">最大重试次数</label>
              <input
                type="number"
                min={0}
                max={5}
                value={formData.max_retries}
                onChange={(e) => setFormData(prev => ({ ...prev, max_retries: parseInt(e.target.value) }))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
            
            {/* Priority (for backups) */}
            {!model.is_primary && (
              <div>
                <label className="block text-sm text-gray-600 dark:text-gray-300 mb-1">优先级</label>
                <input
                  type="number"
                  min={0}
                  value={formData.priority}
                  onChange={(e) => setFormData(prev => ({ ...prev, priority: parseInt(e.target.value) }))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">数字越小优先级越高</p>
              </div>
            )}
            
            {/* Actions */}
            <div className="flex gap-2 pt-2">
              <Button onClick={handleSave} disabled={isUpdating}>
                {isUpdating ? '保存中...' : '保存'}
              </Button>
              <Button variant="outline" onClick={handleCancel} disabled={isUpdating}>
                取消
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-600 dark:text-gray-400">模型 ID</span>
              <span className="font-mono text-gray-900 dark:text-white">{model.model_id}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600 dark:text-gray-400">API Key</span>
              <span className="font-mono text-gray-900 dark:text-white">{model.api_key_masked}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600 dark:text-gray-400">超时</span>
              <span className="text-gray-900 dark:text-white">{model.timeout}s</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600 dark:text-gray-400">重试次数</span>
              <span className="text-gray-900 dark:text-white">{model.max_retries}</span>
            </div>
            {!model.is_primary && (
              <div className="flex justify-between text-sm">
                <span className="text-gray-600 dark:text-gray-400">优先级</span>
                <span className="text-gray-900 dark:text-white">{model.priority}</span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
