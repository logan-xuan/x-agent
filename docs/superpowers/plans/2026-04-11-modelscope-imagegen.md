# ModelScope Image Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a built-in `imagegen` skill and `generate_image` tool that call ModelScope text-to-image, store images under a project asset space grouped by `agent_id`, and return public asset URLs.

**Architecture:** Keep user intent handling in a system skill and move all network, download, persistence, and URL generation logic into backend services plus one built-in tool. Use the existing config system for `image_generation`, the existing SQLite main database for asset metadata, and a small read-only asset router for public file serving.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy async, pytest, httpx, existing built-in tool framework

---

## File Map

### Config

- Modify: `backend/src/config/models.py`
  - Add `ImageGenerationConfig`
  - Add `image_generation` to root `Config`
- Modify: `backend/src/config/validator.py`
  - Validate enabled/disabled state, placeholder token, and URL/path shape
- Test: `backend/tests/unit/test_image_generation_config.py`
  - Config parsing and validation coverage

### Persistence and Services

- Create: `backend/src/models/generated_asset.py`
  - SQLAlchemy model for generated image metadata
- Modify: `backend/src/models/__init__.py`
  - Register the new model for `Base.metadata.create_all`
- Create: `backend/src/services/image_generation/__init__.py`
  - Public exports
- Create: `backend/src/services/image_generation/client.py`
  - ModelScope API client
- Create: `backend/src/services/image_generation/asset_store.py`
  - Asset path resolution, file persistence, DB metadata write, public URL generation
- Test: `backend/tests/unit/services/test_image_generation_client.py`
  - API payload and response parsing coverage
- Test: `backend/tests/unit/services/test_image_asset_store.py`
  - Safe path resolution and metadata persistence coverage

### Public Asset API

- Create: `backend/src/api/v1/assets.py`
  - Public read-only asset route
- Modify: `backend/src/main.py`
  - Include the new router
- Test: `backend/tests/unit/test_assets_api.py`
  - Public URL serving and path traversal protection

### Tooling and Skill

- Create: `backend/src/tools/builtin/generate_image.py`
  - Built-in text-to-image tool
- Modify: `backend/src/tools/builtin/__init__.py`
  - Register `GenerateImageTool`
- Modify: `backend/src/tools/semantic_mapping.py`
  - Add `generate_image` as a built-in tool for plan/tool metadata consistency
- Create: `backend/src/skills/imagegen/SKILL.md`
  - Skill instructions for prompt shaping and tool usage
- Test: `backend/tests/unit/tools/test_generate_image_tool.py`
  - Tool contract and error mapping coverage
- Modify: `backend/tests/unit/test_skill_system.py`
  - System skill discovery coverage

---

### Task 1: Add image generation config schema and validator coverage

**Files:**
- Create: `backend/tests/unit/test_image_generation_config.py`
- Modify: `backend/src/config/models.py`
- Modify: `backend/src/config/validator.py`

- [ ] **Step 1: Write the failing config parsing test**

Create `backend/tests/unit/test_image_generation_config.py` with a parsing-level assertion that currently fails because `Config` has no `image_generation` field:

```python
"""Image generation configuration tests."""

from src.config.models import Config, ModelConfig


def _base_model() -> ModelConfig:
    return ModelConfig(
        name="primary",
        provider="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test-primary-key-1234567890",
        model_id="gpt-5.4",
        is_primary=True,
    )


def test_config_exposes_image_generation_section() -> None:
    config = Config(
        models=[_base_model()],
        image_generation={
            "enabled": True,
            "provider": "modelscope",
            "endpoint": "https://api-inference.modelscope.cn/v1/images/generations",
            "api_key": "ms-test-token",
            "model": "Tongyi-MAI/Z-Image-Turbo",
            "assets_dir": "backend/assets/generated-images",
            "public_base_url": "http://localhost:8888/api/v1/assets/generated-images",
        },
    )

    dumped = config.model_dump()

    assert "image_generation" in dumped
    assert config.image_generation.enabled is True
    assert config.image_generation.model == "Tongyi-MAI/Z-Image-Turbo"
    assert config.image_generation.default_size == "1024x1024"
    assert config.image_generation.default_count == 1
```

