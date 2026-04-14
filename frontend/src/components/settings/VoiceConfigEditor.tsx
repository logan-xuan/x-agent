import { useState } from 'react';

import { Button } from '../ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card';

export interface EditableVoiceOpenAIConfig {
  enabled: boolean;
  base_url: string;
  api_key_masked: string;
  timeout: number;
  tts_model: string;
  asr_model: string;
}

export interface EditableVoiceWhisperCompatibleConfig {
  enabled: boolean;
  endpoint: string;
  auth_token_masked: string;
  timeout: number;
  default_model: string;
  response_format: string;
}

export interface EditableVoiceFunASRBailianConfig {
  enabled: boolean;
  websocket_url: string;
  api_key_masked: string;
  timeout: number;
  model: string;
  sample_rate_hz: number;
  chunk_interval_ms: number;
  chunk_size_bytes: number;
  language_hints: string[];
}

export interface EditableVoiceGPTSoVITSConfig {
  enabled: boolean;
  endpoint: string;
  timeout: number;
  ref_audio_path: string;
  ref_text: string;
  text_lang: string;
  prompt_lang: string;
}

export interface EditableVoiceTTSVoiceConfig {
  default: string | null;
  options: string[];
}

export interface EditableVoiceTTSConfig {
  default_provider: string;
  voices: Record<string, EditableVoiceTTSVoiceConfig>;
}

export interface EditableVoiceRewriteConfig {
  mode: 'rules' | 'model';
}

export interface EditableVoiceConfig {
  enabled: boolean;
  assets_dir: string;
  public_base_url: string;
  playback_base_url: string;
  upload_max_bytes: number;
  rewrite: EditableVoiceRewriteConfig;
  tts: EditableVoiceTTSConfig;
  openai: EditableVoiceOpenAIConfig;
  whisper_compatible: EditableVoiceWhisperCompatibleConfig;
  funasr_bailian: EditableVoiceFunASRBailianConfig;
  gpt_sovits: EditableVoiceGPTSoVITSConfig;
}

interface VoiceConfigEditorProps {
  voice: EditableVoiceConfig;
  onUpdate: (updates: Record<string, unknown>) => Promise<void>;
  isUpdating: boolean;
}

function buildFormData(voice: EditableVoiceConfig) {
  return {
    enabled: voice.enabled,
    assets_dir: voice.assets_dir,
    public_base_url: voice.public_base_url,
    playback_base_url: voice.playback_base_url,
    upload_max_bytes: voice.upload_max_bytes,
    rewrite: {
      mode: voice.rewrite.mode,
    },
    tts: {
      default_provider: voice.tts.default_provider,
      voices: Object.fromEntries(
        Object.entries(voice.tts.voices).map(([provider, entry]) => [
          provider,
          {
            default: entry.default ?? '',
            options: [...entry.options],
          },
        ]),
      ),
    },
    openai: {
      enabled: voice.openai.enabled,
      base_url: voice.openai.base_url,
      api_key: '',
      timeout: voice.openai.timeout,
      tts_model: voice.openai.tts_model,
      asr_model: voice.openai.asr_model,
    },
    whisper_compatible: {
      enabled: voice.whisper_compatible.enabled,
      endpoint: voice.whisper_compatible.endpoint,
      auth_token: '',
      timeout: voice.whisper_compatible.timeout,
      default_model: voice.whisper_compatible.default_model,
      response_format: voice.whisper_compatible.response_format,
    },
    funasr_bailian: {
      enabled: voice.funasr_bailian.enabled,
      websocket_url: voice.funasr_bailian.websocket_url,
      api_key: '',
      timeout: voice.funasr_bailian.timeout,
      model: voice.funasr_bailian.model,
      sample_rate_hz: voice.funasr_bailian.sample_rate_hz,
      chunk_interval_ms: voice.funasr_bailian.chunk_interval_ms,
      chunk_size_bytes: voice.funasr_bailian.chunk_size_bytes,
      language_hints: voice.funasr_bailian.language_hints.join(', '),
    },
    gpt_sovits: {
      enabled: voice.gpt_sovits.enabled,
      endpoint: voice.gpt_sovits.endpoint,
      timeout: voice.gpt_sovits.timeout,
      ref_audio_path: voice.gpt_sovits.ref_audio_path,
      ref_text: voice.gpt_sovits.ref_text,
      text_lang: voice.gpt_sovits.text_lang,
      prompt_lang: voice.gpt_sovits.prompt_lang,
    },
  }
}

