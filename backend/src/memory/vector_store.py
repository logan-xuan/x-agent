"""Vector store using sqlite-vss for vector similarity search.

This module provides:
- Vector embedding storage and retrieval
- Cosine similarity search
- Integration with SQLite database
"""

import json
from pathlib import Path
from typing import Any

from ..utils.logger import get_logger

logger = get_logger(__name__)


class VectorStore:
    """Vector store using sqlite-vss extension.
    
    Provides vector storage and similarity search capabilities
    using SQLite with the vss extension.
    """
    
    def __init__(self, db_path: str, embedding_dim: int = 384) -> None:
        """Initialize vector store.
        
        Args:
            db_path: Path to SQLite database file
            embedding_dim: Dimension of embedding vectors (default: 384 for all-MiniLM-L6-v2)
        """
        self.db_path = Path(db_path)
        self.embedding_dim = embedding_dim
        self._connection: Any = None
        self._initialized = False
        self._vss_available = False
        self._vss_table_exists = False
        
        logger.info(
            "VectorStore initialized",
            extra={
                "db_path": str(db_path),
                "embedding_dim": embedding_dim,
            }
        )

    def _load_vss_extension(self, conn: Any) -> bool:
        """Load sqlite-vss extension into connection.
        
        Args:
            conn: SQLite connection
            
        Returns:
            True if extension loaded successfully
        """
        import os
        
        try:
            conn.enable_load_extension(True)
            
            # Try to find extension files
            # First check if sqlite_vss package is installed
            try:
                import sqlite_vss
                vss_dir = os.path.dirname(sqlite_vss.__file__)
            except ImportError:
                # Fallback to common installation paths
                import sys
                vss_dir = os.path.join(sys.prefix, "lib/python3.13/site-packages/sqlite_vss")
            
            vector0_path = os.path.join(vss_dir, "vector0.dylib")
            vss0_path = os.path.join(vss_dir, "vss0.dylib")
            
            # For Linux
            if not os.path.exists(vector0_path):
                vector0_path = os.path.join(vss_dir, "vector0.so")
            if not os.path.exists(vss0_path):
                vss0_path = os.path.join(vss_dir, "vss0.so")
            
            # Load extensions
            if os.path.exists(vector0_path) and os.path.exists(vss0_path):
                conn.load_extension(vector0_path)
                conn.load_extension(vss0_path)
                logger.debug("sqlite-vss extension loaded successfully")
                return True
            else:
                logger.warning(
                    "sqlite-vss extension files not found",
                    extra={"vss_dir": vss_dir}
                )
                return False
                
        except Exception as e:
            logger.warning(
                "Failed to load sqlite-vss extension",
                extra={"error": str(e)}
            )
            return False
    
    def _get_connection(self) -> Any:
        """Get or create database connection."""
        if self._connection is None:
            import sqlite3
            # check_same_thread=False allows connection to be shared across threads
            # This is needed because file_watcher runs in a separate thread
            self._connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            
            # Try to load sqlite-vss extension
            self._vss_available = self._load_vss_extension(self._connection)
            
        return self._connection
    
    def initialize(self) -> None:
        """Initialize vector store tables and indexes.
        
        Creates the necessary tables for vector storage if they don't exist.
        """
        if self._initialized:
            return
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Create memory entries table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    source_file TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT
                )
            """)
            
            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_entries_created_at 
                ON memory_entries(created_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_entries_content_type 
                ON memory_entries(content_type)
            """)
            
            # Create embeddings table (used when vss is not available)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    entry_id TEXT PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    FOREIGN KEY (entry_id) REFERENCES memory_entries(id)
                )
            """)
            
            # Try to create virtual table for vector search
            # Only attempt if vss extension was loaded successfully
            if self._vss_available:
                try:
                    cursor.execute(f"""
                        CREATE VIRTUAL TABLE IF NOT EXISTS memory_embeddings_vss 
                        USING vss0(embedding({self.embedding_dim}))
                    """)
                    self._vss_table_exists = True
                    logger.info(
                        "Vector search table created with sqlite-vss",
                        extra={"embedding_dim": self.embedding_dim}
                    )
                except Exception as e:
                    self._vss_table_exists = False
                    logger.warning(
                        "Failed to create vss virtual table",
                        extra={"error": str(e)}
                    )
            else:
                self._vss_table_exists = False
                logger.warning(
                    "sqlite-vss not available, falling back to basic storage",
                    extra={"note": "Install sqlite-vss for vector search support"}
                )
            
            conn.commit()
            self._initialized = True
            logger.info("VectorStore tables initialized successfully")
            
        except Exception as e:
            logger.error(
                "Failed to initialize VectorStore",
                extra={"error": str(e)}
            )
            raise
    
    def insert(self, entry_id: str, embedding: list[float], content: str, 
               content_type: str, metadata: dict[str, Any] | None = None) -> None:
        """Insert a vector embedding into the store.
        
        Args:
            entry_id: Unique identifier for the entry
            embedding: Vector embedding
            content: Text content
            content_type: Type of content
            metadata: Optional metadata
        """
        if not self._initialized:
            self.initialize()
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Insert into main table
            cursor.execute("""
                INSERT OR REPLACE INTO memory_entries 
                (id, content, content_type, source_file, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), ?)
            """, (
                entry_id,
                content,
                content_type,
                "",
                json.dumps(metadata) if metadata else None
            ))
            
            # Insert into vector table (regular table, always available)
            try:
                embedding_json = json.dumps(embedding)
                cursor.execute("""
                    INSERT OR REPLACE INTO memory_embeddings (entry_id, embedding)
                    VALUES (?, ?)
                """, (entry_id, embedding_json))
            except Exception as e:
                logger.debug(
                    "Could not insert vector embedding",
                    extra={"entry_id": entry_id, "error": str(e)}
                )
            
            # Also insert into vss table if available
            if self._vss_available and self._vss_table_exists:
                try:
                    import struct
                    # Convert embedding to bytes for vss
                    embedding_bytes = struct.pack(f'{len(embedding)}f', *embedding)
                    cursor.execute("""
                        INSERT OR REPLACE INTO memory_embeddings_vss (rowid, embedding)
                        VALUES (?, ?)
                    """, (abs(hash(entry_id)) % (2**31), embedding_bytes))
                except Exception as e:
                    logger.debug(
                        "Could not insert into vss table",
                        extra={"entry_id": entry_id, "error": str(e)}
                    )
            
            conn.commit()
            logger.debug(
                "Vector entry inserted",
                extra={"entry_id": entry_id, "content_type": content_type}
            )
            
        except Exception as e:
            logger.error(
                "Failed to insert vector",
                extra={"entry_id": entry_id, "error": str(e)}
            )
            raise
    
    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Cosine similarity score (0.0 to 1.0)
        """
        import math
        
        if len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(x * x for x in vec1))
        norm2 = math.sqrt(sum(x * x for x in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def search(self, query_embedding: list[float], limit: int = 10) -> list[dict[str, Any]]:
        """Search for similar vectors.
        
        Args:
            query_embedding: Query vector
            limit: Maximum number of results
            
        Returns:
            List of matching entries with similarity scores
        """
        if not self._initialized:
            self.initialize()
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # If vss is available, use it
            if self._vss_available and self._vss_table_exists:
                try:
                    # Convert query to blob format for vss
                    import struct
                    query_bytes = struct.pack(f'{len(query_embedding)}f', *query_embedding)
                    
                    cursor.execute("""
                        SELECT rowid, distance
                        FROM memory_embeddings_vss
                        WHERE embedding MATCH vss_search_params(?, ?)
                        ORDER BY distance
                        LIMIT ?
                    """, (query_bytes, limit, limit))
                    
                    results = []
                    for row in cursor.fetchall():
                        # Get entry by hash lookup
                        entry_id_hash = row["rowid"]
                        # We need to find the entry_id from the hash
                        # For now, skip vss and use Python fallback
                        pass
                    
                    if results:
                        return results
                except Exception as e:
                    logger.debug(f"VSS search failed: {e}, falling back to Python")
            
            # Fallback: Use Python to calculate cosine similarity
            logger.debug("Using Python cosine similarity (vss not available)")
            
            # Get all entries with embeddings using proper join
            cursor.execute("""
                SELECT m.id, m.content, m.content_type, m.metadata, e.embedding
                FROM memory_entries m
                JOIN memory_embeddings e ON m.id = e.entry_id
            """)
            
            results = []
            for row in cursor.fetchall():
                entry_embedding_json = row["embedding"]
                if entry_embedding_json:
                    try:
                        entry_embedding = json.loads(entry_embedding_json)
                        similarity = self._cosine_similarity(query_embedding, entry_embedding)
                        if similarity > 0.0:  # Only include if there's some similarity
                            results.append({
                                "id": row["id"],
                                "content": row["content"],
                                "content_type": row["content_type"],
                                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                                "score": similarity
                            })
                    except (json.JSONDecodeError, TypeError):
                        continue
            
            # Sort by similarity and limit results
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]
                
        except Exception as e:
            logger.error(
                "Failed to search vectors",
                extra={"error": str(e)}
            )
            return []
    
    def delete(self, entry_id: str) -> bool:
        """Delete a vector entry.
        
        Args:
            entry_id: ID of entry to delete
            
        Returns:
            True if deleted, False if not found
        """
        if not self._initialized:
            self.initialize()
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM memory_entries WHERE id = ?", (entry_id,))
            conn.commit()
            
            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug("Vector entry deleted", extra={"entry_id": entry_id})
            return deleted
            
        except Exception as e:
            logger.error(
                "Failed to delete vector",
                extra={"entry_id": entry_id, "error": str(e)}
            )
            return False
    
    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.debug("VectorStore connection closed")

    def get_embedding(self, entry_id: str) -> list[float] | None:
        """Get embedding for an entry.
        
        Args:
            entry_id: ID of the entry
            
        Returns:
            Embedding vector if found, None otherwise
        """
        if not self._initialized:
            self.initialize()
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Try to get from vector table
            try:
                row_id = hash(entry_id) % (2**31)
                cursor.execute("""
                    SELECT embedding FROM memory_embeddings WHERE rowid = ?
                """, (row_id,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
            except Exception:
                pass
            
            return None
            
        except Exception as e:
            logger.error(
                "Failed to get embedding",
                extra={"entry_id": entry_id, "error": str(e)}
            )
            return None

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        """Get entry by ID.
        
        Args:
            entry_id: ID of the entry
            
        Returns:
            Entry dict if found, None otherwise
        """
        if not self._initialized:
            self.initialize()
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT id, content, content_type, source_file, created_at, updated_at, metadata
                FROM memory_entries WHERE id = ?
            """, (entry_id,))
            row = cursor.fetchone()
            
            if row is None:
                return None
                
            return {
                "id": row["id"],
                "content": row["content"],
                "content_type": row["content_type"],
                "source_file": row["source_file"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            }
            
        except Exception as e:
            logger.error(
                "Failed to get entry",
                extra={"entry_id": entry_id, "error": str(e)}
            )
            return None

    def count(self) -> int:
        """Count total entries in the store.
        
        Returns:
            Number of entries
        """
        if not self._initialized:
            self.initialize()
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) as count FROM memory_entries")
            row = cursor.fetchone()
            return row["count"] if row else 0
            
        except Exception as e:
            logger.error(
                "Failed to count entries",
                extra={"error": str(e)}
            )
            return 0

    def clear(self) -> None:
        """Clear all entries from the store."""
        if not self._initialized:
            self.initialize()
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM memory_entries")
            try:
                cursor.execute("DELETE FROM memory_embeddings")
            except Exception:
                pass  # vss table may not exist
            
            conn.commit()
            logger.info("VectorStore cleared")
            
        except Exception as e:
            logger.error(
                "Failed to clear VectorStore",
                extra={"error": str(e)}
            )
            raise

    def get_all_entries(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Get all entries with pagination.
        
        Args:
            limit: Maximum number of entries
            offset: Pagination offset
            
        Returns:
            List of entry dicts
        """
        if not self._initialized:
            self.initialize()
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT id, content, content_type, source_file, created_at, updated_at, metadata
                FROM memory_entries
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "content_type": row["content_type"],
                    "source_file": row["source_file"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                })
            
            return results
            
        except Exception as e:
            logger.error(
                "Failed to get all entries",
                extra={"error": str(e)}
            )
            return []


# Global vector store instance
_vector_store: VectorStore | None = None


def get_vector_store(db_path: str | None = None) -> VectorStore:
    """Get or create global vector store instance.
    
    Args:
        db_path: Path to database file (optional if already initialized)
        
    Returns:
        VectorStore instance
    """
    global _vector_store
    if _vector_store is None:
        if db_path is None:
            db_path = "x-agent.db"
        _vector_store = VectorStore(db_path)
        _vector_store.initialize()
    return _vector_store
