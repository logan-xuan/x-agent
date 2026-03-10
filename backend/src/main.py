"""X-Agent main application entry point."""

import asyncio
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import Callable
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.middleware import ErrorHandlerMiddleware, TracingMiddleware
from .api.middleware.rate_limit import RateLimitMiddleware
from .config.manager import ConfigManager
from .conversation.context import context_manager
from .services.storage import init_storage, close_storage
from .services.llm.router import LLMRouter
from .utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


def _install_global_exception_hooks() -> None:
    """Install global exception hooks to catch ALL unhandled exceptions.
    
    Covers two blind spots that ErrorHandlerMiddleware cannot reach:
    1. sys.excepthook — uncaught synchronous exceptions (e.g. background threads)
    2. asyncio exception handler — uncaught async exceptions (e.g. fire-and-forget tasks)
    
    These hooks ensure that no exception is silently swallowed anywhere in the system.
    """
    # 1. Synchronous uncaught exceptions
    original_excepthook = sys.excepthook

    def global_excepthook(exc_type, exc_value, exc_tb):
        if exc_type is KeyboardInterrupt:
            original_excepthook(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "Uncaught exception (sys.excepthook)",
            extra={
                "error_type": exc_type.__name__,
                "error": str(exc_value),
                "traceback": "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
            },
        )
        original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = global_excepthook

    # 2. Asyncio uncaught exceptions (fire-and-forget tasks, callbacks)
    def asyncio_exception_handler(loop, context):
        exception = context.get("exception")
        message = context.get("message", "Unhandled async exception")
        
        if exception:
            logger.critical(
                f"Uncaught async exception: {message}",
                extra={
                    "error_type": type(exception).__name__,
                    "error": str(exception),
                    "traceback": "".join(traceback.format_exception(type(exception), exception, exception.__traceback__)),
                    "async_context": {k: str(v) for k, v in context.items() if k != "exception"},
                },
            )
        else:
            logger.critical(
                f"Uncaught async error: {message}",
                extra={"async_context": {k: str(v) for k, v in context.items()}},
            )

    try:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(asyncio_exception_handler)
    except RuntimeError:
        pass

    logger.info("Global exception hooks installed (sys.excepthook + asyncio handler)")

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


