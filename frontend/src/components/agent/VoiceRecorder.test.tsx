import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { VoiceRecorder } from './VoiceRecorder'

class FakeMediaRecorder {
  static isTypeSupported(type: string) {
    return type.includes('webm')
  }

  mimeType = 'audio/webm'
  state: 'inactive' | 'recording' = 'inactive'
  ondataavailable: ((event: BlobEvent) => void) | null = null
  onerror: (() => void) | null = null
  onstop: (() => void | Promise<void>) | null = null

  constructor(public stream: MediaStream, _options?: MediaRecorderOptions) {}

  start() {
    this.state = 'recording'
  }

  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({
      data: new Blob(['voice-data'], { type: 'audio/webm' }),
    } as BlobEvent)
    void this.onstop?.()
  }
}

describe('VoiceRecorder', () => {
  const stopTrack = vi.fn()
  const createObjectURL = vi.fn(() => 'blob:voice-preview')
  const revokeObjectURL = vi.fn()

  beforeEach(() => {
    stopTrack.mockReset()
    createObjectURL.mockClear()
    revokeObjectURL.mockClear()

    Object.defineProperty(globalThis, 'MediaRecorder', {
      configurable: true,
      writable: true,
      value: FakeMediaRecorder,
    })

    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: stopTrack }],
        } as unknown as MediaStream),
      },
    })

    Object.defineProperty(globalThis.URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: createObjectURL,
    })

    Object.defineProperty(globalThis.URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: revokeObjectURL,
    })
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('creates a preview first and sends only after confirmation', async () => {
    const onSendVoiceMessage = vi.fn().mockResolvedValue(undefined)

    const { container } = render(<VoiceRecorder onSendVoiceMessage={onSendVoiceMessage} />)

    fireEvent.click(screen.getByTitle('开始录音'))

    expect(await screen.findByText('录音中...')).toBeInTheDocument()

    fireEvent.click(screen.getByTitle('停止录音'))

    expect(await screen.findByText(/录音已完成，可预览后发送/)).toBeInTheDocument()
    expect(container.querySelector('audio')).toBeInTheDocument()
    expect(onSendVoiceMessage).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '发送录音' }))

    await waitFor(() => {
      expect(onSendVoiceMessage).toHaveBeenCalledTimes(1)
    })

    const sentFile = onSendVoiceMessage.mock.calls[0][0] as File
    const sendOptions = onSendVoiceMessage.mock.calls[0][1] as { durationMs?: number } | undefined
    expect(sentFile).toBeInstanceOf(File)
    expect(sentFile.name).toBe('voice-message.webm')
    expect(sendOptions?.durationMs).toBeGreaterThanOrEqual(0)
    expect(stopTrack).toHaveBeenCalled()
    expect(createObjectURL).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:voice-preview')
  })

  it('shows recording duration while recording', async () => {
    vi.useFakeTimers()
    render(<VoiceRecorder onSendVoiceMessage={vi.fn().mockResolvedValue(undefined)} />)

    await act(async () => {
      fireEvent.click(screen.getByTitle('开始录音'))
      await Promise.resolve()
    })

    expect(screen.getByText('录音中...')).toBeInTheDocument()
    expect(screen.getByText('00:00')).toBeInTheDocument()
    expect(screen.getByTitle('停止录音')).toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500)
    })

    expect(screen.getByText('00:02')).toBeInTheDocument()
  })

  it('passes the measured duration when sending a recorded clip', async () => {
    vi.useFakeTimers()
    const onSendVoiceMessage = vi.fn().mockResolvedValue(undefined)

    render(<VoiceRecorder onSendVoiceMessage={onSendVoiceMessage} />)

    await act(async () => {
      fireEvent.click(screen.getByTitle('开始录音'))
      await Promise.resolve()
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3600)
    })

    await act(async () => {
      fireEvent.click(screen.getByTitle('停止录音'))
      await Promise.resolve()
    })

    expect(screen.getByText('录音已完成，可预览后发送 · 00:03')).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '发送录音' }))
      await Promise.resolve()
    })

    expect(onSendVoiceMessage).toHaveBeenCalledTimes(1)
    expect(onSendVoiceMessage.mock.calls[0][1]).toEqual({ durationMs: 3600 })
  })
})