- [ ] **Step 2: Write the failing validator coverage**

Append two validator tests in the same file:

```python
from src.config.validator import validate_config


def test_config_validator_rejects_enabled_image_generation_without_api_key() -> None:
    config = Config(
        models=[_base_model()],
        image_generation={
            "enabled": True,
            "provider": "modelscope",
            "endpoint": "https://api-inference.modelscope.cn/v1/images/generations",
            "api_key": "",
            "model": "Tongyi-MAI/Z-Image-Turbo",
            "assets_dir": "backend/assets/generated-images",
            "public_base_url": "http://localhost:8888/api/v1/assets/generated-images",
        },
    )

    result = validate_config(config)

    assert result.is_valid is False
    assert any(issue.field == "image_generation.api_key" for issue in result.errors)


def test_config_validator_rejects_placeholder_modelscope_token() -> None:
    config = Config(
        models=[_base_model()],
        image_generation={
            "enabled": True,
            "provider": "modelscope",
            "endpoint": "https://api-inference.modelscope.cn/v1/images/generations",
            "api_key": "ms-your-modelscope-token",
            "model": "Tongyi-MAI/Z-Image-Turbo",
            "assets_dir": "backend/assets/generated-images",
            "public_base_url": "http://localhost:8888/api/v1/assets/generated-images",
        },
    )

    result = validate_config(config)

    assert result.is_valid is False
    assert any("placeholder" in issue.message.lower() for issue in result.errors)
```

- [ ] **Step 3: Run the config tests to verify they fail**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/test_image_generation_config.py -v --no-cov
```

Expected: FAIL because `Config` does not expose `image_generation` yet and the validator has no `image_generation.*` checks.

- [ ] **Step 4: Implement the minimal config schema**

Update `backend/src/config/models.py` with a focused config model and root field:

```python
class ImageGenerationConfig(BaseModel):
    """Text-to-image generation configuration."""

    enabled: bool = Field(default=False, description="Whether image generation is enabled")
    provider: Literal["modelscope"] = Field(default="modelscope")
    endpoint: HttpUrl = Field(
        default="https://api-inference.modelscope.cn/v1/images/generations",
        description="ModelScope image generation endpoint",
    )
    api_key: SecretStr = Field(default=SecretStr(""), description="ModelScope API token")
    model: str = Field(default="Tongyi-MAI/Z-Image-Turbo")
    timeout: int = Field(default=180, ge=10, le=600)
    download_timeout: int = Field(default=180, ge=10, le=600)
    assets_dir: str = Field(default="backend/assets/generated-images")
    public_base_url: HttpUrl = Field(
        default="http://localhost:8888/api/v1/assets/generated-images"
    )
    default_size: Literal["1024x1024", "768x1024", "1024x768"] = Field(
        default="1024x1024"
    )
    default_count: int = Field(default=1, ge=1, le=4)
    max_count: int = Field(default=4, ge=1, le=8)

    @model_validator(mode="after")
    def validate_enabled_requirements(self) -> "ImageGenerationConfig":
        if self.enabled and not self.api_key.get_secret_value().strip():
            raise ValueError("api_key is required when image generation is enabled")
        if self.default_count > self.max_count:
            raise ValueError("default_count cannot exceed max_count")
        return self


class Config(BaseModel):
    ...
    image_generation: ImageGenerationConfig = Field(
        default_factory=ImageGenerationConfig,
        description="ModelScope image generation config",
    )
```

- [ ] **Step 5: Implement the minimal validator checks**

Update `backend/src/config/validator.py` to validate the new section:

```python
class ConfigValidator:
    ...

    def validate(self, config: Config) -> ValidationResult:
        result = ValidationResult(is_valid=True)
        self._validate_models(config, result)
        self._validate_server(config, result)
        self._validate_image_generation(config, result)
        result.is_valid = len(result.errors) == 0
        return result

    def _validate_image_generation(self, config: Config, result: ValidationResult) -> None:
        image_cfg = config.image_generation
        if not image_cfg.enabled:
            return

        token = image_cfg.api_key.get_secret_value()
        if not token.strip():
            result.issues.append(
                ValidationIssue(
                    field="image_generation.api_key",
                    message="Image generation API key is required when enabled",
                    severity=ValidationSeverity.ERROR,
                    suggestion="Set image_generation.api_key to a valid ModelScope token",
                )
            )
        if token == "ms-your-modelscope-token":
            result.issues.append(
                ValidationIssue(
                    field="image_generation.api_key",
                    message="Image generation API key appears to be a placeholder",
                    severity=ValidationSeverity.ERROR,
                    suggestion="Replace with your actual ModelScope token",
                )
            )
