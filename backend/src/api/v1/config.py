"""Configuration API endpoints."""

from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...config.manager import ConfigManager
from ...config.validator import validate_config
from ...config.voice_options import (
    DEFAULT_TTS_PROVIDER,
    build_default_tts_voice_catalog,
    is_valid_edge_voice,
)
from ...services.llm.circuit_breaker import circuit_breaker_manager
from ...utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class ConfigReloadResponse(BaseModel):
    """Response for config reload."""

    success: bool
    message: str
    models_count: int


class ConfigValidationResponse(BaseModel):
    """Response for config validation."""

    is_valid: bool
    errors: list[dict]
    warnings: list[dict]


class ProviderStatus(BaseModel):
    """Status of a single provider."""

    name: str
    model_id: str
    is_primary: bool
    is_healthy: bool
    circuit_state: str
    stats: dict


class ConfigStatusResponse(BaseModel):
    """Full configuration status."""

    providers: list[ProviderStatus]
    circuit_breakers: dict[str, dict]


class EditableModelConfig(BaseModel):
    """Editable model configuration."""

    name: str
    provider: str
    base_url: str
    api_key_masked: str  # Masked for display
    model_id: str
    is_primary: bool
    timeout: float
    max_retries: int
    priority: int


class EditableConfigResponse(BaseModel):
    """Editable configuration response."""

    models: list[EditableModelConfig]
    voice: "EditableVoiceConfig"
    config_path: str


class UpdateModelRequest(BaseModel):
    """Request to update a model configuration."""

    model_id: str | None = None
    api_key: str | None = None  # New API key (optional)
    is_primary: bool | None = None
    timeout: float | None = Field(default=None, ge=5.0, le=300.0)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    priority: int | None = Field(default=None, ge=0)


class UpdateModelResponse(BaseModel):
    """Response for model update."""

    success: bool
    message: str
    model: EditableModelConfig


class EditableVoiceOpenAIConfig(BaseModel):
    enabled: bool
    base_url: str
    api_key_masked: str
    timeout: int
    tts_model: str
    asr_model: str


class EditableVoiceWhisperCompatibleConfig(BaseModel):
    enabled: bool
    endpoint: str
    auth_token_masked: str
    timeout: int
    default_model: str
    response_format: str


class EditableVoiceFunASRBailianConfig(BaseModel):
    enabled: bool
    websocket_url: str
    api_key_masked: str
    timeout: int
    model: str
    sample_rate_hz: int
    chunk_interval_ms: int
    chunk_size_bytes: int
    language_hints: list[str]


class EditableVoiceGPTSoVITSConfig(BaseModel):
    enabled: bool
    endpoint: str
    timeout: int
    ref_audio_path: str
    ref_text: str
    text_lang: str
    prompt_lang: str


class EditableVoiceTTSVoiceConfig(BaseModel):
    default: str | None = None
    options: list[str]


class EditableVoiceTTSConfig(BaseModel):
    default_provider: str
    voices: dict[str, EditableVoiceTTSVoiceConfig]


class EditableVoiceRewriteConfig(BaseModel):
    mode: str


class EditableVoiceConfig(BaseModel):
    enabled: bool
    assets_dir: str
    public_base_url: str
    playback_base_url: str
    upload_max_bytes: int
    rewrite: EditableVoiceRewriteConfig
    tts: EditableVoiceTTSConfig
    openai: EditableVoiceOpenAIConfig
    whisper_compatible: EditableVoiceWhisperCompatibleConfig
    funasr_bailian: EditableVoiceFunASRBailianConfig
    gpt_sovits: EditableVoiceGPTSoVITSConfig


class UpdateVoiceOpenAIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout: int | None = Field(default=None, ge=10, le=600)
    tts_model: str | None = None
    asr_model: str | None = None


class UpdateVoiceWhisperCompatibleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    endpoint: str | None = None
    auth_token: str | None = None
    timeout: int | None = Field(default=None, ge=10, le=600)
    default_model: str | None = None
    response_format: str | None = None


class UpdateVoiceFunASRBailianRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    websocket_url: str | None = None
    api_key: str | None = None
    timeout: int | None = Field(default=None, ge=10, le=600)
    model: str | None = None
    sample_rate_hz: int | None = Field(default=None, ge=8000, le=48000)
    chunk_interval_ms: int | None = Field(default=None, ge=0, le=5000)
    chunk_size_bytes: int | None = Field(default=None, ge=256, le=262144)
    language_hints: list[str] | None = None


class UpdateVoiceGPTSoVITSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    endpoint: str | None = None
    timeout: int | None = Field(default=None, ge=10, le=600)
    ref_audio_path: str | None = None
    ref_text: str | None = None
    text_lang: str | None = None
    prompt_lang: str | None = None


class UpdateVoiceTTSVoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str | None = None


class UpdateVoiceTTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_provider: str | None = None
    voices: dict[str, UpdateVoiceTTSVoiceRequest] | None = None

    @field_validator("voices")
    @classmethod
    def validate_edge_voice_entries(
        cls, value: dict[str, UpdateVoiceTTSVoiceRequest] | None
    ) -> dict[str, UpdateVoiceTTSVoiceRequest] | None:
        if value is None:
            return value
        edge_entry = value.get("edge")
        if edge_entry is not None and edge_entry.default and not is_valid_edge_voice(edge_entry.default):
            raise ValueError("edge 默认音色必须是受支持的 Edge 音色")
        return value


class UpdateVoiceRewriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str | None = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in {"rules", "model"}:
            raise ValueError("rewrite.mode 仅支持 rules 或 model")
        return value


class UpdateVoiceConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    assets_dir: str | None = None
    public_base_url: str | None = None
    playback_base_url: str | None = None
    upload_max_bytes: int | None = Field(default=None, ge=1)
    rewrite: UpdateVoiceRewriteRequest | None = None
    tts: UpdateVoiceTTSRequest | None = None
    openai: UpdateVoiceOpenAIRequest | None = None
    whisper_compatible: UpdateVoiceWhisperCompatibleRequest | None = None
    funasr_bailian: UpdateVoiceFunASRBailianRequest | None = None
    gpt_sovits: UpdateVoiceGPTSoVITSRequest | None = None


class UpdateVoiceConfigResponse(BaseModel):
    success: bool
    message: str
    voice: EditableVoiceConfig


EditableConfigResponse.model_rebuild()


def _mask_secret(value: str) -> str:
    if not value:
        return "***"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _read_yaml_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml_config(config_path: Path, yaml_data: dict) -> None:
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _editable_voice_config(config) -> EditableVoiceConfig:
    voice = config.voice
    return EditableVoiceConfig(
        enabled=voice.enabled,
        assets_dir=voice.assets_dir,
        public_base_url=str(voice.public_base_url),
        playback_base_url=voice.playback_base_url,
        upload_max_bytes=voice.upload_max_bytes,
        rewrite=EditableVoiceRewriteConfig(
            mode=voice.rewrite.mode,
        ),
        tts=EditableVoiceTTSConfig(
            default_provider=voice.tts.default_provider,
            voices={
                provider: EditableVoiceTTSVoiceConfig(
                    default=entry.default,
                    options=list(entry.options),
                )
                for provider, entry in voice.tts.voices.items()
            },
        ),
        openai=EditableVoiceOpenAIConfig(
            enabled=voice.openai.enabled,
            base_url=str(voice.openai.base_url),
            api_key_masked=_mask_secret(voice.openai.api_key.get_secret_value()),
            timeout=voice.openai.timeout,
            tts_model=voice.openai.tts_model,
            asr_model=voice.openai.asr_model,
        ),
        whisper_compatible=EditableVoiceWhisperCompatibleConfig(
            enabled=voice.whisper_compatible.enabled,
            endpoint=str(voice.whisper_compatible.endpoint),
            auth_token_masked=_mask_secret(voice.whisper_compatible.auth_token.get_secret_value()),
            timeout=voice.whisper_compatible.timeout,
            default_model=voice.whisper_compatible.default_model,
            response_format=voice.whisper_compatible.response_format,
        ),
        funasr_bailian=EditableVoiceFunASRBailianConfig(
            enabled=voice.funasr_bailian.enabled,
            websocket_url=voice.funasr_bailian.websocket_url,
            api_key_masked=_mask_secret(voice.funasr_bailian.api_key.get_secret_value()),
            timeout=voice.funasr_bailian.timeout,
            model=voice.funasr_bailian.model,
            sample_rate_hz=voice.funasr_bailian.sample_rate_hz,
            chunk_interval_ms=voice.funasr_bailian.chunk_interval_ms,
            chunk_size_bytes=voice.funasr_bailian.chunk_size_bytes,
            language_hints=list(voice.funasr_bailian.language_hints),
        ),
        gpt_sovits=EditableVoiceGPTSoVITSConfig(
            enabled=voice.gpt_sovits.enabled,
            endpoint=str(voice.gpt_sovits.endpoint),
            timeout=voice.gpt_sovits.timeout,
            ref_audio_path=voice.gpt_sovits.ref_audio_path,
            ref_text=voice.gpt_sovits.ref_text,
            text_lang=voice.gpt_sovits.text_lang,
            prompt_lang=voice.gpt_sovits.prompt_lang,
        ),
    )


