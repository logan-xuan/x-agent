import { describe, expect, it } from "vitest";
import { afterEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { AgentMessageItem } from "./AgentMessageItem";
import type { AgentMessage } from "../../hooks/useAgent";

function buildAssistantMessage(content: string): AgentMessage {
  return {
    id: "assistant-1",
    sessionId: "session-1",
    role: "assistant",
    content,
    createdAt: new Date().toISOString(),
    model: "gpt-5.4",
  };
}

afterEach(() => {
  cleanup();
});

describe("AgentMessageItem", () => {
  it("renders assistant bold markdown without showing literal asterisks", () => {
    const { container } = render(
      <AgentMessageItem
        message={buildAssistantMessage("**穿搭建议：**\n- **上衣**：薄外套")}
      />,
    );

    expect(screen.getByText("穿搭建议：")).toBeInTheDocument();
    expect(screen.getByText("上衣")).toBeInTheDocument();
    expect(container).not.toHaveTextContent("**");
  });

  it("renders markdown bullet lines as list items", () => {
    const { container } = render(
      <AgentMessageItem
        message={buildAssistantMessage(
          "**穿搭建议：**\n- **上衣**：薄外套\n- **鞋子**：运动鞋",
        )}
      />,
    );

    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("鞋子")).toBeInTheDocument();
    expect(container).not.toHaveTextContent("- **");
  });

  it("renders markdown image syntax as an inline image for assistant messages", () => {
    render(
      <AgentMessageItem
        message={buildAssistantMessage(
          "先看这张图\n\n![小猫](http://localhost:8888/cat.png)",
        )}
      />,
    );

    const image = screen.getByRole("img", { name: "小猫" });

    expect(image).toBeInTheDocument();
    expect(image).toHaveAttribute("src", "http://localhost:8888/cat.png");
  });

  it("opens a lightbox when clicking an assistant image and closes on Escape", () => {
    render(
      <AgentMessageItem
        message={buildAssistantMessage(
          "先看这张图\n\n![小猫](http://localhost:8888/cat.png)",
        )}
      />,
    );

    const image = screen.getByRole("img", { name: "小猫" });
    fireEvent.click(image);

    const dialog = screen.getByRole("dialog", { name: "图片预览" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: "小猫" })).toHaveLength(2);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(
      screen.queryByRole("dialog", { name: "图片预览" }),
    ).not.toBeInTheDocument();
  });

  it("closes the lightbox when clicking the backdrop", () => {
    render(
      <AgentMessageItem
        message={buildAssistantMessage(
          "先看这张图\n\n![小猫](http://localhost:8888/cat.png)",
        )}
      />,
    );

    fireEvent.click(screen.getByRole("img", { name: "小猫" }));
    fireEvent.click(screen.getByRole("dialog", { name: "图片预览" }));

    expect(
      screen.queryByRole("dialog", { name: "图片预览" }),
    ).not.toBeInTheDocument();
  });

  it("renders transcript and audio player metadata when voice fields are present", () => {
    const message: AgentMessage = {
      id: "assistant-voice-1",
      sessionId: "session-1",
      role: "assistant",
      content: "这是语音回复",
      createdAt: new Date().toISOString(),
      voiceState: {
        phase: "ready",
        label: "语音回复已生成",
      },
      audio: {
        publicUrl:
          "http://localhost:8888/api/v1/assets/audio/main-agent/2026-04-12/reply.mp3",
        provider: "edge",
        voice: "zh-CN-YunxiNeural",
        format: "mp3",
      },
      transcript: {
        text: "这是语音转写",
        provider: "openai",
        language: "zh",
      },
    };

    const { container } = render(<AgentMessageItem message={message} />);

    expect(screen.getByText("语音转写")).toBeInTheDocument();
    expect(screen.getByText("这是语音转写")).toBeInTheDocument();
    expect(screen.getByText("语音回复已生成")).toBeInTheDocument();
    expect(
      screen.getByText("edge · zh-CN-YunxiNeural · mp3"),
    ).toBeInTheDocument();
    expect(container.querySelector("audio")).toBeInTheDocument();
  });

  it("renders voice error details when speech processing fails", () => {
    const message: AgentMessage = {
      id: "user-voice-error-1",
      sessionId: "session-1",
      role: "user",
      content: "语音转写失败",
      createdAt: new Date().toISOString(),
      transcript: {
        text: "语音转写失败",
      },
      voiceError: {
        stage: "asr",
        message: "语音转写失败，请重试",
        recoverable: true,
      },
    };

    render(<AgentMessageItem message={message} />);

    expect(screen.getAllByText("语音转写失败")).toHaveLength(3);
    expect(screen.getByText("语音转写失败，请重试")).toBeInTheDocument();
  });

  it("renders voice status badge with duration for user messages", () => {
    const message: AgentMessage = {
      id: "user-voice-status-1",
      sessionId: "session-1",
      role: "user",
      content: "语音消息转写中...",
      createdAt: new Date().toISOString(),
      voiceState: {
        phase: "transcribing",
        label: "语音转写中",
        durationMs: 4200,
      },
    };

    render(<AgentMessageItem message={message} />);

    expect(screen.getByText("语音转写中")).toBeInTheDocument();
    expect(screen.getByText("4.2 秒")).toBeInTheDocument();
  });
});