```

- [ ] **Step 6: Re-run the config tests to verify they pass**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/test_image_generation_config.py tests/unit/test_config_validator.py -v --no-cov
```

Expected: PASS.

- [ ] **Step 7: Commit the config work**

```bash
git add backend/src/config/models.py backend/src/config/validator.py backend/tests/unit/test_image_generation_config.py
git commit -m "feat(config): add image generation settings"
```

---

### Task 2: Add generated image metadata model and asset store

**Files:**
- Create: `backend/src/models/generated_asset.py`
- Modify: `backend/src/models/__init__.py`
- Create: `backend/src/services/image_generation/__init__.py`
- Create: `backend/src/services/image_generation/asset_store.py`
- Create: `backend/tests/unit/services/test_image_asset_store.py`

- [ ] **Step 1: Write the failing asset store tests**

Create `backend/tests/unit/services/test_image_asset_store.py`:

```python
"""Tests for generated image asset persistence."""

from pathlib import Path

import pytest

from src.config.models import ImageGenerationConfig
from src.services.image_generation.asset_store import ImageAssetStore
from src.services.storage import StorageService


@pytest.mark.asyncio
async def test_image_asset_store_persists_image_bytes_and_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    storage = StorageService(f"sqlite+aiosqlite:///{db_path}")
    await storage.initialize()

    config = ImageGenerationConfig(
        enabled=True,
        api_key="ms-test-token",
        assets_dir=str(tmp_path / "generated-images"),
        public_base_url="http://localhost:8888/api/v1/assets/generated-images",
    )
    store = ImageAssetStore(config=config, storage=storage)

    stored = await store.save_generated_image(
        agent_id="main-agent",
        session_id="session-1",
        prompt="画一只猫",
        model="Tongyi-MAI/Z-Image-Turbo",
        size="1024x1024",
        image_bytes=b"fake-png-bytes",
        mime_type="image/png",
    )

    assert stored.relative_path.startswith("main-agent/")
    assert stored.file_path.exists() is True
    assert stored.public_url.startswith("http://localhost:8888/api/v1/assets/generated-images/main-agent/")


@pytest.mark.asyncio
async def test_image_asset_store_rejects_agent_id_path_traversal(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    storage = StorageService(f"sqlite+aiosqlite:///{db_path}")
    await storage.initialize()

    config = ImageGenerationConfig(
        enabled=True,
        api_key="ms-test-token",
        assets_dir=str(tmp_path / "generated-images"),
        public_base_url="http://localhost:8888/api/v1/assets/generated-images",
    )
    store = ImageAssetStore(config=config, storage=storage)

    with pytest.raises(ValueError, match="agent_id"):
        await store.save_generated_image(
            agent_id="../escape",
            session_id="session-1",
            prompt="bad",
            model="Tongyi-MAI/Z-Image-Turbo",
            size="1024x1024",
            image_bytes=b"fake-png-bytes",
            mime_type="image/png",
        )
```