def _merge_voice_section(target: dict, updates: dict, *, secret_fields: set[str] | None = None) -> None:
    secrets = secret_fields or set()
    for key, value in updates.items():
        if value is None:
            continue
        if key in secrets and value == "":
            continue
        target[key] = value


def _normalize_tts_yaml(voice: dict[str, object]) -> None:
    tts = dict(voice.get("tts", {}) or {})
    voices = {
        provider: dict(entry)
        for provider, entry in build_default_tts_voice_catalog().items()
    }
    raw_voices = dict(tts.get("voices", {}) or {})
    for provider, entry in raw_voices.items():
        merged_entry = dict(voices.get(provider, {}) or {})
        merged_entry.update(dict(entry or {}))
        voices[provider] = merged_entry

    tts["default_provider"] = str(tts.get("default_provider") or DEFAULT_TTS_PROVIDER)
    tts["voices"] = voices
    voice["tts"] = tts


def _update_voice_yaml(yaml_data: dict, request: UpdateVoiceConfigRequest) -> None:
    voice = dict(yaml_data.get("voice", {}) or {})
    request_data = request.model_dump(exclude_unset=True)

    for key in (
        "enabled",
        "assets_dir",
        "public_base_url",
        "playback_base_url",
        "upload_max_bytes",
    ):
        if key in request_data and request_data[key] is not None:
            voice[key] = request_data[key]

    if request.rewrite is not None:
        rewrite = dict(voice.get("rewrite", {}) or {})
        _merge_voice_section(rewrite, request.rewrite.model_dump(exclude_unset=True))
        voice["rewrite"] = rewrite

    if request.tts is not None:
        tts = dict(voice.get("tts", {}) or {})
        tts_update = request.tts.model_dump(exclude_unset=True)
        if "default_provider" in tts_update and tts_update["default_provider"] is not None:
            tts["default_provider"] = tts_update["default_provider"]
        if "voices" in tts_update and tts_update["voices"] is not None:
            voices = dict(tts.get("voices", {}) or {})
            for provider, voice_update in tts_update["voices"].items():
                current_entry = dict(voices.get(provider, {}) or {})
                current_entry.update({key: value for key, value in voice_update.items() if value is not None})
                voices[provider] = current_entry
            tts["voices"] = voices
        voice["tts"] = tts

    if request.openai is not None:
        openai = dict(voice.get("openai", {}) or {})
        _merge_voice_section(
            openai,
            request.openai.model_dump(exclude_unset=True),
            secret_fields={"api_key"},
        )
        voice["openai"] = openai

    if request.whisper_compatible is not None:
        whisper = dict(voice.get("whisper_compatible", {}) or {})
        _merge_voice_section(
            whisper,
            request.whisper_compatible.model_dump(exclude_unset=True),
            secret_fields={"auth_token"},
        )
        voice["whisper_compatible"] = whisper

    if request.gpt_sovits is not None:
        gpt_sovits = dict(voice.get("gpt_sovits", {}) or {})
        _merge_voice_section(gpt_sovits, request.gpt_sovits.model_dump(exclude_unset=True))
        voice["gpt_sovits"] = gpt_sovits

    if request.funasr_bailian is not None:
        funasr_bailian = dict(voice.get("funasr_bailian", {}) or {})
        _merge_voice_section(
            funasr_bailian,
            request.funasr_bailian.model_dump(exclude_unset=True),
            secret_fields={"api_key"},
        )
        voice["funasr_bailian"] = funasr_bailian

    _normalize_tts_yaml(voice)
    yaml_data["voice"] = voice


