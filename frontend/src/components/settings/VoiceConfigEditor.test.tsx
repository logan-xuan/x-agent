import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { VoiceConfigEditor } from './VoiceConfigEditor'

describe('VoiceConfigEditor', () => {
  it('submits updated voice provider settings', async () => {
    const onUpdate = vi.fn().mockResolvedValue(undefined)

    render(
      <VoiceConfigEditor
        voice={{
          enabled: true,
          assets_dir: 'backend/assets/audio',
          public_base_url: 'http://localhost:8888/api/v1/assets/audio',
          playback_base_url: '/api/v1/assets/audio',
          upload_max_bytes: 26214400,
          edge_default_voice: 'zh-CN-YunxiNeural',
          openai: {
            enabled: true,
            base_url: 'https://api.openai.com/v1',
            api_key_masked: 'sk-t...7890',
            timeout: 120,
            tts_model: 'gpt-4o-mini-tts',
            tts_default_voice: 'alloy',
            asr_model: 'gpt-4o-transcribe',
          },
          whisper_compatible: {
            enabled: false,
            endpoint: 'http://localhost:9000/v1/audio/transcriptions',
            auth_token_masked: 'whis...3456',
            timeout: 120,
            default_model: 'whisper-1',
            response_format: 'verbose_json',
          },
          funasr_bailian: {
            enabled: false,
            websocket_url: 'wss://dashscope.aliyuncs.com/api-ws/v1/inference',
            api_key_masked: 'sk-f...7890',
            timeout: 120,
            model: 'fun-asr-realtime-2026-02-28',
            sample_rate_hz: 16000,
            chunk_interval_ms: 100,
            chunk_size_bytes: 3200,
            language_hints: ['zh', 'en'],
          },
          gpt_sovits: {
            enabled: false,
            endpoint: 'http://localhost:9880',
            timeout: 120,
            ref_audio_path: '',
            ref_text: '',
            text_lang: 'zh',
            prompt_lang: 'zh',
          },
        }}
        onUpdate={onUpdate}
        isUpdating={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    fireEvent.change(screen.getByLabelText('前端播放地址'), { target: { value: '/proxy/audio' } })
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://lxagent.fun/v1' } })
    fireEvent.change(screen.getByPlaceholderText('输入新的 OpenAI API Key，留空则保持不变'), { target: { value: 'sk-updated-voice-1234567890' } })
    fireEvent.change(screen.getByLabelText('语言提示（逗号分隔）'), { target: { value: 'zh, yue' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({
      playback_base_url: '/proxy/audio',
      openai: expect.objectContaining({
        base_url: 'https://lxagent.fun/v1',
        api_key: 'sk-updated-voice-1234567890',
      }),
      funasr_bailian: expect.objectContaining({
        language_hints: ['zh', 'yue'],
      }),
    }))
  })
})