- [ ] **Step 2: Run the asset store tests to verify they fail**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/services/test_image_asset_store.py -v --no-cov
```

Expected: FAIL because neither `generated_asset.py` nor `ImageAssetStore` exists.

- [ ] **Step 3: Create the SQLAlchemy metadata model**

Create `backend/src/models/generated_asset.py`:

```python
"""Generated image asset metadata model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class GeneratedImageAsset(Base):
    """Metadata for a generated image stored in the project asset space."""

    __tablename__ = "generated_image_assets"

    asset_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(255))
    size: Mapped[str] = mapped_column(String(32))
    mime_type: Mapped[str] = mapped_column(String(64))
    relative_path: Mapped[str] = mapped_column(String(512), unique=True)
    public_url: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
```

Update `backend/src/models/__init__.py`:

```python
from .generated_asset import GeneratedImageAsset

__all__ = [
    "Message",
    "Session",
    "LLMRequestStat",
    "CompressionEvent",
    "RuntimeRecord",
    "SkillMetadata",
    "GeneratedImageAsset",
]
```

- [ ] **Step 4: Create the asset store service**

Create `backend/src/services/image_generation/asset_store.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from ...models.generated_asset import GeneratedImageAsset
from ...services.storage import StorageService
from ...config.models import ImageGenerationConfig


@dataclass(slots=True)
class StoredImageAsset:
    asset_id: str
    file_path: Path
    relative_path: str
    public_url: str
    mime_type: str


class ImageAssetStore:
    def __init__(self, config: ImageGenerationConfig, storage: StorageService) -> None:
        self._config = config
        self._storage = storage
        self._root = Path(config.assets_dir).expanduser().resolve()

    def _sanitize_agent_id(self, agent_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", agent_id):
            raise ValueError("agent_id contains unsupported characters")
        return agent_id

    async def save_generated_image(
        self,
        *,
        agent_id: str,
        session_id: str,
        prompt: str,
        model: str,
        size: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> StoredImageAsset:
        safe_agent_id = self._sanitize_agent_id(agent_id)
        date_part = datetime.utcnow().strftime("%Y-%m-%d")
        asset_id = uuid4().hex[:8]
        extension = ".png" if mime_type == "image/png" else ".jpg"
        relative_path = f"{safe_agent_id}/{date_part}/img_{asset_id}{extension}"
        file_path = (self._root / relative_path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(image_bytes)

        public_url = f"{str(self._config.public_base_url).rstrip('/')}/{relative_path}"

        async with self._storage.session() as db:
            db.add(
                GeneratedImageAsset(
                    asset_id=asset_id,
                    agent_id=safe_agent_id,
                    session_id=session_id,
                    prompt=prompt,
                    model=model,
                    size=size,
                    mime_type=mime_type,
                    relative_path=relative_path,
                    public_url=public_url,
                )
            )

        return StoredImageAsset(
            asset_id=asset_id,
            file_path=file_path,
            relative_path=relative_path,
            public_url=public_url,
            mime_type=mime_type,
        )
```

Also create `backend/src/services/image_generation/__init__.py`:

```python
from .asset_store import ImageAssetStore, StoredImageAsset

__all__ = ["ImageAssetStore", "StoredImageAsset"]
```

- [ ] **Step 5: Re-run the asset store tests to verify they pass**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/services/test_image_asset_store.py -v --no-cov
```

Expected: PASS.

- [ ] **Step 6: Commit the persistence work**

```bash
git add backend/src/models/generated_asset.py backend/src/models/__init__.py backend/src/services/image_generation/__init__.py backend/src/services/image_generation/asset_store.py backend/tests/unit/services/test_image_asset_store.py
git commit -m "feat(image): add generated asset storage"
```

---

### Task 3: Add public generated-image asset route

**Files:**
- Create: `backend/src/api/v1/assets.py`
- Modify: `backend/src/main.py`
- Create: `backend/tests/unit/test_assets_api.py`

- [ ] **Step 1: Write the failing asset API tests**

Create `backend/tests/unit/test_assets_api.py`:

```python
"""Tests for generated image public asset endpoints."""

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.main import app


def test_assets_api_serves_generated_image(monkeypatch, tmp_path: Path) -> None:
    asset_root = tmp_path / "generated-images"
    asset_file = asset_root / "main-agent" / "2026-04-11" / "img_demo.png"
    asset_file.parent.mkdir(parents=True)
    asset_file.write_bytes(b"fake-image")

    image_cfg = SimpleNamespace(assets_dir=str(asset_root), enabled=True)
    config = SimpleNamespace(image_generation=image_cfg)
    monkeypatch.setattr("src.api.v1.assets.get_config", lambda: config)

    client = TestClient(app)
    response = client.get("/api/v1/assets/generated-images/main-agent/2026-04-11/img_demo.png")

    assert response.status_code == 200
    assert response.content == b"fake-image"


def test_assets_api_blocks_path_traversal(monkeypatch, tmp_path: Path) -> None:
    asset_root = tmp_path / "generated-images"
    image_cfg = SimpleNamespace(assets_dir=str(asset_root), enabled=True)
    config = SimpleNamespace(image_generation=image_cfg)
    monkeypatch.setattr("src.api.v1.assets.get_config", lambda: config)

    client = TestClient(app)
    response = client.get("/api/v1/assets/generated-images/../secrets.txt")

    assert response.status_code in {400, 404}
```

- [ ] **Step 2: Run the asset API tests to verify they fail**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/test_assets_api.py -v --no-cov
```

Expected: FAIL because `src.api.v1.assets` does not exist and `main.py` does not include the router.

- [ ] **Step 3: Implement the read-only asset router**

Create `backend/src/api/v1/assets.py`:

```python
"""Public asset routes for generated images."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...config.manager import get_config