@router.get("/config/status", response_model=ConfigStatusResponse)
async def get_config_status() -> ConfigStatusResponse:
    """Get current configuration status including provider health.

    Returns:
        Configuration status with provider health and circuit breaker states
    """
    config_manager = ConfigManager()
    config = config_manager.config

    providers = []

    # Get LLM router from app state or create one
    from ...main import get_llm_router

    llm_router = get_llm_router()

    # Get persistent stats from stat service
    persistent_stats = {}
    try:
        from ...services.stat_service import get_stat_service

        stat_service = get_stat_service()
        provider_stats = await stat_service.get_stats_by_provider()
        for ps in provider_stats:
            persistent_stats[ps["provider_name"]] = ps
    except Exception as e:
        logger.warning(
            "Failed to get persistent stats",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )

    for model in config.models:
        # Get circuit breaker for this provider
        cb = circuit_breaker_manager.get_breaker(model.name)
        cb_status = cb.to_dict()

        # Merge persistent stats with in-memory stats
        stats = cb_status["stats"].copy()
        if model.name in persistent_stats:
            ps = persistent_stats[model.name]
            # Use persistent stats as primary source
            stats["total_requests"] = ps["total_requests"]
            stats["successful_requests"] = ps["successful_requests"]
            stats["failed_requests"] = ps["failed_requests"]
            stats["success_rate"] = ps["success_rate"]
            stats["avg_latency_ms"] = ps["avg_latency_ms"]

        # Check provider health
        is_healthy = True
        if llm_router:
            try:
                health_results = await llm_router.health_check()
                is_healthy = health_results.get(model.name, False)
            except Exception as e:
                logger.warning(
                    "Health check failed for model",
                    extra={
                        "model_name": model.name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                is_healthy = False

        providers.append(
            ProviderStatus(
                name=model.name,
                model_id=model.model_id,
                is_primary=model.is_primary,
                is_healthy=is_healthy,
                circuit_state=cb_status["state"],
                stats=stats,
            )
        )

    return ConfigStatusResponse(
        providers=providers,
        circuit_breakers=circuit_breaker_manager.get_all_status(),
    )


@router.post("/config/reload", response_model=ConfigReloadResponse)
async def reload_config() -> ConfigReloadResponse:
    """Reload configuration from file.

    Forces a reload of the configuration file and updates all services.

    Returns:
        Reload result with model count
    """
    config_manager = ConfigManager()

    try:
        # Force reload
        config_manager.reload()
        config = config_manager.config

        logger.info(
            "Configuration reloaded successfully",
            extra={
                "models_count": len(config.models),
            },
        )

        return ConfigReloadResponse(
            success=True,
            message=f"Configuration reloaded with {len(config.models)} models",
            models_count=len(config.models),
        )
    except Exception as exc:
        logger.error(
            "Failed to reload configuration",
            extra={
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload configuration: {exc}",
        ) from exc


@router.get("/config/validate", response_model=ConfigValidationResponse)
async def validate_current_config() -> ConfigValidationResponse:
    """Validate current configuration.

    Returns detailed validation results including errors and warnings.

    Returns:
        Validation result with errors and warnings
    """
    config_manager = ConfigManager()
    config = config_manager.config

    result = validate_config(config)

    return ConfigValidationResponse(
        is_valid=result.is_valid,
        errors=[
            {"field": e.field, "message": e.message, "suggestion": e.suggestion}
            for e in result.errors
        ],
        warnings=[
            {"field": w.field, "message": w.message, "suggestion": w.suggestion}
            for w in result.warnings
        ],
    )


@router.post("/config/circuit-breaker/{provider_name}/reset")
async def reset_circuit_breaker(provider_name: str) -> dict:
    """Reset circuit breaker for a specific provider.

    Args:
        provider_name: Name of the provider to reset

    Returns:
        Success message
    """
    breaker = circuit_breaker_manager.get_breaker(provider_name)
    breaker.reset()

    logger.info(
        "Circuit breaker reset for provider",
        extra={
            "provider_name": provider_name,
        },
    )

    return {"success": True, "message": f"Circuit breaker reset for {provider_name}"}


@router.post("/config/circuit-breaker/reset-all")
async def reset_all_circuit_breakers() -> dict:
    """Reset all circuit breakers.

    Returns:
        Success message
    """
    circuit_breaker_manager.reset_all()

    logger.info("All circuit breakers reset")

    return {"success": True, "message": "All circuit breakers reset"}


@router.get("/config/edit", response_model=EditableConfigResponse)
async def get_editable_config() -> EditableConfigResponse:
    """Get editable configuration.

    Returns configuration with masked API keys for editing.

    Returns:
        Editable configuration
    """
    config_manager = ConfigManager()
    config = config_manager.config

    models = []
    for model in config.models:
        models.append(
            EditableModelConfig(
                name=model.name,
                provider=model.provider,
                base_url=str(model.base_url),
                api_key_masked=model.get_masked_key(),
                model_id=model.model_id,
                is_primary=model.is_primary,
                timeout=model.timeout,
                max_retries=model.max_retries,
                priority=model.priority,
            )
        )

    return EditableConfigResponse(
        models=models,
        voice=_editable_voice_config(config),
        config_path=str(config_manager.config_path),
    )


@router.put("/config/models/{model_name}", response_model=UpdateModelResponse)
async def update_model_config(model_name: str, request: UpdateModelRequest) -> UpdateModelResponse:
    """Update a model configuration.

    Updates the configuration file and reloads.

    Args:
        model_name: Name of the model to update
        request: Update request with fields to change

    Returns:
        Updated model configuration
    """
    config_manager = ConfigManager()
    config = config_manager.config
    config_path = config_manager.config_path

    # Find the model
    model = config.get_model_by_name(model_name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

    # Read current YAML
    try:
        yaml_data = _read_yaml_config(config_path)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read config file: {exc}",
        ) from exc

    # Find and update the model in YAML
    models_list = yaml_data.get("models", [])
    model_found = False

    for _i, m in enumerate(models_list):
        if m.get("name") == model_name:
            model_found = True
            # Update fields
            if request.model_id is not None:
                m["model_id"] = request.model_id
            if request.api_key is not None:
                m["api_key"] = request.api_key
            if request.is_primary is not None:
                # If setting this as primary, unset others
                if request.is_primary:
                    for other_m in models_list:
                        if other_m.get("name") != model_name:
                            other_m["is_primary"] = False
                m["is_primary"] = request.is_primary
            if request.timeout is not None:
                m["timeout"] = request.timeout
            if request.max_retries is not None:
                m["max_retries"] = request.max_retries
            if request.priority is not None:
                m["priority"] = request.priority
            break

    if not model_found:
        raise HTTPException(
            status_code=404, detail=f"Model '{model_name}' not found in config file"
        )

    # Write back to YAML
    try:
        _write_yaml_config(config_path, yaml_data)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write config file: {exc}",
        ) from exc

    # Reload configuration
    config_manager.reload()
    config = config_manager.config
    updated_model = config.get_model_by_name(model_name)

    if not updated_model:
        raise HTTPException(status_code=500, detail="Model disappeared after update")

    logger.info(
        "Model updated successfully",
        extra={
            "model_name": model_name,
        },
    )

    return UpdateModelResponse(
        success=True,
        message=f"Model '{model_name}' updated successfully",
        model=EditableModelConfig(
            name=updated_model.name,
            provider=updated_model.provider,
            base_url=str(updated_model.base_url),
            api_key_masked=updated_model.get_masked_key(),
            model_id=updated_model.model_id,
            is_primary=updated_model.is_primary,
            timeout=updated_model.timeout,
            max_retries=updated_model.max_retries,
            priority=updated_model.priority,
        ),
    )


@router.put("/config/voice", response_model=UpdateVoiceConfigResponse)
async def update_voice_config(request: UpdateVoiceConfigRequest) -> UpdateVoiceConfigResponse:
    """Update voice-related configuration and reload config."""
    config_manager = ConfigManager()
    config_path = config_manager.config_path

    try:
        yaml_data = _read_yaml_config(config_path)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read config file: {exc}",
        ) from exc

    _update_voice_yaml(yaml_data, request)

    try:
        _write_yaml_config(config_path, yaml_data)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write config file: {exc}",
        ) from exc

    try:
        config_manager.reload()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload configuration: {exc}",
        ) from exc

    logger.info("Voice configuration updated successfully")

    return UpdateVoiceConfigResponse(
        success=True,
        message="Voice configuration updated successfully",
        voice=_editable_voice_config(config_manager.config),
    )
