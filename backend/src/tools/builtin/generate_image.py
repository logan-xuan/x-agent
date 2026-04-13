"""内置文生图工具。"""

from __future__ import annotations

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

    async def execute(
        self,
        prompt: str,
        size: str | None = None,
        count: int | None = None,
        style_hint: str | None = None,
    ) -> ToolResult:
        """执行文生图。"""

        if not self._config.enabled:
            return ToolResult.error_result("Image generation is disabled in configuration")

        final_count = count or self._config.default_count
        if final_count > self._max_count:
            return ToolResult.error_result(f"Requested count exceeds max_count={self._max_count}")

        final_size = size or self._config.default_size
        final_prompt = prompt if not style_hint else f"{prompt}\n风格提示：{style_hint}"
        agent_id, session_id = self._resolve_agent_context()

        try:
            provider_urls = await self._client.generate(
                prompt=final_prompt,
                size=final_size,
                count=final_count,
            )
            assets: list[dict[str, str]] = []
            for provider_url in provider_urls:
                image_bytes, mime_type = await self._client.download_image(provider_url)
                stored = await self._store.save_generated_image(
                    agent_id=agent_id,
                    session_id=session_id,
                    prompt=final_prompt,
                    model=self._config.model,
                    size=final_size,
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