router = APIRouter(prefix="/assets", tags=["assets"])


def _resolve_asset_root() -> Path:
    config = get_config()
    return Path(config.image_generation.assets_dir).expanduser().resolve()


def _resolve_public_asset_path(agent_id: str, date: str, filename: str) -> Path:
    root = _resolve_asset_root()
    candidate = (root / agent_id / date / filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset path") from exc
    return candidate


@router.get("/generated-images/{agent_id}/{date}/{filename}")
async def get_generated_image(agent_id: str, date: str, filename: str) -> FileResponse:
    asset_path = _resolve_public_asset_path(agent_id, date, filename)
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(asset_path)
```

Update `backend/src/main.py` route imports:

```python
from .api.v1.assets import router as assets_router
...
app.include_router(assets_router, prefix="/api/v1", tags=["Assets"])
```

- [ ] **Step 4: Re-run the asset API tests to verify they pass**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/test_assets_api.py -v --no-cov
```

Expected: PASS.

- [ ] **Step 5: Commit the asset API work**

```bash
git add backend/src/api/v1/assets.py backend/src/main.py backend/tests/unit/test_assets_api.py
git commit -m "feat(api): expose generated image assets"
```

---

### Task 4: Add ModelScope client and generate_image built-in tool

**Files:**
- Create: `backend/src/services/image_generation/client.py`
- Create: `backend/src/tools/builtin/generate_image.py`
- Modify: `backend/src/tools/builtin/__init__.py`
- Modify: `backend/src/tools/semantic_mapping.py`
- Create: `backend/tests/unit/services/test_image_generation_client.py`
- Create: `backend/tests/unit/tools/test_generate_image_tool.py`

- [ ] **Step 1: Write the failing ModelScope client tests**

Create `backend/tests/unit/services/test_image_generation_client.py`:

```python
"""Tests for ModelScope image generation client."""

import json

import httpx
import pytest

from src.config.models import ImageGenerationConfig
from src.services.image_generation.client import ModelScopeImageClient


@pytest.mark.asyncio
async def test_modelscope_client_builds_generation_request() -> None:
    config = ImageGenerationConfig(enabled=True, api_key="ms-test-token")
    client = ModelScopeImageClient(config=config)

    request = client._build_request(prompt="a cat", size="1024x1024", count=2)
    payload = json.loads(request.content.decode("utf-8"))

    assert str(request.url) == "https://api-inference.modelscope.cn/v1/images/generations"
    assert request.headers["Authorization"] == "Bearer ms-test-token"
    assert payload["model"] == "Tongyi-MAI/Z-Image-Turbo"
    assert payload["prompt"] == "a cat"
    assert payload["size"] == "1024x1024"
    assert payload["n"] == 2


def test_modelscope_client_extracts_urls_from_data_items() -> None:
    config = ImageGenerationConfig(enabled=True, api_key="ms-test-token")
    client = ModelScopeImageClient(config=config)

    urls = client._extract_image_urls(
        {"data": [{"url": "https://example.com/a.png"}, {"url": "https://example.com/b.png"}]}
    )

    assert urls == ["https://example.com/a.png", "https://example.com/b.png"]
```

- [ ] **Step 2: Write the failing tool tests**

Create `backend/tests/unit/tools/test_generate_image_tool.py`:

```python
"""Tests for generate_image tool."""

from unittest.mock import AsyncMock

import pytest

from src.tools.builtin.generate_image import GenerateImageTool


@pytest.mark.asyncio
async def test_generate_image_tool_returns_public_asset_urls(monkeypatch) -> None:
    tool = GenerateImageTool()
    monkeypatch.setattr(tool, "_resolve_agent_context", lambda: ("main-agent", "session-1"))
    tool._client = AsyncMock()
    tool._store = AsyncMock()
    tool._client.generate = AsyncMock(return_value=["https://provider.example.com/demo.png"])
    tool._client.download_image = AsyncMock(return_value=(b"fake-png", "image/png"))
    tool._store.save_generated_image = AsyncMock(
        return_value=type(
            "StoredImage",
            (),
            {
                "asset_id": "demo",
                "file_path": "/tmp/generated-images/main-agent/2026-04-11/img_demo.png",
                "relative_path": "main-agent/2026-04-11/img_demo.png",
                "public_url": "http://localhost:8888/api/v1/assets/generated-images/main-agent/2026-04-11/img_demo.png",
                "mime_type": "image/png",
            },
        )()
    )

    result = await tool.execute(prompt="画一只猫", size="1024x1024", count=1)

    assert result.success is True
    assert "http://localhost:8888/api/v1/assets/generated-images/main-agent/" in result.output
    assert result.metadata["assets"][0]["public_url"].endswith("img_demo.png")


@pytest.mark.asyncio
async def test_generate_image_tool_rejects_count_above_config_limit(monkeypatch) -> None:
    tool = GenerateImageTool()
    monkeypatch.setattr(tool, "_max_count", 2)

    result = await tool.execute(prompt="画一只猫", count=3)

    assert result.success is False
    assert "max_count" in result.error
```

- [ ] **Step 3: Run the client and tool tests to verify they fail**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/services/test_image_generation_client.py tests/unit/tools/test_generate_image_tool.py -v --no-cov
```

Expected: FAIL because neither the client nor the tool exists.

- [ ] **Step 4: Implement the ModelScope client**

Create `backend/src/services/image_generation/client.py`:

```python
from __future__ import annotations

import httpx

from ...config.models import ImageGenerationConfig


class ModelScopeImageClient:
    def __init__(self, config: ImageGenerationConfig) -> None:
        self._config = config
        self._http = httpx.AsyncClient(timeout=config.timeout)

    def _build_request(self, *, prompt: str, size: str, count: int) -> httpx.Request:
        payload = {
            "model": self._config.model,
            "prompt": prompt,
            "size": size,
            "n": count,
        }
        return self._http.build_request(
            "POST",
            str(self._config.endpoint),
            headers={"Authorization": f"Bearer {self._config.api_key.get_secret_value()}"},
            json=payload,
        )

    def _extract_image_urls(self, payload: dict) -> list[str]:
        items = payload.get("data") or payload.get("images") or []
        urls: list[str] = []
        for item in items:
            if isinstance(item, dict) and item.get("url"):
                urls.append(str(item["url"]))
            elif isinstance(item, str):
                urls.append(item)
        return urls

    async def generate(self, *, prompt: str, size: str, count: int) -> list[str]:
        request = self._build_request(prompt=prompt, size=size, count=count)
        response = await self._http.send(request)
        response.raise_for_status()
        urls = self._extract_image_urls(response.json())
        if not urls:
            raise ValueError("ModelScope returned no image URLs")
        return urls

    async def download_image(self, url: str) -> tuple[bytes, str]:
        response = await self._http.get(url, timeout=self._config.download_timeout)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "image/png")
