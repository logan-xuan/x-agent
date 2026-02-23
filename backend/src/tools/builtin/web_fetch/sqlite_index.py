"""SQLite Index Manager.

Manages SQLite database index for web content.
Stores metadata and file paths, not the actual content.
TTL: 72 hours with LRU management.
"""

import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLiteIndexManager:
    """SQLite-based index manager for web content."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize index manager.
        
        Args:
            db_path: Path to SQLite database. Defaults to backend/data/web_index.db
        """
        if db_path is None:
            # Default to backend/data directory
            backend_dir = Path(__file__).parent.parent.parent.parent
            data_dir = backend_dir / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "web_index.db")
        
        self.db_path = db_path
        self._init_database()
        
        logger.info(
            "SQLiteIndexManager initialized",
            extra={"db_path": db_path}
        )
    
    def _init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS web_content_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_hash TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    
                    -- File paths
                    markdown_path TEXT NOT NULL,
                    images_dir TEXT NOT NULL,
                    
                    -- Metadata
                    title TEXT NOT NULL,
                    word_count INTEGER DEFAULT 0,
                    language TEXT,
                    
                    -- Timestamps
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    
                    -- LRU stats
                    access_count INTEGER DEFAULT 0,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_url_hash ON web_content_index(url_hash);
                CREATE INDEX IF NOT EXISTS idx_expires_at ON web_content_index(expires_at);
                CREATE INDEX IF NOT EXISTS idx_last_accessed ON web_content_index(last_accessed);
                
                -- Auto-cleanup trigger for expired entries (72 hours TTL)
                CREATE TRIGGER IF NOT EXISTS cleanup_expired_index
                AFTER INSERT ON web_content_index
                BEGIN
                    DELETE FROM web_content_index
                    WHERE expires_at < CURRENT_TIMESTAMP;
                END;
            """)
            
            conn.commit()
        
        logger.debug("Database schema initialized")
    
    def _compute_url_hash(self, url: str) -> str:
        """Compute MD5 hash of URL."""
        return hashlib.md5(url.encode()).hexdigest()
    
    async def get_index(self, url: str) -> Optional[dict]:
        """Get index entry if exists and not expired.
        
        Args:
            url: The URL to look up
            
        Returns:
            Index entry as dict, or None if not found/expired
        """
        url_hash = self._compute_url_hash(url)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT *
                    FROM web_content_index
                    WHERE url_hash = ? AND expires_at > CURRENT_TIMESTAMP
                """, (url_hash,))
                
                row = cursor.fetchone()
                if row:
                    # Update access count and last_accessed (LRU)
                    conn.execute("""
                        UPDATE web_content_index
                        SET access_count = access_count + 1,
                            last_accessed = CURRENT_TIMESTAMP
                        WHERE url_hash = ?
                    """, (url_hash,))
                    conn.commit()
                    
                    logger.debug(f"Index hit for URL: {url}")
                    return dict(row)
                    
        except Exception as e:
            logger.error(f"Failed to get index: {e}")
        
        return None
    
    async def add_index(
        self,
        url: str,
        markdown_path: str,
        images_dir: str,
        title: str,
        word_count: int,
        language: Optional[str] = None,
        ttl_hours: int = 72,  # 72 hours TTL
    ):
        """Add index entry with TTL.
        
        Args:
            url: The URL
            markdown_path: Relative path to Markdown file
            images_dir: Relative path to images directory
            title: Page title
            word_count: Word count
            language: Content language
            ttl_hours: Time-to-live in hours (default 72)
        """
        url_hash = self._compute_url_hash(url)
        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO web_content_index
                    (url_hash, url, markdown_path, images_dir, title, word_count, language, 
                     fetched_at, expires_at, access_count, last_accessed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, 0, CURRENT_TIMESTAMP)
                """, (
                    url_hash, url, markdown_path, images_dir,
                    title, word_count, language, expires_at.isoformat()
                ))
                conn.commit()
            
            logger.info(
                f"Added index entry",
                extra={
                    "url": url,
                    "markdown_path": markdown_path,
                    "expires_at": expires_at.isoformat(),
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to add index: {e}")
            raise
    
    async def cleanup_expired(self) -> int:
        """Manually cleanup expired entries.
        
        Returns:
            Number of deleted entries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                result = conn.execute("""
                    DELETE FROM web_content_index 
                    WHERE expires_at < CURRENT_TIMESTAMP
                """)
                deleted_count = result.rowcount
                conn.commit()
            
            logger.info(f"Cleaned up {deleted_count} expired index entries")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return 0
    
    async def get_stats(self) -> dict:
        """Get index statistics.
        
        Returns:
            Statistics dict
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM web_content_index").fetchone()[0]
                
                # Get size breakdown by date
                date_counts = conn.execute("""
                    SELECT substr(fetched_at, 1, 10) as date, COUNT(*) as count
                    FROM web_content_index
                    GROUP BY substr(fetched_at, 1, 10)
                    ORDER BY date DESC
                    LIMIT 7
                """).fetchall()
                
                db_size = Path(self.db_path).stat().st_size
                
                return {
                    "total_entries": total,
                    "database_size_bytes": db_size,
                    "database_size_mb": round(db_size / 1024 / 1024, 2),
                    "entries_by_date": [
                        {"date": row[0], "count": row[1]} 
                        for row in date_counts
                    ],
                }
                
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "total_entries": 0,
                "database_size_bytes": 0,
                "database_size_mb": 0,
                "entries_by_date": [],
            }
    
    async def remove_index(self, url: str) -> bool:
        """Remove index entry for a URL.
        
        Args:
            url: URL to remove
            
        Returns:
            True if removed, False if not found
        """
        url_hash = self._compute_url_hash(url)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                result = conn.execute("""
                    DELETE FROM web_content_index
                    WHERE url_hash = ?
                """, (url_hash,))
                conn.commit()
                
                removed = result.rowcount > 0
                if removed:
                    logger.info(f"Removed index for URL: {url}")
                return removed
                
        except Exception as e:
            logger.error(f"Failed to remove index: {e}")
            return False
