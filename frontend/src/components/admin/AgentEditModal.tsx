import { useMemo, useState } from 'react';

import { EDGE_VOICE_OPTIONS } from '../../constants/edgeVoices';
import { Button } from '../ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card';

export interface AgentVoiceConfig {
  enabled: boolean;
  reply_enabled: boolean;
  asr_provider: string;
  tts: {
    provider: string;
    voice?: string | null;
  };
  gpt_sovits?: {
    endpoint?: string | null;
    ref_audio_path?: string | null;
    ref_text?: string | null;
  };
}

export interface EditableAgent {
  agent_id: string;
  agent_name: string;
  agent_persona: string;
  voice: AgentVoiceConfig;
}

interface AgentEditModalProps {
  agent: EditableAgent;
  onSave: (updated: {
    agent_name: string;
    agent_persona: string;
    voice: AgentVoiceConfig;
  }) => Promise<void>;
  onCancel: () => void;
}

const COMMON_TTS_PROVIDERS = ['edge', 'openai', 'gpt-sovits'] as const;
const COMMON_ASR_PROVIDERS = ['openai', 'whisper-compatible'] as const;

function resolveProviderSelection(
  value: string,
  commonProviders: readonly string[],
): { preset: string; customValue: string } {
  if (commonProviders.includes(value)) {
    return { preset: value, customValue: '' };
  }
  return { preset: 'custom', customValue: value };
}