```

- [ ] **Step 5: Implement the built-in tool and register it**

Create `backend/src/tools/builtin/generate_image.py`:

```python
from __future__ import annotations

from ...config.manager import get_config
from ...conversation.context import get_current_context
from ...services.image_generation.asset_store import ImageAssetStore
from ...services.image_generation.client import ModelScopeImageClient
from ...services.storage import get_storage_service
from ..base import BaseTool, ToolParameter, ToolParameterType, ToolResult


class GenerateImageTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        image_cfg = get_config().image_generation
        self._config = image_cfg
        self._client = ModelScopeImageClient(config=image_cfg)
        self._store = ImageAssetStore(config=image_cfg, storage=get_storage_service())
        self._max_count = image_cfg.max_count

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return "Generate images from natural language using ModelScope and return public asset URLs."

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="prompt", type=ToolParameterType.STRING, description="Image prompt"),
            ToolParameter(name="size", type=ToolParameterType.STRING, required=False, default="1024x1024"),
            ToolParameter(name="count", type=ToolParameterType.INTEGER, required=False, default=1),
            ToolParameter(name="style_hint", type=ToolParameterType.STRING, required=False, default=""),
        ]

    def _resolve_agent_context(self) -> tuple[str, str]:
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
        if not self._config.enabled:
            return ToolResult.error_result("Image generation is disabled in configuration")

        final_count = count or self._config.default_count
        if final_count > self._max_count:
            return ToolResult.error_result(f"Requested count exceeds max_count={self._max_count}")

        final_size = size or self._config.default_size
        final_prompt = prompt if not style_hint else f"{prompt}，风格：{style_hint}"
        agent_id, session_id = self._resolve_agent_context()
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

        lines = [f"已生成 {len(assets)} 张图片", f"Model: {self._config.model}", f"Size: {final_size}"]
        for index, asset in enumerate(assets, start=1):
            lines.append(f"Asset {index}:")
            lines.append(f"- URL: {asset['public_url']}")
            lines.append(f"- Path: {asset['file_path']}")
        return ToolResult.ok("\n".join(lines), model=self._config.model, final_prompt=final_prompt, size=final_size, count=len(assets), agent_id=agent_id, assets=assets)
