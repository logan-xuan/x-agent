"""内置文生图工具。"""

from __future__ import annotations

from typing import Any

from ...config.manager import get_config
from ...conversation.context import get_current_context
from ...services.image_generation.asset_store import ImageAssetStore
from ...services.image_generation.client import ModelScopeImageClient
from ...services.storage import get_storage_service
from ..base import BaseTool, ToolParameter, ToolParameterType, ToolResult


class GenerateImageTool(BaseTool):
    """根据自然语言描述生成图片并返回公开资产地址。"""

    def __init__(self) -> None:
        super().__init__()
        image_config = get_config().image_generation
        self._config = image_config
        self._client = ModelScopeImageClient(config=image_config)
        self._store = ImageAssetStore(config=image_config, storage=get_storage_service())
        self._max_count = image_config.max_count

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return "根据自然语言描述生成图片，并返回项目资产空间中的公开访问地址。"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="prompt",
                type=ToolParameterType.STRING,
                description="图片描述词。",
                required=True,
            ),
            ToolParameter(
                name="size",
                type=ToolParameterType.STRING,
                description="输出尺寸。",
                required=False,
                default="1024x1024",
                enum=["1024x1024", "768x1024", "1024x768"],
            ),
            ToolParameter(
                name="count",
                type=ToolParameterType.INTEGER,
                description="生成图片数量。",
                required=False,
                default=1,
                min_value=1,
            ),
            ToolParameter(
                name="style_hint",
                type=ToolParameterType.STRING,
                description="补充风格提示词。",
                required=False,
                default="",
            ),
        ]

    def _resolve_agent_context(self) -> tuple[str, str]:
        """解析当前请求上下文中的 agent_id 与 session_id。"""

        context = get_current_context()
        if context is None:
            return "main-agent", ""
        return context.agent_id or "main-agent", context.session_id or ""

    async def _persist_assets(
        self,
        *,
        provider_urls: list[str],
        agent_id: str,
        session_id: str,
        prompt: str,
        size: str,
    ) -> list[dict[str, str]]:
        """将 provider 图片下载并落盘到项目资产空间。"""

        assets: list[dict[str, str]] = []
        for provider_url in provider_urls:
            image_bytes, mime_type = await self._client.download_image(provider_url)
            stored = await self._store.save_generated_image(
                agent_id=agent_id,
                session_id=session_id,
                prompt=prompt,
                model=self._config.model,
                size=size,
                image_bytes=image_bytes,
                mime_type=mime_type,
            )
            assets.append(
                {
                    "file_path": str(stored.file_path),
                    "relative_path": stored.relative_path,
                    "public_url": stored.public_url,
                    "mime_type": stored.mime_type,
                    "provider_asset_url": provider_url,
                }
            )
        return assets

    def _background_receipt(
        self,
        *,
        task_id: str,
        agent_id: str,
        session_id: str,
        prompt: str,
        size: str,
        count: int,
    ) -> ToolResult:
        """返回后台图片任务收据，由 runtime 在后续完成通知。"""

        lines = [
            "图片生成任务已提交，正在后台处理。",
            f"Task ID: {task_id}",
            f"Model: {self._config.model}",
            f"Size: {size}",
            f"Count: {count}",
            "完成后系统会自动把结果推送到当前会话。",
        ]
        return ToolResult.ok(
            "\n".join(lines),
            model=self._config.model,
            final_prompt=prompt,
            prompt=prompt,
            size=size,
            count=count,
            agent_id=agent_id,
            session_id=session_id,
            assets=[],
            is_background=True,
            background_task_kind="image_generation",
            background_task_title="图片生成任务",
            modelscope_task_id=task_id,
        )

    async def execute(
        self,
        **params: Any,
    ) -> ToolResult:
        """执行文生图。"""

        prompt = params.get("prompt")
        size = params.get("size")
        count = params.get("count")
        style_hint = params.get("style_hint")

        if not isinstance(prompt, str) or not prompt.strip():
            return ToolResult.error_result("prompt is required")
        if size is not None and not isinstance(size, str):
            return ToolResult.error_result("size must be a string")
        if count is not None and not isinstance(count, int):
            return ToolResult.error_result("count must be an integer")
        if style_hint is not None and not isinstance(style_hint, str):
            return ToolResult.error_result("style_hint must be a string")

        if not self._config.enabled:
            return ToolResult.error_result("Image generation is disabled in configuration")

        final_count = count or self._config.default_count
        if final_count > self._max_count:
            return ToolResult.error_result(f"Requested count exceeds max_count={self._max_count}")

        final_size = size or self._config.default_size
        final_prompt = prompt if not style_hint else f"{prompt}\n风格提示：{style_hint}"
        agent_id, session_id = self._resolve_agent_context()

        try:
            submission = await self._client.submit_generation(
                prompt=final_prompt,
                size=final_size,
                count=final_count,
            )
            if submission.task_id and not submission.provider_urls:
                return self._background_receipt(
                    task_id=submission.task_id,
                    agent_id=agent_id,
                    session_id=session_id,
                    prompt=final_prompt,
                    size=final_size,
                    count=final_count,
                )

            assets = await self._persist_assets(
                provider_urls=list(submission.provider_urls),
                agent_id=agent_id,
                session_id=session_id,
                prompt=final_prompt,
                size=final_size,
            )
        except Exception as exc:
            return ToolResult.error_result(f"Image generation failed: {exc}")

        lines = [
            f"已生成 {len(assets)} 张图片",
            f"Model: {self._config.model}",
            f"Size: {final_size}",
        ]
        for index, asset in enumerate(assets, start=1):
            lines.append(f"Asset {index}:")
            lines.append(f"![生成图片]({asset['public_url']})")
            lines.append(f"- URL: {asset['public_url']}")
            lines.append(f"- Path: {asset['file_path']}")

        return ToolResult.ok(
            "\n".join(lines),
            model=self._config.model,
            final_prompt=final_prompt,
            size=final_size,
            count=len(assets),
            agent_id=agent_id,
            assets=assets,
        )
