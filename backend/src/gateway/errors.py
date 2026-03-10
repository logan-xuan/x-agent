"""Gateway 错误定义。

定义 Gateway 层的异常层次结构，用于精确的错误处理和上报。
所有 Gateway 异常继承自 GatewayError 基类。
"""

from __future__ import annotations


class GatewayError(Exception):
    """Gateway 基础异常。

    所有 Gateway 层的异常都继承自此类，
    便于上游端点统一捕获和处理。

    Attributes:
        message: 人类可读的错误描述。
        error_type: 错误类型标识，用于序列化。
    """

    def __init__(self, message: str) -> None:
        self.message = message
        self.error_type = type(self).__name__
        super().__init__(message)


class AgentNotFoundError(GatewayError):
    """指定的 Agent 不存在。

    当 Envelope 中的 agent_id 或 agent_name 无法匹配到
    任何已注册的 Agent 时抛出。

    Attributes:
        agent_id: 请求的 Agent ID（如有）。
        agent_name: 请求的 Agent 名称（如有）。
    """

    def __init__(
        self,
        message: str = "Agent not found",
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        detail = message
        if agent_id:
            detail = f"{message} (agent_id={agent_id})"
        elif agent_name:
            detail = f"{message} (agent_name={agent_name})"
        super().__init__(detail)


class SessionNotFoundError(GatewayError):
    """指定的 Session 不存在。

    当 Envelope 中的 session_id 无法匹配到任何已存在的会话，
    且无法自动创建新会话时抛出。

    Attributes:
        session_id: 请求的 Session ID。
    """

    def __init__(
        self,
        session_id: str,
        message: str = "Session not found",
    ) -> None:
        self.session_id = session_id
        super().__init__(f"{message} (session_id={session_id})")


class EnvelopeValidationError(GatewayError):
    """Envelope 验证失败。

    当 Envelope 的必填字段缺失或格式不正确时抛出。

    Attributes:
        validation_errors: 具体的验证错误列表。
    """

    def __init__(self, validation_errors: list[str]) -> None:
        self.validation_errors = validation_errors
        detail = "; ".join(validation_errors)
        super().__init__(f"Envelope validation failed: {detail}")


class DispatchError(GatewayError):
    """分发过程中的运行时错误。

    当 GatewayDispatcher 在处理 Envelope 过程中遇到
    非预期的错误时抛出（如 Agent Core 内部异常）。
    """

    pass


class AbortError(GatewayError):
    """会话中断错误。

    当尝试中断一个不存在或已完成的会话时抛出。

    Attributes:
        session_id: 尝试中断的 Session ID。
    """

    def __init__(self, session_id: str, message: str = "Cannot abort session") -> None:
        self.session_id = session_id
        super().__init__(f"{message} (session_id={session_id})")