```

Update `backend/src/tools/builtin/__init__.py`:

```python
from .generate_image import GenerateImageTool

__all__ = [
    ...
    "GenerateImageTool",
    "get_builtin_tools",
]

def get_builtin_tools() -> list:
    terminal_tool = RunInTerminalTool()
    return [
        ...
        FetchWebContentTool(),
        GenerateImageTool(),
        MemorySearchTool(),
        ...
    ]
```

Update `backend/src/tools/semantic_mapping.py`:

```python
"generate_image": {
    "type": "builtin_tool",
    "module": "src.tools.builtin.generate_image",
    "description": "根据自然语言描述生成图片并返回公开资产地址",
    "can_call_directly": True,
},
```

- [ ] **Step 6: Re-run the client and tool tests to verify they pass**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/services/test_image_generation_client.py tests/unit/tools/test_generate_image_tool.py -v --no-cov
```

Expected: PASS.

- [ ] **Step 7: Commit the tooling work**

```bash
git add backend/src/services/image_generation/client.py backend/src/tools/builtin/generate_image.py backend/src/tools/builtin/__init__.py backend/src/tools/semantic_mapping.py backend/tests/unit/services/test_image_generation_client.py backend/tests/unit/tools/test_generate_image_tool.py
git commit -m "feat(image): add generate_image builtin tool"
```

---

### Task 5: Add the imagegen system skill and discovery coverage

**Files:**
- Create: `backend/src/skills/imagegen/SKILL.md`
- Modify: `backend/tests/unit/test_skill_system.py`

- [ ] **Step 1: Write the failing discovery test**

Append to `backend/tests/unit/test_skill_system.py`:

```python
def test_discover_imagegen_system_skill():
    backend_dir = Path(__file__).parent.parent.parent
    registry = SkillRegistry(backend_dir)

    imagegen = registry.get_skill_metadata("imagegen")

    assert imagegen is not None
    assert imagegen.name == "imagegen"
    assert imagegen.allowed_tools == ["generate_image", "read_file"]
```

- [ ] **Step 2: Run the skill test to verify it fails**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/test_skill_system.py -k imagegen -v --no-cov
```

Expected: FAIL because `backend/src/skills/imagegen/SKILL.md` does not exist.

- [ ] **Step 3: Create the system skill**

Create `backend/src/skills/imagegen/SKILL.md`:

```markdown
---
name: imagegen
description: "根据用户自然语言描述调用内置生图工具生成图片，并返回可访问地址"
keywords:
  - 生图
  - 画图
  - 生成图片
  - 海报
  - 插画
  - text to image