def _make_memory_sync_callback(manager: Any) -> Callable[[str], None]:
    """Create a file-change callback that syncs memory via MemoryManager."""
    def on_memory_file_changed(file_path: str) -> None:
        try:
            manager.sync_to_vectors(file_path)
        except Exception as exc:
            logger.error(
                "Failed to sync memory file change",
                extra={"file_path": file_path, "error": str(exc)},
            )
    return on_memory_file_changed


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
    
    # 2.1 Initialize AgentLogger file persistence
    from .agent_core.logger import AgentLogger
    agent_logger = AgentLogger()
    agent_logger.initialize_file_persistence(
        log_file=config.logging.agent_log_file,
        max_size=config.logging.agent_log_max_size,
        backup_count=config.logging.agent_log_backup_count,
        when=config.logging.when,
        interval=config.logging.interval,
    )
    logger.info(
        "AgentLogger file persistence initialized",
        extra={"log_file": config.logging.agent_log_file}
    )
    
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

    # 3.1 Ensure default User exists (Agent/Channel are config-driven)
    raw_workspace_path = config.workspace.path
    expanded_workspace_path = Path(raw_workspace_path).expanduser()
    if expanded_workspace_path.is_absolute():
        workspace_path = str(expanded_workspace_path.resolve())
    else:
        backend_dir = Path(__file__).parent
        workspace_path = str((backend_dir / raw_workspace_path).resolve())

    from .conversation.dao import ensure_default_entities
    await ensure_default_entities()
    logger.info("Default entities ensured")
    
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
    
    # 5.5 Initialize Multi-Agent Context Loader (if multi-agent config exists)
    if hasattr(config, 'multi_agent') and config.multi_agent and config.multi_agent.agents:
        try:
            from .conversation.multi_agent_context_loader import MultiAgentContextLoader
            
            multi_agent_context_loader = MultiAgentContextLoader(config.multi_agent)
            agent_contexts = multi_agent_context_loader.initialize_all_agents()
            app.state.multi_agent_context_loader = multi_agent_context_loader

            # 注册全局单例，供 agent_bridge 等模块直接导入使用
            from .conversation.multi_agent_context_loader import set_multi_agent_context_loader
            set_multi_agent_context_loader(multi_agent_context_loader)
            
            # Log summary of loaded context files
            total_files = sum(len(files) for files in agent_contexts.values())
            logger.info(
                "Multi-Agent context initialized",
                extra={
                    "agent_count": len(agent_contexts),
                    "total_context_files": total_files,
                }
            )
            
            # Log detailed status for each agent
            for agent_id, files in agent_contexts.items():
                loaded_count = sum(1 for exists in files.values() if exists)
                logger.info(
                    f"Agent {agent_id} context loaded",
                    extra={
                        "agent_id": agent_id,
                        "loaded_files": loaded_count,
                        "total_files": len(files),
                        "files": files,
                    }
                )
        except Exception as e:
            logger.error(
                "Failed to initialize multi-agent context loader",
                extra={"error": str(e)},
            )
            # Non-fatal error, continue startup
    
    # 6. Initialize MemoryManager and start file watcher
    from .memory.file_watcher import get_file_watcher
    from .memory.manager import init_memory_manager
    from .conversation.session import SessionManager
    
    # workspace_path 已在步骤 3.1 中解析完成，直接复用
    
    # Initialize MemoryManager (unified entry point for all memory operations)
    session_manager = SessionManager()
    memory_manager = init_memory_manager(
        workspace_path=workspace_path,
        llm_router=_llm_router,
        session_manager=session_manager,
    )
    app.state.memory_manager = memory_manager
    logger.info("MemoryManager initialized")
    
    # Start file watcher with callbacks
    def _on_spirit_changed() -> None:
        logger.info("SPIRIT.md changed, hot-reload triggered")

    def _on_owner_changed() -> None:
        logger.info("OWNER.md changed, hot-reload triggered")

    def _on_identity_changed() -> None:
        _clear_context_cache()
        logger.info("IDENTITY.md changed, context cache cleared")

    _file_watcher = get_file_watcher(workspace_path)
    _file_watcher.start(
        on_spirit_changed=_on_spirit_changed,
        on_owner_changed=_on_owner_changed,
        on_tools_changed=lambda: logger.info("TOOLS.md changed, hot-reload triggered"),
        on_memory_changed=_make_memory_sync_callback(memory_manager),
        on_identity_changed=_on_identity_changed,
    )
    logger.info("File watcher started for memory sync")
    
    # 7. Initial sync: Markdown -> Vector Store
    try:
        synced_count = memory_manager.sync_to_vectors()
        logger.info(
            "Initial memory sync completed",
            extra={"synced_entries": synced_count}
        )
    except Exception as e:
        logger.warning(
            "Initial memory sync failed (non-fatal)",
            extra={"error": str(e)}
        )
    
    # 8. Initialize and start cron scheduler
    from .cron.scheduler import get_scheduler as get_cron_scheduler
    _cron_scheduler = get_cron_scheduler()
    await _cron_scheduler.initialize()
    await _cron_scheduler.start()
    app.state.cron_scheduler = _cron_scheduler
    logger.info("Cron scheduler initialized and started")
    
    # 9. Install global exception hooks
    _install_global_exception_hooks()
    
    logger.info("X-Agent started successfully")
    
    yield
    
    # === SHUTDOWN ===
    logger.info("Shutting down X-Agent...")
    
    # 1. Stop cron scheduler
    if _cron_scheduler:
        await _cron_scheduler.stop()
        logger.info("Cron scheduler stopped")
    
    # 2. Stop file watcher
    if _file_watcher:
        _file_watcher.stop()
        logger.info("File watcher stopped")
    
    # 3. Stop config watcher
    if _config_manager:
        _config_manager.stop_watcher()
        logger.info("Configuration watcher stopped")
    
    # 4. Close LLM connections
    if _llm_router:
        await _llm_router.close()
        logger.info("LLM router closed")
    
    # 5. Close database connections
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
    from .api.v1.config import router as config_router
    from .api.v1.dev import router as dev_router
    from .api.v1.health import router as health_router
    from .api.v1.stats import router as stats_router
    from .api.v1.memory import router as memory_router
    from .api.v1.trace import router as trace_router
    from .api.v1.skills import router as skills_router
    from .api.v1.sessions import router as sessions_router
    from .api.v1.admin import router as admin_router
    from .gateway.endpoints import websocket_router as agent_websocket_router
    from .gateway.endpoints import rest_router as gateway_rest_router
    from .agent_core.api import agent_rest_router
    
    app.include_router(health_router, prefix="/api/v1", tags=["Health"])
    app.include_router(config_router, prefix="/api/v1", tags=["Config"])
    app.include_router(stats_router, prefix="/api/v1", tags=["Stats"])
    app.include_router(memory_router, prefix="/api/v1", tags=["Memory"])
    app.include_router(dev_router, prefix="/api/v1", tags=["Developer"])
    app.include_router(trace_router, prefix="/api/v1", tags=["Trace"])
    app.include_router(skills_router, prefix="/api/v1", tags=["Skills"])
    app.include_router(sessions_router, prefix="/api/v1", tags=["Sessions"])
    app.include_router(admin_router, prefix="/api/v1", tags=["Admin"])
    app.include_router(agent_websocket_router, prefix="/ws", tags=["WebSocket"])
    app.include_router(gateway_rest_router, prefix="/api/v1", tags=["Gateway"])
    app.include_router(agent_rest_router, prefix="/api/v1", tags=["Agent Logs"])
    
    # Add cron scheduler router
    from .cron.api.router import router as cron_router
    app.include_router(cron_router, prefix="/api/v1", tags=["Cron"])
    
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