export function AgentEditModal({ agent, onSave, onCancel }: AgentEditModalProps) {
  const [agentName, setAgentName] = useState(agent.agent_name);
  const [agentPersona, setAgentPersona] = useState(agent.agent_persona);
  const [voiceEnabled, setVoiceEnabled] = useState(agent.voice.enabled);
  const [replyEnabled, setReplyEnabled] = useState(agent.voice.reply_enabled);
  const initialTtsProvider = resolveProviderSelection(agent.voice.tts.provider || 'edge', COMMON_TTS_PROVIDERS);
  const initialAsrProvider = resolveProviderSelection(agent.voice.asr_provider || 'openai', COMMON_ASR_PROVIDERS);
  const [ttsProviderPreset, setTtsProviderPreset] = useState(initialTtsProvider.preset);
  const [ttsProviderCustom, setTtsProviderCustom] = useState(initialTtsProvider.customValue);
  const [asrProviderPreset, setAsrProviderPreset] = useState(initialAsrProvider.preset);
  const [asrProviderCustom, setAsrProviderCustom] = useState(initialAsrProvider.customValue);
  const [ttsVoice, setTtsVoice] = useState(agent.voice.tts.voice || '');
  const [gptSoVitsEndpoint, setGptSoVitsEndpoint] = useState(agent.voice.gpt_sovits?.endpoint || '');
  const [gptSoVitsRefAudioPath, setGptSoVitsRefAudioPath] = useState(agent.voice.gpt_sovits?.ref_audio_path || '');
  const [gptSoVitsRefText, setGptSoVitsRefText] = useState(agent.voice.gpt_sovits?.ref_text || '');
  const [saving, setSaving] = useState(false);

  const ttsProvider = ttsProviderPreset === 'custom' ? ttsProviderCustom.trim() : ttsProviderPreset;
  const asrProvider = asrProviderPreset === 'custom' ? asrProviderCustom.trim() : asrProviderPreset;
  const showGptSoVitsFields = useMemo(() => ttsProvider === 'gpt-sovits', [ttsProvider]);
  const showEdgeVoiceSelect = useMemo(() => ttsProvider === 'edge', [ttsProvider]);
  const showVoiceIdentifierInput = useMemo(
    () => ttsProvider !== 'edge' && ttsProvider !== 'gpt-sovits',
    [ttsProvider],
  );
  const validationErrors = useMemo(() => {
    const errors: string[] = [];

    if (!agentName.trim()) {
      errors.push('Agent 名称不能为空');
    }

    if (voiceEnabled && !asrProvider) {
      errors.push('启用语音能力时必须选择 ASR Provider');
    }

    if (voiceEnabled && !ttsProvider) {
      errors.push('启用语音能力时必须选择 TTS Provider');
    }

    if (replyEnabled && !voiceEnabled) {
      errors.push('启用默认语音回复前必须先启用语音能力');
    }

    if (ttsProvider === 'gpt-sovits') {
      if (!gptSoVitsEndpoint.trim()) {
        errors.push('GPT-SoVITS Endpoint 不能为空');
      }
      if (!gptSoVitsRefAudioPath.trim()) {
        errors.push('GPT-SoVITS 参考音频路径不能为空');
      }
      if (!gptSoVitsRefText.trim()) {
        errors.push('GPT-SoVITS 参考文本不能为空');
      }
    }

    return errors;
  }, [
    agentName,
    asrProvider,
    gptSoVitsEndpoint,
    gptSoVitsRefAudioPath,
    gptSoVitsRefText,
    replyEnabled,
    ttsProvider,
    voiceEnabled,
  ]);
  const fieldId = (name: string) => `agent-edit-${agent.agent_id}-${name}`;

  const handleSave = async () => {
    if (validationErrors.length > 0) {
      return;
    }

    setSaving(true);
    try {
      await onSave({
        agent_name: agentName,
        agent_persona: agentPersona,
        voice: {
          enabled: voiceEnabled,
          reply_enabled: replyEnabled,
          asr_provider: asrProvider,
          tts: {
            provider: ttsProvider,
            voice: ttsVoice || null,
          },
          gpt_sovits: {
            endpoint: gptSoVitsEndpoint || null,
            ref_audio_path: gptSoVitsRefAudioPath || null,
            ref_text: gptSoVitsRefText || null,
          },
        },
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>编辑 Agent</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                Agent 名称
              </label>
              <input
                id={fieldId('name')}
                type="text"
                value={agentName}
                onChange={(event) => setAgentName(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              />
            </div>

            <div className="rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-700">
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={voiceEnabled}
                    onChange={(event) => setVoiceEnabled(event.target.checked)}
                  />
                  <span>启用语音能力</span>
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={replyEnabled}
                    onChange={(event) => setReplyEnabled(event.target.checked)}
                  />
                  <span>默认语音回复</span>
                </label>
              </div>
            </div>
          </div>

          <div>
              <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                人设描述
              </label>
              <textarea
                id={fieldId('persona')}
                value={agentPersona}
                onChange={(event) => setAgentPersona(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                rows={3}
            />
          </div>

          <div className="rounded-xl border border-gray-200 p-4 dark:border-gray-700">
            <div className="mb-3 text-sm font-medium text-gray-900 dark:text-white">语音配置</div>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                  ASR Provider
                </label>
                <select
                  aria-label="ASR Provider"
                  id={fieldId('asr-provider')}
                  value={asrProviderPreset}
                  onChange={(event) => setAsrProviderPreset(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                >
                  <option value="openai">OpenAI</option>
                  <option value="whisper-compatible">Whisper Compatible</option>
                  <option value="custom">自定义</option>
                </select>
                {asrProviderPreset === 'custom' && (
                  <input
                    aria-label="自定义 ASR Provider"
                    id={fieldId('custom-asr-provider')}
                    type="text"
                    value={asrProviderCustom}
                    onChange={(event) => setAsrProviderCustom(event.target.value)}
                    placeholder="输入自定义 ASR provider"
                    className="mt-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  />
                )}
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                  TTS Provider
                </label>
                <select
                  aria-label="TTS Provider"
                  id={fieldId('tts-provider')}
                  value={ttsProviderPreset}
                  onChange={(event) => setTtsProviderPreset(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                >
                  <option value="edge">Edge TTS</option>
                  <option value="openai">OpenAI TTS</option>
                  <option value="gpt-sovits">GPT-SoVITS</option>
                  <option value="custom">自定义</option>
                </select>
                {ttsProviderPreset === 'custom' && (
                  <input
                    aria-label="自定义 TTS Provider"
                    id={fieldId('custom-tts-provider')}
                    type="text"
                    value={ttsProviderCustom}
                    onChange={(event) => setTtsProviderCustom(event.target.value)}
                    placeholder="输入自定义 TTS provider"
                    className="mt-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  />
                )}
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                  {showEdgeVoiceSelect ? 'Edge 音色' : '音色标识'}
                </label>
                {showEdgeVoiceSelect ? (
                  <select
                    aria-label="Edge 音色"
                    id={fieldId('tts-voice')}
                    value={ttsVoice}
                    onChange={(event) => setTtsVoice(event.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  >
                    <option value="">跟随全局默认</option>
                    {EDGE_VOICE_OPTIONS.map((voiceOption) => (
                      <option key={voiceOption} value={voiceOption}>
                        {voiceOption}
                      </option>
                    ))}
                  </select>
                ) : showVoiceIdentifierInput ? (
                  <input
                    aria-label="音色标识"
                    id={fieldId('tts-voice')}
                    type="text"
                    value={ttsVoice}
                    onChange={(event) => setTtsVoice(event.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  />
                ) : (
                  <div className="rounded-lg border border-dashed border-gray-300 px-3 py-2 text-sm text-gray-400 dark:border-gray-600">
                    当前 Provider 不使用 Edge 音色枚举
                  </div>
                )}
              </div>
            </div>

            {showGptSoVitsFields && (
              <div className="mt-4 grid gap-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                    GPT-SoVITS Endpoint
                  </label>
                  <input
                    aria-label="GPT-SoVITS Endpoint"
                    id={fieldId('gpt-sovits-endpoint')}
                    type="text"
                    value={gptSoVitsEndpoint}
                    onChange={(event) => setGptSoVitsEndpoint(event.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                    GPT-SoVITS 参考音频路径
                  </label>
                  <input
                    aria-label="GPT-SoVITS 参考音频路径"
                    id={fieldId('gpt-sovits-ref-audio')}
                    type="text"
                    value={gptSoVitsRefAudioPath}
                    onChange={(event) => setGptSoVitsRefAudioPath(event.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">
                    GPT-SoVITS 参考文本
                  </label>
                  <textarea
                    aria-label="GPT-SoVITS 参考文本"
                    id={fieldId('gpt-sovits-ref-text')}
                    value={gptSoVitsRefText}
                    onChange={(event) => setGptSoVitsRefText(event.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                    rows={3}
                  />
                </div>
              </div>
            )}
          </div>

          {validationErrors.length > 0 && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
              {validationErrors.map((error) => (
                <div key={error}>{error}</div>
              ))}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onCancel}>取消</Button>
            <Button size="sm" onClick={handleSave} disabled={saving || validationErrors.length > 0}>
              {saving ? '保存中...' : '保存'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
