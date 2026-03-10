"""笑话定时推送任务。

通过 AgentInvoker 调用 LLM 生成笑话，并推送到用户的 WebChat 终端。

AgentInvoker 完整链路：
1. 解析 Session（找到用户的 WebChat 会话）
2. 构建 Identity（INTERNAL 协议）
3. 创建 Agent + 加载历史上下文
4. 执行 agent_loop（LLM 生成笑话）
5. 推送到 ConnectionRegistry（实时推送到 WebChat）
6. 推送失败则暂存到 Outbox（用户重连时投递）
"""

from datetime import datetime


async def run_task():
    """任务入口函数（cron 调度器调用）。

    注意：cron 调度器使用 AsyncScheduler，会自动检测协程函数并 await，
    所以这里直接定义为 async 函数即可。
    """
    from src.gateway.agent_invoker import AgentInvoker, InvokeSource  # type: ignore[import-not-found]
    from src.conversation.dao.bootstrap import DEFAULT_AGENT_ID  # type: ignore[import-not-found]
    from src.conversation.identity import ChannelType  # type: ignore[import-not-found]

    invoker = AgentInvoker()
    result = await invoker.invoke(
        content="请写一个好笑的笑话，要求原创、幽默、让人忍不住笑出来。**注意：请将笑话控制在 200 字以内，简洁精炼。**直接输出笑话内容即可，不需要额外的解释。",
        agent_id=DEFAULT_AGENT_ID,
        channel_type=ChannelType.WEB_CHAT,
        source=InvokeSource.CRON,
    )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if result.error:
        return {
            "success": False,
            "timestamp": timestamp,
            "error": result.error,
        }

    return {
        "success": True,
        "timestamp": timestamp,
        "joke": result.response,
        "delivered": result.delivered,
        "queued": result.queued,
        "session_id": result.session_id,
    }