"""哪吒闹海故事生成任务。"""
import datetime
from pathlib import Path

async def run_task():
    from src.gateway.agent_invoker import AgentInvoker, InvokeSource  # type: ignore[import-not-found]
    from src.conversation.dao.bootstrap import DEFAULT_AGENT_ID  # type: ignore[import-not-found]
    from src.conversation.identity import ChannelType  # type: ignore[import-not-found]

    result = await AgentInvoker().invoke(
        content="创作一集哪吒闹海的深度故事，要求：1. 故事情节跌宕起伏，引人入胜 2. 人物刻画生动，富有个性 3. 富含哲理和深度，体现反抗精神与成长主题 4. 字数控制在500字以内 5. 可以涉及哪吒与龙王三太子冲突、闹海的起因、后续发展等相关情节 6. 每次创作要有新意，推进故事发展",
        agent_id=DEFAULT_AGENT_ID,
        channel_type=ChannelType.WEB_CHAT,
        source=InvokeSource.CRON,
    )

    if result.error:
        return {"success": False, "error": result.error}

    # 保存到文件
    # ⚠️ 必须用绝对路径！任务运行时工作目录是 backend/，相对路径会写错位置
    # 通过配置获取 workspace 绝对路径
    from src.config.manager import ConfigManager  # type: ignore[import-not-found]
    # ⚠️ 必须 expanduser().resolve()，否则 ~ 不展开会产生 workspace/workspace/ 嵌套
    workspace_path = Path(ConfigManager().config.workspace.path).expanduser().resolve()
    now = datetime.datetime.now()
    out = workspace_path / "naz"  # 哪吒故事目录
    out.mkdir(parents=True, exist_ok=True)
    filepath = out / f"nazha_episode_{now.strftime('%Y%m%d_%H%M%S')}.md"
    filepath.write_text(result.response, encoding="utf-8")

    # AgentInvoker 会自动把 LLM 结果推送给用户，无需手动 notify
    return {"success": True, "filepath": str(filepath), "delivered": result.delivered}