auto-trigger: true
priority: 1
allowed_tools:
  - generate_image
  - read_file
---

# Image Generation Guide

## Overview

当用户想要“画一张图”“生成海报”“根据描述出图”时，优先使用 `generate_image`。

## Required behavior

1. 先将用户描述整理成适合文生图的 prompt。
2. 如果用户没有明确说明尺寸和数量，直接使用工具默认值，不额外追问。
3. 不要自己写脚本访问第三方 API。
4. 只使用 `generate_image` 产出图片。
5. 如果用户要求图像编辑、局部重绘或图生图，说明当前能力仅支持文生图。
```

- [ ] **Step 4: Re-run the skill test to verify it passes**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/test_skill_system.py -k imagegen -v --no-cov
```

Expected: PASS.

- [ ] **Step 5: Commit the skill work**

```bash
git add backend/src/skills/imagegen/SKILL.md backend/tests/unit/test_skill_system.py
git commit -m "feat(skill): add image generation system skill"
```

---

### Task 6: Run focused verification and smoke checks

**Files:**
- Modify: `backend/src/config/models.py`
- Modify: `backend/src/config/validator.py`
- Modify: `backend/src/models/generated_asset.py`
- Modify: `backend/src/models/__init__.py`
- Modify: `backend/src/services/image_generation/asset_store.py`
- Modify: `backend/src/services/image_generation/client.py`
- Modify: `backend/src/api/v1/assets.py`
- Modify: `backend/src/main.py`
- Modify: `backend/src/tools/builtin/generate_image.py`
- Modify: `backend/src/tools/builtin/__init__.py`
- Modify: `backend/src/tools/semantic_mapping.py`
- Modify: `backend/src/skills/imagegen/SKILL.md`
- Test: `backend/tests/unit/test_image_generation_config.py`
- Test: `backend/tests/unit/services/test_image_asset_store.py`
- Test: `backend/tests/unit/services/test_image_generation_client.py`
- Test: `backend/tests/unit/tools/test_generate_image_tool.py`
- Test: `backend/tests/unit/test_assets_api.py`
- Test: `backend/tests/unit/test_skill_system.py`

- [ ] **Step 1: Run the full focused verification set**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/test_image_generation_config.py tests/unit/services/test_image_asset_store.py tests/unit/services/test_image_generation_client.py tests/unit/tools/test_generate_image_tool.py tests/unit/test_assets_api.py tests/unit/test_skill_system.py -v --no-cov
```

Expected: PASS.

- [ ] **Step 2: Run a tool registration regression**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && python - <<'PY'
from src.tools.builtin import get_builtin_tools
print(sorted(tool.name for tool in get_builtin_tools()))
PY
```

Expected: output includes `generate_image`.

- [ ] **Step 3: Run one API smoke check**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && python - <<'PY'
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)
response = client.get("/api/v1/assets/generated-images/main-agent/2099-01-01/missing.png")
print(response.status_code)
print(response.json())
PY
```

Expected: `404` with `{"detail": "Asset not found"}`.

- [ ] **Step 4: Confirm only intended files changed**

Run:

```bash
git status --short
```

Expected: only the config, model, service, API, tool, skill, and test files listed in this plan are changed for this feature.

- [ ] **Step 5: Create the final feature commit if per-task commits were skipped**

```bash
git add backend/src/config/models.py backend/src/config/validator.py backend/src/models/generated_asset.py backend/src/models/__init__.py backend/src/services/image_generation/__init__.py backend/src/services/image_generation/asset_store.py backend/src/services/image_generation/client.py backend/src/api/v1/assets.py backend/src/main.py backend/src/tools/builtin/generate_image.py backend/src/tools/builtin/__init__.py backend/src/tools/semantic_mapping.py backend/src/skills/imagegen/SKILL.md backend/tests/unit/test_image_generation_config.py backend/tests/unit/services/test_image_asset_store.py backend/tests/unit/services/test_image_generation_client.py backend/tests/unit/tools/test_generate_image_tool.py backend/tests/unit/test_assets_api.py backend/tests/unit/test_skill_system.py
git commit -m "feat(image): add modelscope image generation flow"
```

Use this final commit only if the earlier per-task commits were intentionally skipped.
