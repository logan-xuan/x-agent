"""长耗时媒体任务的后台监控与通知。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from ..config.manager import get_config
from ..conversation.identity import ChannelType
from ..services.image_generation.asset_store import ImageAssetStore, StoredImageAsset
from ..services.image_generation.client import ModelScopeImageClient
from ..services.storage import get_storage_service
from .bridge_dependencies import get_tool_manager
from .notification import NotificationMessage, NotificationTarget, get_notification_router

try:
    from ..utils.logger import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


@dataclass
class MediaBackgroundTask:
    """Tracked media background task metadata."""

    process_id: str
    session_id: str
    agent_id: str
    command: str
    working_dir: str
    kind: str
    title: str
    provider_task_id: str = ""
    prompt: str = ""
    model: str = ""
    size: str = ""
    count: int = 0


class MediaBackgroundTaskManager:
    """Poll background media tasks and notify the owning session on completion."""

    def __init__(self) -> None:
        self._watchers: dict[str, asyncio.Task[None]] = {}

    def schedule(self, task: MediaBackgroundTask) -> None:
        """Start monitoring a background media task if it is not already tracked."""
        watcher_key = self._watcher_key(task)
        if watcher_key in self._watchers:
            return
        self._watchers[watcher_key] = asyncio.create_task(self._watch(task))

    @staticmethod
    def _watcher_key(task: MediaBackgroundTask) -> str:
        if task.process_id:
            return f"process:{task.process_id}"
        if task.provider_task_id:
            return f"provider:{task.provider_task_id}"
        return f"{task.kind}:{task.session_id}:{task.agent_id}"

    async def _watch(self, task: MediaBackgroundTask) -> None:
        watcher_key = self._watcher_key(task)
        try:
            title: str
            message: str
            urgency: str
            if task.kind == "image_generation":
                title, message, urgency = await self._watch_image_generation(task)
            else:
                title, message, urgency = await self._watch_terminal_media(task)

            router = get_notification_router()
            await router.notify(
                NotificationMessage(
                    title=title,
                    content=message,
                    source="background_tool",
                    urgency=urgency,
                ),
                targets=[
                    NotificationTarget(
                        session_id=task.session_id,
                        agent_id=task.agent_id,
                    )
                ],
                channel_types=[ChannelType.WEB_CHAT],
            )
        except Exception as exc:
            logger.warning(
                "Background media task monitor failed",
                extra={
                    "process_id": task.process_id,
                    "provider_task_id": task.provider_task_id,
                    "session_id": task.session_id,
                    "kind": task.kind,
                    "error": str(exc),
                },
            )
        finally:
            self._watchers.pop(watcher_key, None)

    async def _watch_terminal_media(self, task: MediaBackgroundTask) -> tuple[str, str, str]:
        """轮询终端后台任务并在完成时构造通知。"""

        tool_manager = get_tool_manager()
        poller = tool_manager.get_tool("get_terminal_output")
        if poller is None:
            logger.warning(
                "Background media task monitor unavailable: get_terminal_output tool missing",
                extra={"process_id": task.process_id, "kind": task.kind},
            )
            return (
                f"{task.title}失败",
                self._build_failure_message(task, "get_terminal_output tool missing"),
                "high",
            )

        while True:
            await asyncio.sleep(5)
            result = await poller.execute(task.process_id)
            completed = bool(result.metadata.get("completed"))
            if not completed:
                continue

            if result.success:
                return f"{task.title}已完成", self._build_success_message(task), "normal"
            return f"{task.title}失败", self._build_failure_message(task, result.error or result.output), "high"

    async def _watch_image_generation(self, task: MediaBackgroundTask) -> tuple[str, str, str]:
        """等待 ModelScope 图片任务完成并将结果落盘。"""

        config = get_config().image_generation
        client = ModelScopeImageClient(config=config)
        store = ImageAssetStore(config=config, storage=get_storage_service())
        try:
            provider_urls = await client.wait_for_task_result(task.provider_task_id)
            stored_assets: list[StoredImageAsset] = []
            for provider_url in provider_urls:
                image_bytes, mime_type = await client.download_image(provider_url)
                stored = await store.save_generated_image(
                    agent_id=task.agent_id,
                    session_id=task.session_id,
                    prompt=task.prompt,
                    model=task.model or config.model,
                    size=task.size or config.default_size,
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                )
                stored_assets.append(stored)
            return (
                f"{task.title}已完成",
                self._build_image_generation_success_message(task, stored_assets),
                "normal",
            )
        except Exception as exc:
            return f"{task.title}失败", self._build_failure_message(task, str(exc)), "high"
        finally:
            close = getattr(client, "aclose", None)
            if callable(close):
                await close()

    def _build_success_message(self, task: MediaBackgroundTask) -> str:
        lines = [f"{task.title}已完成。", f"进程 ID: `{task.process_id}`"]
        if task.kind == "video_pipeline":
            lines.extend(self._video_pipeline_artifact_lines(task))
        lines.append("如需继续提质，我可以基于最新产物继续优化字幕、画面和节奏。")
        return "\n".join(lines)

    def _build_failure_message(self, task: MediaBackgroundTask, error_text: str) -> str:
        lines = [f"{task.title}执行失败。"]
        if task.process_id:
            lines.append(f"进程 ID: `{task.process_id}`")
        if task.provider_task_id:
            lines.append(f"任务 ID: `{task.provider_task_id}`")
        if task.command:
            lines.append(f"命令: `{task.command}`")
        snippet = (error_text or "").strip()
        if snippet:
            lines.extend(["", "错误摘要：", snippet[:1200]])
        return "\n".join(lines)

    def _build_image_generation_success_message(
        self,
        task: MediaBackgroundTask,
        stored_assets: list[StoredImageAsset],
    ) -> str:
        lines = [f"{task.title}已完成。"]
        if task.provider_task_id:
            lines.append(f"任务 ID: `{task.provider_task_id}`")
        if task.prompt:
            lines.append(f"提示词: {task.prompt}")
        if task.size:
            lines.append(f"尺寸: {task.size}")
        for index, asset in enumerate(stored_assets, start=1):
            lines.append(f"图片 {index}:")
            lines.append(f"![生成图片]({asset.public_url})")
            lines.append(f"URL: {asset.public_url}")
            lines.append(f"Path: {asset.file_path}")
        lines.append("如需继续改风格、构图或比例，我可以基于这批结果继续迭代。")
        return "\n".join(lines)

    def _video_pipeline_artifact_lines(self, task: MediaBackgroundTask) -> list[str]:
        working_dir = Path(task.working_dir)
        output_dir = working_dir / "output"
        lines: list[str] = []
        pipeline_result = output_dir / "pipeline_result.json"
        if pipeline_result.exists():
            lines.append(f"结果文件: `{pipeline_result}`")
            try:
                payload = json.loads(pipeline_result.read_text(encoding="utf-8"))
                topic = str(payload.get("topic") or "").strip()
                if topic:
                    lines.append(f"主题: {topic}")
            except Exception:
                pass

        mp4_candidates = sorted(
            (path for path in output_dir.glob("*.mp4") if path.is_file() and path.stat().st_size > 0),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if mp4_candidates:
            lines.append(f"视频产物: `{mp4_candidates[0]}`")
        else:
            lines.append("未检测到有效的 MP4 产物，请检查 pipeline 日志。")
        return lines


_media_background_task_manager: MediaBackgroundTaskManager | None = None


def get_media_background_task_manager() -> MediaBackgroundTaskManager:
    """Return the singleton media background task manager."""
    global _media_background_task_manager
    if _media_background_task_manager is None:
        _media_background_task_manager = MediaBackgroundTaskManager()
    return _media_background_task_manager