export function VoiceConfigEditor({ voice, onUpdate, isUpdating }: VoiceConfigEditorProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [showOpenAIKey, setShowOpenAIKey] = useState(false);
  const [showWhisperToken, setShowWhisperToken] = useState(false);
  const [showFunASRKey, setShowFunASRKey] = useState(false);
  const [formData, setFormData] = useState(() => buildFormData(voice));
  const ttsProviderOptions = Object.keys(formData.tts.voices).map((provider) => ({
    value: provider,
    label: formatTtsProviderLabel(provider),
  }));

  const handleCancel = () => {
    setFormData(buildFormData(voice));
    setIsEditing(false);
  };

  const handleSave = async () => {
    await onUpdate({
      ...formData,
      funasr_bailian: {
        ...formData.funasr_bailian,
        language_hints: formData.funasr_bailian.language_hints
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
      },
    });
    setIsEditing(false);
    setFormData((current) => ({
      ...current,
      openai: { ...current.openai, api_key: '' },
      whisper_compatible: { ...current.whisper_compatible, auth_token: '' },
      funasr_bailian: { ...current.funasr_bailian, api_key: '' },
    }));
  };

  return (
    <Card className="mb-3">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">语音配置</CardTitle>
          {!isEditing && (
            <Button variant="outline" size="sm" onClick={() => setIsEditing(true)}>
              编辑
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent>
        {isEditing ? (
          <div className="space-y-5">
            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">通用设置</h3>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={formData.enabled}
                  onChange={(event) => setFormData((prev) => ({ ...prev, enabled: event.target.checked }))}
                />
                <span>启用语音能力</span>
              </label>
              <div className="grid gap-3 md:grid-cols-2">
                <LabeledInput label="音频资产目录" value={formData.assets_dir} onChange={(value) => setFormData((prev) => ({ ...prev, assets_dir: value }))} />
                <LabeledInput label="Provider 外网地址" value={formData.public_base_url} onChange={(value) => setFormData((prev) => ({ ...prev, public_base_url: value }))} />
                <LabeledInput label="前端播放地址" value={formData.playback_base_url} onChange={(value) => setFormData((prev) => ({ ...prev, playback_base_url: value }))} />
                <LabeledInput label="上传大小上限（字节）" type="number" value={String(formData.upload_max_bytes)} onChange={(value) => setFormData((prev) => ({ ...prev, upload_max_bytes: Number(value) || 0 }))} />
                <LabeledSelect
                  label="文案改写模式"
                  value={formData.rewrite.mode}
                  options={[
                    { value: 'rules', label: '规则改写' },
                    { value: 'model', label: '模型改写' },
                  ]}
                  onChange={(value) =>
                    setFormData((prev) => ({
                      ...prev,
                      rewrite: { mode: value as 'rules' | 'model' },
                    }))
                  }
                />
                <LabeledSelect
                  label="默认 TTS Provider"
                  value={formData.tts.default_provider}
                  options={ttsProviderOptions}
                  onChange={(value) =>
                    setFormData((prev) => ({
                      ...prev,
                      tts: { ...prev.tts, default_provider: value },
                    }))
                  }
                />
                {Object.entries(formData.tts.voices).map(([provider, entry]) => (
                  <LabeledSelect
                    key={provider}
                    label={`${formatTtsProviderLabel(provider)} 默认音色`}
                    value={entry.default ?? ''}
                    options={entry.options.map((item) => ({ value: item, label: item }))}
                    onChange={(value) =>
                      setFormData((prev) => ({
                        ...prev,
                        tts: {
                          ...prev.tts,
                          voices: {
                            ...prev.tts.voices,
                            [provider]: {
                              ...prev.tts.voices[provider],
                              default: value,
                            },
                          },
                        },
                      }))
                    }
                  />
                ))}
              </div>
            </section>

            <section className="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">OpenAI Voice</h3>
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={formData.openai.enabled}
                    onChange={(event) => setFormData((prev) => ({ ...prev, openai: { ...prev.openai, enabled: event.target.checked } }))}
                  />
                  <span>启用</span>
                </label>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <LabeledInput label="Base URL" value={formData.openai.base_url} onChange={(value) => setFormData((prev) => ({ ...prev, openai: { ...prev.openai, base_url: value } }))} />
                <SecretInput
                  label={`API Key（当前: ${voice.openai.api_key_masked}）`}
                  value={formData.openai.api_key}
                  onChange={(value) => setFormData((prev) => ({ ...prev, openai: { ...prev.openai, api_key: value } }))}
                  show={showOpenAIKey}
                  onToggle={() => setShowOpenAIKey((prev) => !prev)}
                  placeholder="输入新的 OpenAI API Key，留空则保持不变"
                />
                <LabeledInput label="超时（秒）" type="number" value={String(formData.openai.timeout)} onChange={(value) => setFormData((prev) => ({ ...prev, openai: { ...prev.openai, timeout: Number(value) || 0 } }))} />
                <LabeledInput label="TTS 模型" value={formData.openai.tts_model} onChange={(value) => setFormData((prev) => ({ ...prev, openai: { ...prev.openai, tts_model: value } }))} />
                <LabeledInput label="ASR 模型" value={formData.openai.asr_model} onChange={(value) => setFormData((prev) => ({ ...prev, openai: { ...prev.openai, asr_model: value } }))} />
              </div>
            </section>

            <section className="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Whisper Compatible</h3>
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={formData.whisper_compatible.enabled}
                    onChange={(event) => setFormData((prev) => ({ ...prev, whisper_compatible: { ...prev.whisper_compatible, enabled: event.target.checked } }))}
                  />
                  <span>启用</span>
                </label>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <LabeledInput label="Endpoint" value={formData.whisper_compatible.endpoint} onChange={(value) => setFormData((prev) => ({ ...prev, whisper_compatible: { ...prev.whisper_compatible, endpoint: value } }))} />
                <SecretInput
                  label={`Auth Token（当前: ${voice.whisper_compatible.auth_token_masked}）`}
                  value={formData.whisper_compatible.auth_token}
                  onChange={(value) => setFormData((prev) => ({ ...prev, whisper_compatible: { ...prev.whisper_compatible, auth_token: value } }))}
                  show={showWhisperToken}
                  onToggle={() => setShowWhisperToken((prev) => !prev)}
                  placeholder="输入新的鉴权 Token，留空则保持不变"
                />
                <LabeledInput label="超时（秒）" type="number" value={String(formData.whisper_compatible.timeout)} onChange={(value) => setFormData((prev) => ({ ...prev, whisper_compatible: { ...prev.whisper_compatible, timeout: Number(value) || 0 } }))} />
                <LabeledInput label="默认模型" value={formData.whisper_compatible.default_model} onChange={(value) => setFormData((prev) => ({ ...prev, whisper_compatible: { ...prev.whisper_compatible, default_model: value } }))} />
                <LabeledInput label="响应格式" value={formData.whisper_compatible.response_format} onChange={(value) => setFormData((prev) => ({ ...prev, whisper_compatible: { ...prev.whisper_compatible, response_format: value } }))} />
              </div>
            </section>

            <section className="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">FunASR Bailian</h3>
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={formData.funasr_bailian.enabled}
                    onChange={(event) => setFormData((prev) => ({ ...prev, funasr_bailian: { ...prev.funasr_bailian, enabled: event.target.checked } }))}
                  />
                  <span>启用</span>
                </label>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <LabeledInput label="WebSocket 地址" value={formData.funasr_bailian.websocket_url} onChange={(value) => setFormData((prev) => ({ ...prev, funasr_bailian: { ...prev.funasr_bailian, websocket_url: value } }))} />
                <SecretInput
                  label={`API Key（当前: ${voice.funasr_bailian.api_key_masked}）`}
                  value={formData.funasr_bailian.api_key}
                  onChange={(value) => setFormData((prev) => ({ ...prev, funasr_bailian: { ...prev.funasr_bailian, api_key: value } }))}
                  show={showFunASRKey}
                  onToggle={() => setShowFunASRKey((prev) => !prev)}
                  placeholder="输入新的百炼 API Key，留空则保持不变"
                />
                <LabeledInput label="模型名" value={formData.funasr_bailian.model} onChange={(value) => setFormData((prev) => ({ ...prev, funasr_bailian: { ...prev.funasr_bailian, model: value } }))} />
                <LabeledInput label="超时（秒）" type="number" value={String(formData.funasr_bailian.timeout)} onChange={(value) => setFormData((prev) => ({ ...prev, funasr_bailian: { ...prev.funasr_bailian, timeout: Number(value) || 0 } }))} />
                <LabeledInput label="采样率（Hz）" type="number" value={String(formData.funasr_bailian.sample_rate_hz)} onChange={(value) => setFormData((prev) => ({ ...prev, funasr_bailian: { ...prev.funasr_bailian, sample_rate_hz: Number(value) || 0 } }))} />
                <LabeledInput label="分片间隔（毫秒）" type="number" value={String(formData.funasr_bailian.chunk_interval_ms)} onChange={(value) => setFormData((prev) => ({ ...prev, funasr_bailian: { ...prev.funasr_bailian, chunk_interval_ms: Number(value) || 0 } }))} />
                <LabeledInput label="分片大小（字节）" type="number" value={String(formData.funasr_bailian.chunk_size_bytes)} onChange={(value) => setFormData((prev) => ({ ...prev, funasr_bailian: { ...prev.funasr_bailian, chunk_size_bytes: Number(value) || 0 } }))} />
                <LabeledInput label="语言提示（逗号分隔）" value={formData.funasr_bailian.language_hints} onChange={(value) => setFormData((prev) => ({ ...prev, funasr_bailian: { ...prev.funasr_bailian, language_hints: value } }))} />
              </div>
            </section>

            <section className="space-y-3 rounded-xl border border-gray-200 p-4 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">GPT-SoVITS</h3>
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={formData.gpt_sovits.enabled}
                    onChange={(event) => setFormData((prev) => ({ ...prev, gpt_sovits: { ...prev.gpt_sovits, enabled: event.target.checked } }))}
                  />
                  <span>启用</span>
                </label>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <LabeledInput label="Endpoint" value={formData.gpt_sovits.endpoint} onChange={(value) => setFormData((prev) => ({ ...prev, gpt_sovits: { ...prev.gpt_sovits, endpoint: value } }))} />
                <LabeledInput label="超时（秒）" type="number" value={String(formData.gpt_sovits.timeout)} onChange={(value) => setFormData((prev) => ({ ...prev, gpt_sovits: { ...prev.gpt_sovits, timeout: Number(value) || 0 } }))} />
                <LabeledInput label="参考音频路径" value={formData.gpt_sovits.ref_audio_path} onChange={(value) => setFormData((prev) => ({ ...prev, gpt_sovits: { ...prev.gpt_sovits, ref_audio_path: value } }))} />
                <LabeledInput label="参考文本" value={formData.gpt_sovits.ref_text} onChange={(value) => setFormData((prev) => ({ ...prev, gpt_sovits: { ...prev.gpt_sovits, ref_text: value } }))} />
                <LabeledInput label="文本语言" value={formData.gpt_sovits.text_lang} onChange={(value) => setFormData((prev) => ({ ...prev, gpt_sovits: { ...prev.gpt_sovits, text_lang: value } }))} />
                <LabeledInput label="提示语言" value={formData.gpt_sovits.prompt_lang} onChange={(value) => setFormData((prev) => ({ ...prev, gpt_sovits: { ...prev.gpt_sovits, prompt_lang: value } }))} />
              </div>
            </section>

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
          <div className="space-y-4 text-sm">
            <SummaryRow label="语音总开关" value={voice.enabled ? '已启用' : '已关闭'} />
            <SummaryRow label="Provider 外网地址" value={voice.public_base_url} />
            <SummaryRow label="前端播放地址" value={voice.playback_base_url} />
            <SummaryRow label="默认 TTS Provider" value={voice.tts.default_provider} />
            {Object.entries(voice.tts.voices).map(([provider, entry]) => (
              <SummaryRow
                key={provider}
                label={`${formatTtsProviderLabel(provider)} 默认音色`}
                value={entry.default ?? '-'}
              />
            ))}
            <SummaryRow label="OpenAI Voice" value={`${voice.openai.enabled ? '已启用' : '已关闭'} · ${voice.openai.base_url}`} />
            <SummaryRow label="Whisper Compatible" value={`${voice.whisper_compatible.enabled ? '已启用' : '已关闭'} · ${voice.whisper_compatible.endpoint}`} />
            <SummaryRow label="FunASR Bailian" value={`${voice.funasr_bailian.enabled ? '已启用' : '已关闭'} · ${voice.funasr_bailian.websocket_url}`} />
            <SummaryRow label="GPT-SoVITS" value={`${voice.gpt_sovits.enabled ? '已启用' : '已关闭'} · ${voice.gpt_sovits.endpoint}`} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatTtsProviderLabel(provider: string): string {
  const labels: Record<string, string> = {
    edge: 'Edge',
    openai: 'OpenAI',
    'gpt-sovits': 'GPT-SoVITS',
  }
  return labels[provider] || provider
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-gray-600 dark:text-gray-400">{label}</span>
      <span className="text-right text-gray-900 dark:text-white">{value}</span>
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
  type = 'text',
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm text-gray-600 dark:text-gray-300">{label}</label>
      <input
        type={type}
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
      />
    </div>
  );
}

function LabeledSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm text-gray-600 dark:text-gray-300">{label}</label>
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function SecretInput({
  label,
  value,
  onChange,
  show,
  onToggle,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  show: boolean;
  onToggle: () => void;
  placeholder: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm text-gray-600 dark:text-gray-300">{label}</label>
      <div className="relative">
        <input
          type={show ? 'text' : 'password'}
          aria-label={label}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 pr-10 text-gray-900 placeholder-gray-400 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
        />
        <button
          type="button"
          onClick={onToggle}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
        >
          {show ? '隐' : '显'}
        </button>
      </div>
    </div>
  );
}
