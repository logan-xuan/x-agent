import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AgentChatWindow } from './AgentChatWindow'

vi.mock('@/services/api', () => ({
  listSkills: vi.fn().mockResolvedValue([]),
}))

vi.mock('./AgentSwitcher', () => ({
  AgentSwitcher: () => <div data-testid="agent-switcher" />,
}))

vi.mock('../dev/DevModeWindow', () => ({
  DevModeWindow: () => null,
}))

vi.mock('./AgentMessageList', () => ({
  AgentMessageList: () => <div data-testid="message-list" />,
}))

vi.mock('../skills/SkillMenu', () => ({
  SkillMenu: () => null,
}))

vi.mock('./VoiceRecorder', () => ({
  VoiceRecorder: () => <div data-testid="voice-recorder" />,
}))

describe('AgentChatWindow', () => {
  it('switches between text mode and voice mode', () => {
    render(
      <AgentChatWindow
        sessionId="session-1"
        messages={[]}
        streamingContent=""
        streamingThinking=""
        isLoading={false}
        connectionStatus="connected"
        currentAgentId="main-agent"
        onSendMessage={() => {}}
        onSendVoiceMessage={async () => {}}
        onAbort={() => {}}
        onClearMessages={() => {}}
      />,
    )

    expect(document.querySelector('textarea')).toBeInTheDocument()
    expect(screen.queryByText('发送语音消息')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '语音模式' }))

    expect(screen.getByText('发送语音消息')).toBeInTheDocument()
    expect(screen.getByTestId('voice-recorder')).toBeInTheDocument()
    expect(document.querySelector('textarea')).not.toBeInTheDocument()
  })
})
