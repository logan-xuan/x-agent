"""Fetch web content tool for X-Agent.

Provides comprehensive web content fetching with:
- HTML parsing and content extraction
- Image download and local storage
- Table data extraction
- Markdown + SQLite hybrid storage (72h TTL)
- Batch URL processing
"""

import json
from pathlib import Path
from typing import Any, Optional
import asyncio

from ..base import BaseTool, ToolResult, ToolParameter, ToolParameterType
from .web_fetch.http_client import HTTPClient
from .web_fetch.html_parser import HTMLParser
from .web_fetch.content_extractor import ContentExtractor
from .web_fetch.markdown_storage import MarkdownStorageManager
from .web_fetch.sqlite_index import SQLiteIndexManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FetchWebContentTool(BaseTool):
    """Fetch and analyze web page content.
    
    Features:
    - Extract title, main content, images, tables
    - Store content as Markdown files
    - SQLite index with 72h TTL and LRU management
    - Batch URL processing (up to 10 URLs)
    - Independent and portable component
    
    Usage Scenarios:
    - Research specific webpages
    - Gather information for reports
    - Extract data from tables
    - Monitor website changes
    - Batch processing multiple URLs
    """
    
    def __init__(self, workspace_path: Optional[str] = None):
        """Initialize tool.
        
        Args:
            workspace_path: Path to workspace directory. If None, loads from x-agent.yaml config.
        """
        if workspace_path is None:
            # Load workspace path from configuration
            try:
                import sys
                from pathlib import Path as SysPath
                
                # Add backend/src to path temporarily for config loading
                backend_src = str(SysPath(__file__).parent.parent.parent)
                if backend_src not in sys.path:
                    sys.path.insert(0, backend_src)
                
                from config.loader import load_config
                from config.models import Config
                
                # Find and load x-agent.yaml
                config_file = SysPath(__file__).parent.parent.parent.parent / "x-agent.yaml"
                config = load_config(config_file)
                
                # Extract workspace path from config
                if config.workspace and config.workspace.path:
                    workspace_path = Path(config.workspace.path).expanduser().resolve()
                else:
                    workspace_path = Path.cwd() / "workspace"
                
                # Remove temporary path
                if backend_src in sys.path:
                    sys.path.remove(backend_src)
                    
            except Exception as e:
                logger.warning(f"Failed to load workspace from config, using default: {e}")
                workspace_path = Path.cwd() / "workspace"
        else:
            workspace_path = Path(workspace_path)
        
        self.workspace_path = workspace_path
        # Enable User-Agent rotation to avoid anti-bot detection
        self._http_client = HTTPClient(rotate_user_agent=True)
        self._html_parser = HTMLParser()
        self._extractor = ContentExtractor()
        self._markdown_storage = MarkdownStorageManager(str(self.workspace_path))
        self._sqlite_index = SQLiteIndexManager()
        
        logger.info(
            "FetchWebContentTool initialized",
            extra={"workspace_path": str(self.workspace_path)}
        )
    
    @property
    def name(self) -> str:
        return "fetch_web_content"
    
    @property
    def description(self) -> str:
        return (
            "Fetch and analyze web page content from a given URL. "
            "Extracts title, main text, images, tables, and other structured data. "
            "Content is stored as Markdown files with SQLite index (72h TTL). "
            "Supports batch fetching of up to 10 URLs concurrently. "
            "Returns file paths and metadata. "
            "Use this tool when you need to read or analyze specific webpages."
        )
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="url",
                type=ToolParameterType.STRING,
                description="The URL to fetch content from. Must be a valid HTTP/HTTPS URL.",
                required=False,  # Optional for batch mode
            ),
            ToolParameter(
                name="batch_urls",
                type=ToolParameterType.ARRAY,
                description="List of URLs to fetch (up to 10). Use for batch processing.",
                required=False,
            ),
            ToolParameter(
                name="max_images",
                type=ToolParameterType.INTEGER,
                description="Maximum number of images to extract. Default is 20, set to 0 to disable.",
                required=False,
                default=20,
            ),
            ToolParameter(
                name="extract_tables",
                type=ToolParameterType.BOOLEAN,
                description="Whether to extract table data. Default is True.",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="use_cache",
                type=ToolParameterType.BOOLEAN,
                description="Whether to use SQLite cache if available. Default is True.",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="timeout",
                type=ToolParameterType.INTEGER,
                description="Request timeout in seconds. Default is 30.",
                required=False,
                default=30,
            ),
        ]
    
    async def execute(
        self,
        url: Optional[str] = None,
        batch_urls: Optional[list[str]] = None,
        max_images: int = 20,
        extract_tables: bool = True,
        use_cache: bool = True,
        timeout: int = 30,
        **kwargs,
    ) -> ToolResult:
        """Execute the web content fetching tool.
        
        Args:
            url: Single URL to fetch
            batch_urls: List of URLs for batch processing
            max_images: Maximum images to extract
            extract_tables: Whether to extract tables
            use_cache: Whether to use cache
            timeout: Request timeout
            
        Returns:
            Tool result
        """
        try:
            # Single URL mode
            if url and not batch_urls:
                result = await self._fetch_single_url(
                    url=url,
                    max_images=max_images,
                    extract_tables=extract_tables,
                    use_cache=use_cache,
                    timeout=timeout,
                )
                
                return ToolResult.ok(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    **result,
                )
            
            # Batch mode
            elif batch_urls:
                results = await self._fetch_batch_urls(
                    urls=batch_urls,
                    max_images=max_images,
                    extract_tables=extract_tables,
                    use_cache=use_cache,
                    timeout=timeout,
                )
                
                return ToolResult.ok(
                    json.dumps(results, ensure_ascii=False, indent=2),
                    **results,
                )
            
            else:
                return ToolResult.error_result(
                    "Either 'url' or 'batch_urls' must be provided"
                )
                
        except Exception as e:
            logger.error(f"Failed to fetch web content: {e}", exc_info=True)
            return ToolResult.error_result(str(e))
    
    async def _fetch_single_url(
        self,
        url: str,
        max_images: int,
        extract_tables: bool,
        use_cache: bool,
        timeout: int,
    ) -> dict:
        """Fetch a single URL.
        
        Args:
            url: URL to fetch
            max_images: Maximum images
            extract_tables: Extract tables flag
            use_cache: Use cache flag
            timeout: Timeout
            
        Returns:
            Result dictionary
        """
        import time
        start_time = time.time()
        
        # Step 1: Check cache/index
        if use_cache:
            index_entry = await self._sqlite_index.get_index(url)
            if index_entry:
                logger.info(f"Cache hit for {url}")
                
                # Read Markdown file using absolute path
                abs_markdown_path = str(self.workspace_path / index_entry["markdown_path"])
                post = self._markdown_storage.read_markdown_file(abs_markdown_path)
                
                if post:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    return {
                        "success": True,
                        "url": url,
                        "from_cache": True,
                        "title": post.metadata.get("title", ""),
                        "body": f"[Markdown content saved to {abs_markdown_path}]",
                        "word_count": post.metadata.get("word_count", 0),
                        "metadata": {
                            "markdown_path": abs_markdown_path,
                            "images_dir": str(self.workspace_path / index_entry["images_dir"]),
                            "fetched_at": index_entry["fetched_at"],
                            "response_time_ms": elapsed_ms,
                            "cache_hit": True,
                        },
                    }
        
        # Step 2: Validate URL
        if not self._validate_url(url):
            return {
                "success": False,
                "url": url,
                "error": "Invalid URL format",
            }
        
        # Step 3: HTTP request
        try:
            response = await self._http_client.fetch(url, timeout=timeout)
            html_content = response.text
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            return {
                "success": False,
                "url": url,
                "error": f"HTTP request failed: {str(e)}",
            }
        
        # Step 4: Parse HTML
        soup = self._html_parser.parse(html_content)
        soup = self._html_parser.remove_unwanted_tags(soup)
        
        # Step 5: Extract content
        title = self._html_parser.get_title(soup)
        body_html = self._extractor.extract_body(soup)
        images = self._extractor.extract_images(soup, max_images=max_images)
        tables = self._extractor.extract_tables(soup) if extract_tables else []
        language = self._html_parser.get_language(soup)
        
        # Step 6: Save to Markdown files
        try:
            rel_markdown_path, rel_images_dir = await self._markdown_storage.save_content(
                url=url,
                title=title,
                body_html=body_html,
                images=images,
                tables=tables,
                metadata={"status_code": response.status_code},
            )
            
            # Convert to absolute paths for consistency
            markdown_path = str(self.workspace_path / rel_markdown_path)
            images_dir = str(self.workspace_path / rel_images_dir)
            
            # Add to SQLite index (72h TTL) with absolute paths
            await self._sqlite_index.add_index(
                url=url,
                markdown_path=rel_markdown_path,  # Store relative path in index
                images_dir=rel_images_dir,
                title=title,
                word_count=len(body_html.split()),
                language=language,
                ttl_hours=72,
            )
            
            logger.info(f"Saved to {markdown_path}")
            
        except Exception as e:
            logger.error(f"Failed to save content: {e}")
            return {
                "success": False,
                "url": url,
                "error": f"Content save failed: {str(e)}",
            }
        
        # Step 7: Build response
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        return {
            "success": True,
            "url": url,
            "final_url": str(response.url),
            "title": title,
            "body": f"[Markdown content saved to {markdown_path}]",
            "word_count": len(body_html.split()),
            "language": language,
            "metadata": {
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "response_time_ms": elapsed_ms,
                "markdown_path": markdown_path,
                "images_dir": images_dir,
                "images_count": len(images),
                "tables_count": len(tables),
                "cache_hit": False,
            },
        }
    
    async def _fetch_batch_urls(
        self,
        urls: list[str],
        max_images: int,
        extract_tables: bool,
        use_cache: bool,
        timeout: int,
    ) -> dict:
        """Fetch multiple URLs concurrently.
        
        Args:
            urls: List of URLs
            max_images: Maximum images per URL
            extract_tables: Extract tables flag
            use_cache: Use cache flag
            timeout: Timeout
            
        Returns:
            Batch result dictionary
        """
        import time
        start_time = time.time()
        
        # Limit to 10 URLs
        if len(urls) > 10:
            urls = urls[:10]
        
        # Create tasks with semaphore (limit concurrency to 5)
        semaphore = asyncio.Semaphore(5)
        
        async def limited_fetch(url: str):
            async with semaphore:
                return await self._fetch_single_url(
                    url=url,
                    max_images=max_images,
                    extract_tables=extract_tables,
                    use_cache=use_cache,
                    timeout=timeout,
                )
        
        # Execute concurrently
        tasks = [limited_fetch(url) for url in urls]
        results = await asyncio.gather(*tasks)
        
        # Aggregate statistics
        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]
        cached = [r for r in results if r.get("from_cache")]
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        return {
            "success": len(successful) > 0,
            "batch_mode": True,
            "total_urls": len(urls),
            "successful_count": len(successful),
            "failed_count": len(failed),
            "cached_count": len(cached),
            "results": results,
            "total_time_ms": elapsed_ms,
            "errors": [r.get("error") for r in failed if r.get("error")],
        }
    
    def _validate_url(self, url: str) -> bool:
        """Validate URL format.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid
        """
        from urllib.parse import urlparse
        
        try:
            parsed = urlparse(url)
            
            # Only allow HTTP and HTTPS
            if parsed.scheme not in ["http", "https"]:
                return False
            
            # Must have hostname
            if not parsed.hostname:
                return False
            
            # Block private IP ranges (basic check)
            hostname = parsed.hostname
            if hostname in ["localhost", "127.0.0.1"]:
                return False
            
            return True
            
        except Exception:
            return False
