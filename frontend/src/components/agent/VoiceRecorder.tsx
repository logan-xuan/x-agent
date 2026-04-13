import { useEffect, useRef, useState } from 'react';

import { Button } from '../ui/Button';

interface VoiceRecorderProps {
  disabled?: boolean;
  onSendVoiceMessage: (file: File, options?: { durationMs?: number }) => Promise<void>;
}

type RecorderState = 'idle' | 'recording' | 'ready' | 'sending' | 'error';

function preferredMimeType(): string {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return 'audio/webm';
  }

  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
  ];

  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? 'audio/webm';
}

export function VoiceRecorder({
  disabled = false,
  onSendVoiceMessage,
}: VoiceRecorderProps) {
  const [recorderState, setRecorderState] = useState<RecorderState>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [previewFile, setPreviewFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewDurationMs, setPreviewDurationMs] = useState<number | undefined>(undefined);
  const [recordingElapsedMs, setRecordingElapsedMs] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef<number | null>(null);

  const clearPreview = () => {
    setPreviewFile(null);
    setPreviewDurationMs(undefined);
    setPreviewUrl((currentUrl) => {
      if (currentUrl) {
        URL.revokeObjectURL(currentUrl);
      }
      return null;
    });
  };

  const stopTracks = () => {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  };

  useEffect(() => {
    if (recorderState !== 'recording') {
      return;
    }

    const interval = window.setInterval(() => {
      if (recordingStartedAtRef.current !== null) {
        setRecordingElapsedMs(Date.now() - recordingStartedAtRef.current);
      }
    }, 250);

    return () => window.clearInterval(interval);
  }, [recorderState]);

  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      stopTracks();
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const handleStartRecording = async () => {
    if (disabled || recorderState === 'sending') {
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setRecorderState('error');
      setErrorMessage('当前浏览器不支持录音');
      return;
    }

    try {
      setErrorMessage(null);
      audioChunksRef.current = [];
      clearPreview();
      setRecordingElapsedMs(0);

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const recorder = new MediaRecorder(stream, { mimeType: preferredMimeType() });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onerror = () => {
        setRecorderState('error');
        setErrorMessage('录音失败，请重试');
        stopTracks();
      };

      recorder.onstop = async () => {
        const mimeType = recorder.mimeType || 'audio/webm';
        const extension = mimeType.includes('mp4') ? 'm4a' : 'webm';
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        const audioFile = new File([audioBlob], `voice-message.${extension}`, { type: mimeType });

        audioChunksRef.current = [];
        stopTracks();
        const finalDurationMs = recordingStartedAtRef.current !== null
          ? Math.max(0, Date.now() - recordingStartedAtRef.current)
          : recordingElapsedMs;
        recordingStartedAtRef.current = null;
        clearPreview();
        setPreviewFile(audioFile);
        setPreviewDurationMs(finalDurationMs > 0 ? finalDurationMs : undefined);
        setPreviewUrl(URL.createObjectURL(audioFile));
        setRecorderState('ready');
      };

      recorder.start();
      recordingStartedAtRef.current = Date.now();
      setRecorderState('recording');
    } catch (error) {
      console.error('Failed to start recording:', error);
      setRecorderState('error');
      setErrorMessage('无法访问麦克风');
      stopTracks();
    }
  };

  const handleStopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
  };

  const handleSendRecording = async () => {
    if (!previewFile) {
      return;
    }

    setRecorderState('sending');
    setErrorMessage(null);

    try {
      await onSendVoiceMessage(
        previewFile,
        previewDurationMs ? { durationMs: previewDurationMs } : undefined,
      );
      clearPreview();
      setRecorderState('idle');
    } catch (error) {
      console.error('Failed to send recorded audio:', error);
      setRecorderState('error');
      setErrorMessage('发送语音失败，请重试');
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        {recorderState === 'recording' ? (
          <Button
            type="button"
            variant="destructive"
            onClick={handleStopRecording}
            className="px-3"
            title="停止录音"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <rect x="7" y="7" width="10" height="10" rx="2" />
            </svg>
          </Button>
        ) : (
          <Button
            type="button"
            variant="ghost"
            onClick={handleStartRecording}
            disabled={disabled || recorderState === 'sending'}
            className="px-3"
            title={previewFile ? '重新录音' : '开始录音'}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18a4 4 0 004-4V7a4 4 0 10-8 0v7a4 4 0 004 4zm0 0v3m-4 0h8" />
            </svg>
          </Button>
        )}

        {(recorderState === 'recording' || recorderState === 'sending' || recorderState === 'ready' || errorMessage) && (
          <span className={`text-xs ${errorMessage ? 'text-red-500' : 'text-gray-500 dark:text-gray-400'}`}>
            {errorMessage
              ? errorMessage
              : recorderState === 'recording'
                ? '录音中...'
                : recorderState === 'sending'
                  ? '发送语音中...'
                  : previewDurationMs
                    ? `录音已完成，可预览后发送 · ${formatDuration(previewDurationMs)}`
                    : '录音已完成，可预览后发送'}
          </span>
        )}

        {recorderState === 'recording' && (
          <span className="rounded-full bg-red-50 px-2 py-1 text-xs font-medium text-red-600 dark:bg-red-950/40 dark:text-red-300">
            {formatDuration(recordingElapsedMs)}
          </span>
        )}
      </div>

      {previewUrl && (
        <div className="rounded-xl border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900/50">
          <audio
            controls
            preload="metadata"
            className="w-full"
            src={previewUrl}
          >
            当前浏览器不支持音频播放。
          </audio>
          <div className="mt-3 flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleStartRecording}
              disabled={disabled || recorderState === 'sending'}
            >
              重录
            </Button>
            <Button
              type="button"
              onClick={handleSendRecording}
              disabled={disabled || recorderState === 'sending'}
            >
              发送录音
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function formatDuration(durationMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}
