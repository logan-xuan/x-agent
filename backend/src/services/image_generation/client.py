"""ModelScope 文生图客户端。"""

from __future__ import annotations

import asyncio

import httpx

from ...config.models import ImageGenerationConfig


class ModelScopeImageClient:
    """封装 ModelScope 文生图请求与图片下载。"""

    def __init__(self, config: ImageGenerationConfig) -> None:
        self._config = config
        self._http = httpx.AsyncClient(timeout=config.timeout)

    def _build_request(self, *, prompt: str, size: str, count: int) -> httpx.Request:
        """构造文生图请求。"""

        payload = {
            "model": self._config.model,
            "prompt": prompt,
            "size": size,
            "n": count,
        }
        return self._http.build_request(
            "POST",
            str(self._config.endpoint),
            headers={
                "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
                "Content-Type": "application/json",
                "X-ModelScope-Async-Mode": "true",
            },
            json=payload,
        )

    def _extract_image_urls(self, payload: dict) -> list[str]:
        """从响应中提取图片 URL 列表。"""

        items = payload.get("data") or payload.get("images") or payload.get("output_images") or []
        urls: list[str] = []
        for item in items:
            if isinstance(item, dict) and item.get("url"):
                urls.append(str(item["url"]))
            elif isinstance(item, str):
                urls.append(item)
        return urls

    async def generate(self, *, prompt: str, size: str, count: int) -> list[str]:
        """调用 ModelScope 文生图接口。"""

        request = self._build_request(prompt=prompt, size=size, count=count)
        response = await self._http.send(request)
        response.raise_for_status()
        payload = response.json()
        urls = self._extract_image_urls(payload)
        if not urls:
            task_id = str(payload.get("task_id") or "").strip()
            if not task_id:
                raise ValueError("ModelScope returned no image URLs")
            urls = await self._fetch_task_result(task_id)
        return urls

    async def download_image(self, url: str) -> tuple[bytes, str]:
        """下载生成后的图片内容。"""

        response = await self._http.get(url, timeout=self._config.download_timeout)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "image/png")

    async def _fetch_task_result(self, task_id: str) -> list[str]:
        """查询异步任务结果，直到拿到图片 URL。"""

        for _ in range(30):
            response = await self._http.get(
                f"https://api-inference.modelscope.cn/v1/tasks/{task_id}",
                headers={
                    "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
                    "X-ModelScope-Task-Type": "image_generation",
                },
            )
            response.raise_for_status()
            payload = response.json()
            urls = self._extract_image_urls(payload)
            if urls:
                return urls

            task_status = str(payload.get("task_status") or "").upper()
            if task_status not in {"", "PENDING", "RUNNING", "PROCESSING", "SUCCEED"}:
                raise ValueError(f"ModelScope task failed with status: {task_status}")
            await asyncio.sleep(1)

        raise TimeoutError(f"Timed out waiting for ModelScope task {task_id}")
