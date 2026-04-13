"""Public asset routes for generated images and audio."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...config.manager import get_config

router = APIRouter(prefix="/assets", tags=["assets"])


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_asset_root() -> Path:
    configured = Path(get_config().image_generation.assets_dir).expanduser()
    if configured.is_absolute():
        return configured.resolve()
    return (_repo_root() / configured).resolve()


def _resolve_public_asset_path(agent_id: str, date: str, filename: str) -> Path:
    root = _resolve_asset_root()
    candidate = (root / agent_id / date / filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset path") from exc
    return candidate


def _resolve_voice_asset_root() -> Path:
    configured = Path(get_config().voice.assets_dir).expanduser()
    if configured.is_absolute():
        return configured.resolve()
    return (_repo_root() / configured).resolve()


def _resolve_public_voice_asset_path(agent_id: str, date: str, filename: str) -> Path:
    root = _resolve_voice_asset_root()
    candidate = (root / agent_id / date / filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset path") from exc
    return candidate


@router.get("/generated-images/{agent_id}/{date}/{filename}")
async def get_generated_image(agent_id: str, date: str, filename: str) -> FileResponse:
    """Serve a generated image from the project asset space."""

    asset_path = _resolve_public_asset_path(agent_id, date, filename)
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(asset_path)


@router.get("/audio/{agent_id}/{date}/{filename}")
async def get_audio_asset(agent_id: str, date: str, filename: str) -> FileResponse:
    """Serve an audio asset from the project asset space."""

    asset_path = _resolve_public_voice_asset_path(agent_id, date, filename)
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(asset_path)
