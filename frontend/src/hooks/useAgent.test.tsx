import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAgent } from './useAgent'

const mockSend = vi.fn()
const mockGetSession = vi.fn()
const mockCreateSession = vi.fn()
let latestWebSocketOptions: {
  onMessage?: (data: unknown) => void
} | null = null

vi.mock('./useWebSocket', () => ({
  useWebSocket: (options: { onMessage?: (data: unknown) => void }) => {
    latestWebSocketOptions = options
    return {
      status: 'connected',
      send: mockSend,
    }
  },
}))

vi.mock('../services/api', () => ({
  getSession: (...args: unknown[]) => mockGetSession(...args),
  createSession: (...args: unknown[]) => mockCreateSession(...args),
}))

function HookHarness() {
  const agent = useAgent({
    sessionId: 'session-1',
    wsBaseUrl: 'ws://example.test/ws',
  })

  const handleLoadHistory = async () => {
    await agent.loadHistory('session-1')
  }

  const handleSendVoice = async () => {
    const file = new File(['voice-data'], 'voice-message.webm', { type: 'audio/webm' })
    await agent.sendVoiceMessage(file, { durationMs: 4200 })
  }

  const handleTranscript = () => {
    latestWebSocketOptions?.onMessage?.({
      type: 'transcript',
      content: '这是转写结果',
      provider: 'funasr-bailian',
      language: 'zh',
      audio: {
        asset_id: 'upload-asset-1',
        public_url: 'http://localhost:8888/audio-upload.webm',
        mime_type: 'audio/webm',
        format: 'webm',
        duration_ms: 4200,
      },
    })
  }

  return (
    <div>
      <button type="button" onClick={() => void handleLoadHistory()}>
        load-history
      </button>
      <button type="button" onClick={() => void handleSendVoice()}>
        send-voice
      </button>
      <button type="button" onClick={handleTranscript}>
        simulate-transcript
      </button>
      <pre data-testid="messages">{JSON.stringify(agent.messages)}</pre>
    </div>
  )
}

describe('useAgent', () => {
  const createObjectURL = vi.fn(() => 'blob:voice-preview')

  beforeEach(() => {
    mockSend.mockReset()
    mockGetSession.mockReset()
    mockCreateSession.mockReset()
    latestWebSocketOptions = null

    Object.defineProperty(globalThis.URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: createObjectURL,
    })

    Object.defineProperty(File.prototype, 'arrayBuffer', {
      configurable: true,
      writable: true,
      value: function arrayBuffer() {
        return Promise.resolve(new TextEncoder().encode('voice-data').buffer)
      },
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('normalizes persisted voice metadata when loading history', async () => {
    mockGetSession.mockResolvedValue({
      session: {
        id: 'session-1',
        title: 'Voice session',
      },
      messages: [
        {
          id: 'user-voice-1',
          session_id: 'session-1',
          role: 'user',
          content: '你好',
          created_at: '2026-04-12T08:00:00.000Z',
          metadata: {
            audio: {
              asset_id: 'upload-asset-1',
              public_url: 'http://localhost:8888/audio-upload.webm',
              playback_url: '/api/v1/assets/audio/main-agent/2026-04-12/audio-upload.webm',
              mime_type: 'audio/webm',
              format: 'webm',
              duration_ms: 4200,
            },
            transcript: {
              text: '你好',
              provider: 'funasr-bailian',
              language: 'zh',
            },
          },
        },
        {
          id: 'assistant-voice-1',
          session_id: 'session-1',
          role: 'assistant',
          content: '收到',
          created_at: '2026-04-12T08:00:01.000Z',
          metadata: {
            audio_reply: {
              asset_id: 'reply-asset-1',
              public_url: 'http://localhost:8888/reply.mp3',
              playback_url: '/api/v1/assets/audio/main-agent/2026-04-12/reply.mp3',
              mime_type: 'audio/mpeg',
              format: 'mp3',
              provider: 'edge',
              voice: 'zh-CN-YunxiNeural',
            },
          },
        },
      ],
    })

    render(<HookHarness />)

    fireEvent.click(screen.getByRole('button', { name: 'load-history' }))

    await waitFor(() => {
      const messages = JSON.parse(screen.getByTestId('messages').textContent ?? '[]')
      expect(messages).toHaveLength(2)
      expect(messages[0].audio.publicUrl).toBe('/api/v1/assets/audio/main-agent/2026-04-12/audio-upload.webm')
      expect(messages[0].audio.durationMs).toBe(4200)
      expect(messages[0].voiceState.durationMs).toBe(4200)
      expect(messages[1].audio.publicUrl).toBe('/api/v1/assets/audio/main-agent/2026-04-12/reply.mp3')
    })
  })

  it('sends explicit voice duration and preserves it after transcript updates', async () => {
    render(<HookHarness />)

    fireEvent.click(screen.getByRole('button', { name: 'send-voice' }))

    await waitFor(() => {
      expect(mockSend).toHaveBeenCalledTimes(1)
    })

    expect(mockSend.mock.calls[0][0]).toMatchObject({
      type: 'audio_message',
      audio: {
        filename: 'voice-message.webm',
        format: 'webm',
        mime_type: 'audio/webm',
        duration_ms: 4200,
      },
    })

    fireEvent.click(screen.getByRole('button', { name: 'simulate-transcript' }))

    await waitFor(() => {
      const messages = JSON.parse(screen.getByTestId('messages').textContent ?? '[]')
      expect(messages[0].audio.durationMs).toBe(4200)
      expect(messages[0].voiceState.label).toBe('语音已转写')
      expect(messages[0].voiceState.durationMs).toBe(4200)
    })
  })
})
