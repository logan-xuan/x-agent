"""Storage service for database operations."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config.manager import get_config
from ..models.base import Base


class StorageService:
    """Service for database storage operations.
    
    Provides async database access with SQLAlchemy.
    """
    
    def __init__(self, database_url: str | None = None) -> None:
        """Initialize storage service.
        
        Args:
            database_url: Database URL (defaults to SQLite)
        """
        if database_url is None:
            database_url = "sqlite+aiosqlite:///./x-agent.db"
        
        self.engine = create_async_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
        )
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
    
    async def initialize(self) -> None:
        """Initialize database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def close(self) -> None:
        """Close database connections."""
        await self.engine.dispose()
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session context manager.
        
        Usage:
            async with storage.session() as db:
                result = await db.execute(...)
        """
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def health_check(self) -> bool:
        """Check database connectivity.
        
        Returns:
            True if database is accessible
        """
        try:
            async with self.session() as db:
                await db.execute("SELECT 1")
                return True
        except Exception:
            return False


# Global instance
_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    """Get or create global storage service instance."""
    global _storage_service
    if _storage_service is None:
        config = get_config()
        # Use SQLite by default
        _storage_service = StorageService()
    return _storage_service


async def init_storage() -> StorageService:
    """Initialize storage service and database.
    
    Returns:
        Initialized StorageService
    """
    service = get_storage_service()
    await service.initialize()
    return service


async def close_storage() -> None:
    """Close storage service and database connections."""
    global _storage_service
    if _storage_service is not None:
        await _storage_service.close()
        _storage_service = None
