import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AgentEditModal } from './AgentEditModal'

describe('AgentEditModal', () => {
  it('shows GPT-SoVITS fields when provider is set to gpt-sovits and submits voice config', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)

    render(
      <AgentEditModal
        agent={{
          agent_id: 'main-agent',
          agent_name: '主 Agent',
          agent_persona: '默认人设',
          voice: {
            enabled: true,
            reply_enabled: false,
            asr_provider: 'openai',
            tts_provider: 'edge',
            tts_voice: 'zh-CN-YunxiNeural',
          },
        }}
        onSave={onSave}
        onCancel={() => {}}
      />,
    )

    fireEvent.change(screen.getByLabelText('TTS Provider'), { target: { value: 'gpt-sovits' } })
    fireEvent.change(screen.getByLabelText('GPT-SoVITS Endpoint'), { target: { value: 'http://localhost:9880' } })
    fireEvent.change(screen.getByLabelText('GPT-SoVITS 参考音频路径'), { target: { value: '/tmp/ref.wav' } })
    fireEvent.change(screen.getByLabelText('GPT-SoVITS 参考文本'), { target: { value: '这是一段参考文本' } })

    fireEvent.click(screen.getByText('保存'))

    expect(onSave).toHaveBeenCalledWith({
      agent_name: '主 Agent',
      agent_persona: '默认人设',
      voice: expect.objectContaining({
        tts_provider: 'gpt-sovits',
        gpt_sovits_endpoint: 'http://localhost:9880',
        gpt_sovits_ref_audio_path: '/tmp/ref.wav',
        gpt_sovits_ref_text: '这是一段参考文本',
      }),
    })
  })

  it('blocks invalid voice settings before submit', () => {
    const onSave = vi.fn().mockResolvedValue(undefined)

    render(
      <AgentEditModal
        agent={{
          agent_id: 'main-agent',
          agent_name: '主 Agent',
          agent_persona: '默认人设',
          voice: {
            enabled: false,
            reply_enabled: true,
            asr_provider: 'openai',
            tts_provider: 'edge',
          },
        }}
        onSave={onSave}
        onCancel={() => {}}
      />,
    )

    expect(screen.getByText('启用默认语音回复前必须先启用语音能力')).toBeInTheDocument()
    const saveButtons = screen.getAllByRole('button', { name: '保存' })
    expect(saveButtons[saveButtons.length - 1]).toBeDisabled()
    expect(onSave).not.toHaveBeenCalled()
  })
})
