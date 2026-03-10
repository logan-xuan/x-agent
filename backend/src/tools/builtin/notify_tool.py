"""Agent 主动推送通知工具。

NotifyTool 允许 Agent 在对话过程中主动向用户推送通知消息。
与 AgentInvoker 的区别：
- NotifyTool: Agent 自己在对话中调用，直接推送文本，不经过 agent_loop
- AgentInvoker: 外部触发，经过完整 agent_loop（加载上下文、技能、工具等）

使用场景：
1. Agent 在执行长时间任务时，主动推送进度通知
2. Agent 在后台监控到异常时，推送告警通知
3. Agent 需要向其他渠道（如钉钉、Telegram）推送消息
4. Agent 需要向指定 session 推送提醒

推送策略：
- 默认推送到当前会话的 WebChat 通道
- 支持指定 channel_type 推送到其他通道
- 支持指定 session_id 推送到其他会话
- 在线用户实时推送，离线用户暂存到 Outbox
"""

from src.utils.logger import get_logger
from ..base import BaseTool, ToolParameter, ToolParameterType, ToolResult

logger = get_logger(__name__)


class NotifyTool(BaseTool):
    """Agent 主动推送通知工具。

    允许 Agent 在对话过程中主动向用户推送通知消息。
    支持多种通道（WebChat、DingTalk、Telegram）和多种消息类型。

    Features:
    - 多通道推送（WebChat / DingTalk / Telegram）
    - 在线实时推送 + 离线 Outbox 暂存
    - 支持消息标题、紧急程度
    - 支持指定目标 session 或 agent
    """

    @property
    def name(self) -> str:
        return "notify"

    @property
    def description(self) -> str:
        return (
            "Send a notification message to the user. "
            "Use this tool when you need to proactively push information to the user, "
            "such as task progress updates, alerts, reminders, or important notifications. "
            "The message will be delivered in real-time if the user is online, "
            "or queued for delivery when they reconnect. "
            "Supports multiple channels: web_chat (default), dingtalk, telegram."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="content",
                type=ToolParameterType.STRING,
                description=(
                    "The notification message content to send to the user. "
                    "Supports plain text and Markdown formatting."
                ),
                required=True,
                min_length=1,
                max_length=4096,
            ),
            ToolParameter(
                name="title",
                type=ToolParameterType.STRING,
                description=(
                    "Optional title for the notification. "
                    "Displayed as a header in the notification UI."
                ),
                required=False,
                default="",
                max_length=200,
            ),
            ToolParameter(
                name="urgency",
                type=ToolParameterType.STRING,
                description=(
                    "Urgency level of the notification. "
                    "'low' for informational, 'normal' for standard, 'high' for urgent/critical."
                ),
                required=False,
                default="normal",
                enum=["low", "normal", "high"],
            ),
            ToolParameter(
                name="channel",
                type=ToolParameterType.STRING,
                description=(
                    "Target notification channel. "
                    "'web_chat' (default) pushes to the user's browser/app, "
                    "'dingtalk' pushes via DingTalk webhook, "
                    "'telegram' pushes via Telegram Bot API."
                ),
                required=False,
                default="web_chat",
                enum=["web_chat", "dingtalk", "telegram"],
            ),
            ToolParameter(
                name="session_id",
                type=ToolParameterType.STRING,
                description=(
                    "Target session ID to push the notification to. "
                    "If not provided, pushes to the current active session."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="webhook_url",
                type=ToolParameterType.STRING,
                description=(
                    "DingTalk webhook URL. Required when channel is 'dingtalk'. "
                    "Format: https://oapi.dingtalk.com/robot/send?access_token=xxx"
                ),
                required=False,
                default=None,
            ),
        ]

    async def execute(
        self,
        content: str,
        title: str = "",
        urgency: str = "normal",
        channel: str = "web_chat",
        session_id: str | None = None,
        webhook_url: str | None = None,
    ) -> ToolResult:
        """Execute the notification push.

        Args:
            content: Notification message content.
            title: Optional notification title.
            urgency: Urgency level (low/normal/high).
            channel: Target channel (web_chat/dingtalk/telegram).
            session_id: Target session ID (optional).
            webhook_url: DingTalk webhook URL (optional).

        Returns:
            ToolResult with delivery status.
        """
        try:
            from src.gateway.notification import (
                ChannelSendResult,
                NotificationMessage,
                NotificationRouter,
                NotificationTarget,
                get_notification_router,
            )
            from src.conversation.identity import ChannelType

            # 1. 构建通知消息
            notification_message = NotificationMessage(
                content=content,
                title=title or None,
                urgency=urgency,
                source="agent",
                message_type="notification",
            )

            # 2. 构建通知目标
            target = NotificationTarget(
                session_id=session_id,
                webhook_url=webhook_url,
            )

            # 如果没有指定 session_id，尝试从当前上下文获取
            if not session_id:
                target.session_id = self._get_current_session_id()

            # 如果还是没有 session_id，设置 agent_id 让 resolver 自动解析
            if not target.session_id:
                target.agent_id = self._get_current_agent_id()

            # 3. 确定通道类型
            channel_type_map = {
                "web_chat": ChannelType.WEB_CHAT,
                "dingtalk": ChannelType.DINGTALK,
                "telegram": ChannelType.TELEGRAM,
            }
            target_channel_type = channel_type_map.get(channel, ChannelType.WEB_CHAT)

            # 4. 通过 NotificationRouter 发送
            router = get_notification_router()
            results = await router.notify(
                notification_message,
                targets=[target],
                channel_types=[target_channel_type],
            )

            # 5. 汇总结果
            if not results:
                logger.warning(
                    "No notification channels available",
                    extra={"channel": channel},
                )
                return ToolResult.error_result(
                    f"No notification channel available for '{channel}'. "
                    "The channel may not be registered or configured."
                )

            result = results[0]
            return self._build_result(result, channel)

        except Exception as exc:
            logger.error(
                "NotifyTool execution failed",
                extra={"error": str(exc), "channel": channel},
                exc_info=True,
            )
            return ToolResult.error_result(
                f"Failed to send notification: {str(exc)}"
            )

    def _get_current_session_id(self) -> str | None:
        """从当前 AgentContext 获取 session_id。"""
        try:
            from src.conversation.context import get_current_context
            context = get_current_context()
            if context and context.identity:
                return context.identity.session_id
        except Exception:
            pass
        return None

    def _get_current_agent_id(self) -> str | None:
        """从当前 AgentContext 获取 agent_id。"""
        try:
            from src.conversation.context import get_current_context
            context = get_current_context()
            if context and context.identity:
                return context.identity.agent_id
        except Exception:
            pass

        try:
            from src.conversation.dao import DEFAULT_AGENT_ID
            return DEFAULT_AGENT_ID
        except Exception:
            return None

    @staticmethod
    def _build_result(result, channel: str) -> ToolResult:
        """根据通道发送结果构建 ToolResult。"""
        if result.delivered:
            status_text = "delivered in real-time"
            output = (
                f"Notification sent successfully via {channel}. "
                f"Status: {status_text}."
            )
            if result.session_id:
                output += f" Session: {result.session_id}."

            return ToolResult.ok(
                output,
                delivered=True,
                queued=False,
                channel=channel,
                session_id=result.session_id,
            )

        if result.queued:
            output = (
                f"User is currently offline. Notification queued via {channel} "
                "and will be delivered when the user reconnects."
            )
            if result.session_id:
                output += f" Session: {result.session_id}."

            return ToolResult.ok(
                output,
                delivered=False,
                queued=True,
                channel=channel,
                session_id=result.session_id,
            )

        error_detail = result.error or "Unknown error"
        return ToolResult.error_result(
            f"Failed to send notification via {channel}: {error_detail}",
            channel=channel,
        )
