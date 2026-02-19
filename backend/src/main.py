"""X-Agent main application entry point."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.middleware import ErrorHandlerMiddleware, TracingMiddleware
from .api.middleware.rate_limit import RateLimitMiddleware
from .config.manager import ConfigManager
from .core.context import context_manager, ContextSource
from .services.storage import init_storage, close_storage
from .services.llm.router import LLMRouter
from .utils.logger import get_logger, setup_logging

logger = get_logger(__name__)

# Global instances
_config_manager: Optional[ConfigManager] = None
_llm_router: Optional[LLMRouter] = None


def get_config_manager() -> ConfigManager:
    """Get global config manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_llm_router() -> LLMRouter:
    """Get global LLM router instance."""
    global _llm_router
    if _llm_router is None:
        config = get_config_manager().config
        _llm_router = LLMRouter(config.models)
    return _llm_router


def _clear_context_cache() -> None:
    """Clear the context builder cache when IDENTITY.md changes."""
    from .memory.context_builder import get_context_builder
    try:
        context_builder = get_context_builder()
        context_builder.clear_cache()
        logger.info("Context builder cache cleared")
    except Exception as e:
        logger.warning("Failed to clear context cache", extra={"error": str(e)})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager with proper startup/shutdown.
    
    Startup sequence:
    1. Load configuration
    2. Setup logging
    3. Initialize database
    4. Initialize LLM router
    5. Start config watcher
    
    Shutdown sequence:
    1. Stop config watcher
    2. Close LLM connections
    3. Close database connections
    """
    global _config_manager, _llm_router
    
    # === STARTUP ===
    logger.info("Starting X-Agent...")
    
    # 1. Load configuration
    _config_manager = ConfigManager()
    config = _config_manager.config
    logger.info("Configuration loaded", extra={"config_path": str(_config_manager.config_path)})
    
    # 2. Setup logging
    setup_logging(config.logging)
    logger.info("Logging configured")
    
    # 2.5 Validate configuration
    from .config.validator import validate_config
    validation_result = validate_config(config)
    if not validation_result.is_valid:
        for error in validation_result.errors:
            logger.error(
                "Configuration validation error",
                extra={
                    "field": error.field,
                    "message": error.message,
                    "suggestion": error.suggestion,
                }
            )
        raise RuntimeError("Configuration validation failed. Check logs for details.")
    for warning in validation_result.warnings:
        logger.warning(
            "Configuration validation warning",
            extra={
                "field": warning.field,
                "message": warning.message,
                "suggestion": warning.suggestion,
            }
        )
    
    # 3. Initialize database
    await init_storage()
    logger.info("Database initialized")
    
    # 4. Initialize LLM router
    _llm_router = LLMRouter(config.models)
    logger.info(
        "LLM router initialized",
        extra={
            "primary_model": _llm_router.primary_model.model_id if _llm_router.primary_model else None,
            "backup_count": len(_llm_router.backup_models),
        },
    )
    
    # 5. Start config watcher for hot-reload
    _config_manager.start_watcher()
    logger.info("Configuration watcher started")
    
    # Store in app state
    app.state.config_manager = _config_manager
    app.state.llm_router = _llm_router
    
    # 6. Start file watcher for memory sync (Phase 7)
    from .memory.file_watcher import get_file_watcher
    from .memory.md_sync import get_md_sync
    from .memory.vector_store import get_vector_store
    from .memory.embedder import get_embedder
    
    # Handle ~ expansion and absolute/relative paths correctly
    raw_workspace_path = config.workspace.path
    expanded_workspace_path = Path(raw_workspace_path).expanduser()
    if expanded_workspace_path.is_absolute():
        workspace_path = str(expanded_workspace_path.resolve())
    else:
        backend_dir = Path(__file__).parent
        workspace_path = str((backend_dir / raw_workspace_path).resolve())
    
    _file_watcher = get_file_watcher(workspace_path)
    
    # Get dependencies for sync
    md_sync = get_md_sync(workspace_path)
    vector_store = get_vector_store()
    embedder = get_embedder()
    
    # Define sync callback for memory file changes
    def on_memory_file_changed(file_path: str) -> None:
        """Handle memory file changes and sync to vector store."""
        try:
            md_sync.sync_on_file_change(file_path, vector_store, embedder)
        except Exception as e:
            logger.error(
                "Failed to sync memory file change",
                extra={"file_path": file_path, "error": str(e)}
            )
    
    # Start file watcher with callbacks
    _file_watcher.start(
        on_spirit_changed=lambda: logger.info("SPIRIT.md changed, hot-reload triggered"),
        on_owner_changed=lambda: logger.info("OWNER.md changed, hot-reload triggered"),
        on_tools_changed=lambda: logger.info("TOOLS.md changed, hot-reload triggered"),
        on_memory_changed=on_memory_file_changed,
        on_identity_changed=lambda: (_clear_context_cache(), logger.info("IDENTITY.md changed, context cache cleared")),
    )
    logger.info("File watcher started for memory sync")
    
    # 7. Initial sync: Markdown -> Vector Store
    try:
        synced_count = md_sync.sync_all_entries_to_vector_store(vector_store, embedder)
        logger.info(
            "Initial memory sync completed",
            extra={"synced_entries": synced_count}
        )
    except Exception as e:
        logger.warning(
            "Initial memory sync failed (non-fatal)",
            extra={"error": str(e)}
        )
    
    logger.info("X-Agent started successfully")
    
    yield
    
    # === SHUTDOWN ===
    logger.info("Shutting down X-Agent...")
    
    # 1. Stop file watcher
    if _file_watcher:
        _file_watcher.stop()
        logger.info("File watcher stopped")
    
    # 2. Stop config watcher
    if _config_manager:
        _config_manager.stop_watcher()
        logger.info("Configuration watcher stopped")
    
    # 3. Close LLM connections
    if _llm_router:
        await _llm_router.close()
        logger.info("LLM router closed")
    
    # 4. Close database connections
    await close_storage()
    logger.info("Database connections closed")
    
    # Clear global state
    _config_manager = None
    _llm_router = None
    
    logger.info("X-Agent stopped")


def create_app() -> FastAPI:
    """Create and configure FastAPI application.
    
    Middleware order (first added = outermost):
    1. CORS - Allow cross-origin requests
    2. Error Handler - Catch all exceptions
    3. Tracing - Add trace IDs
    
    Returns:
        Configured FastAPI app
    """
    # Load config
    config_manager = get_config_manager()
    config = config_manager.config
    
    app = FastAPI(
        title="X-Agent",
        description="Personal AI Agent with modular architecture",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if config.server.reload else None,
        redoc_url="/redoc" if config.server.reload else None,
    )
    
    # === MIDDLEWARE ===
    # Order matters: first added = outermost
    
    # 1. CORS middleware (outermost)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Trace-ID", "X-Request-ID", "X-Response-Time"],
    )
    
    # 2. Error handling middleware
    app.add_middleware(
        ErrorHandlerMiddleware,
        include_traceback=config.server.reload,
    )
    
    # 3. Rate limiting middleware
    app.add_middleware(RateLimitMiddleware)
    
    # 4. Tracing middleware (innermost)
    app.add_middleware(TracingMiddleware)
    
    # === ROUTES ===
    from .api.v1.chat import router as chat_router
    from .api.v1.config import router as config_router
    from .api.v1.context import router as context_router
    from .api.v1.dev import router as dev_router
    from .api.v1.health import router as health_router
    from .api.v1.session import router as session_router
    from .api.v1.stats import router as stats_router
    from .api.v1.memory import router as memory_router
    from .api.v1.trace import router as trace_router
    from .api.v1.skills import router as skills_router
    from .api.websocket import router as websocket_router
    
    app.include_router(health_router, prefix="/api/v1", tags=["Health"])
    app.include_router(chat_router, prefix="/api/v1", tags=["Chat"])
    app.include_router(config_router, prefix="/api/v1", tags=["Config"])
    app.include_router(context_router, prefix="/api/v1", tags=["Context"])
    app.include_router(session_router, prefix="/api/v1", tags=["Session"])
    app.include_router(stats_router, prefix="/api/v1", tags=["Stats"])
    app.include_router(memory_router, prefix="/api/v1", tags=["Memory"])
    app.include_router(dev_router, prefix="/api/v1", tags=["Developer"])
    app.include_router(trace_router, prefix="/api/v1", tags=["Trace"])
    app.include_router(skills_router, prefix="/api/v1", tags=["Skills"])
    app.include_router(websocket_router, prefix="/ws", tags=["WebSocket"])
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    config = get_config_manager().config
    
    uvicorn.run(
        "src.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.reload,
        log_config=None,  # Use our own logging
    )
