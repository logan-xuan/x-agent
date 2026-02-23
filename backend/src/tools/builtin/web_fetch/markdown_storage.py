"""Markdown Storage Manager.

Manages Markdown files and images for web content.
Stores content in workspace/web_content/{date}/{url_hash}.md
Images stored in workspace/web_content/{date}/images/{url_hash}/
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
import frontmatter
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MarkdownStorageManager:
    """Manage Markdown files and images for web content."""
    
    def __init__(self, workspace_path: str):
        """Initialize storage manager.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.workspace_path = Path(workspace_path)
        self.web_content_dir = self.workspace_path / "web_content"
        
        # Ensure base directory exists
        self.web_content_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            "MarkdownStorageManager initialized",
            extra={"web_content_dir": str(self.web_content_dir)}
        )
    
    def _get_date_dir(self, date: datetime) -> Path:
        """Get date-based directory path."""
        date_str = date.strftime("%Y-%m-%d")
        return self.web_content_dir / date_str
    
    def _compute_url_hash(self, url: str) -> str:
        """Compute MD5 hash of URL."""
        return hashlib.md5(url.encode()).hexdigest()
    
    async def save_content(
        self,
        url: str,
        title: str,
        body_html: str,
        images: list[dict],
        tables: list[dict],
        metadata: dict,
    ) -> tuple[str, str]:
        """Save content to Markdown file and download images.
        
        Args:
            url: Source URL
            title: Page title
            body_html: HTML content of main body
            images: List of image info dicts
            tables: List of table data dicts
            metadata: Additional metadata
            
        Returns:
            Tuple of (markdown_path, images_dir) relative paths
        """
        date = datetime.now()
        url_hash = self._compute_url_hash(url)
        date_dir = self._get_date_dir(date)
        
        # Create directories
        date_dir.mkdir(parents=True, exist_ok=True)
        images_dir = date_dir / "images" / url_hash
        images_dir.mkdir(parents=True, exist_ok=True)
        
        # Download and save images
        image_mapping = {}  # original_url -> local_path
        for i, img in enumerate(images):
            try:
                img_url = img.get("url")
                if not img_url:
                    continue
                
                # Download image
                from .http_client import HTTPClient
                http_client = HTTPClient()
                img_data = await http_client.download(img_url)
                
                if not img_data:
                    continue
                
                # Determine extension
                ext = self._guess_image_extension(img_data)
                filename = f"img{i+1:03d}.{ext}"
                local_path = images_dir / filename
                
                # Save image
                with open(local_path, "wb") as f:
                    f.write(img_data)
                
                # Map original URL to relative path
                rel_path = f"./images/{url_hash}/{filename}"
                image_mapping[img_url] = rel_path
                
                logger.debug(f"Downloaded image {i+1}: {filename}")
                
            except Exception as e:
                logger.warning(f"Failed to download image {img.get('url')}: {e}")
        
        # Convert HTML to Markdown
        markdown_body = self._html_to_markdown(body_html)
        
        # Replace image URLs with local paths
        for orig_url, local_path in image_mapping.items():
            # Escape special characters in URLs for regex
            escaped_url = re.escape(orig_url)
            markdown_body = re.sub(escaped_url, local_path, markdown_body)
        
        # Add tables as Markdown
        if tables:
            markdown_body += "\n\n## 表格数据\n\n"
            for i, table in enumerate(tables, 1):
                markdown_body += f"### 表格 {i}\n\n"
                if table.get("caption"):
                    markdown_body += f"**{table['caption']}**\n\n"
                markdown_body += self._table_to_markdown(table)
                markdown_body += "\n\n"
        
        # Build frontmatter metadata
        post_metadata = {
            "url": url,
            "url_hash": url_hash,
            "title": title,
            "fetched_at": date.isoformat(),
            "word_count": len(body_html.split()),
            "language": metadata.get("language", "auto"),
            "images_count": len(image_mapping),
            "tables_count": len(tables),
        }
        
        # Create post with frontmatter
        post = frontmatter.Post(markdown_body)
        post.metadata.update(post_metadata)
        
        # Save Markdown file
        md_file_path = date_dir / f"{url_hash}.md"
        with open(md_file_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        
        # Return relative paths
        rel_md_path = str(md_file_path.relative_to(self.workspace_path))
        rel_img_dir = str(images_dir.relative_to(self.workspace_path))
        
        logger.info(
            f"Saved content",
            extra={
                "markdown_path": rel_md_path,
                "images_dir": rel_img_dir,
                "image_count": len(image_mapping),
            }
        )
        
        return rel_md_path, rel_img_dir
    
    def _html_to_markdown(self, html: str) -> str:
        """Convert HTML to Markdown.
        
        Args:
            html: HTML string
            
        Returns:
            Markdown string
        """
        try:
            import html2text
            h = html2text.HTML2Text()
            h.body_width = 0  # Don't wrap text
            h.ignore_links = False
            h.ignore_images = False
            h.ignore_tables = True  # We handle tables separately
            return h.handle(html)
        except ImportError:
            logger.warning("html2text not installed, using fallback")
            # Simple fallback: just return HTML
            return html
    
    def _guess_image_extension(self, data: bytes) -> str:
        """Guess image file extension from magic bytes.
        
        Args:
            data: Image binary data
            
        Returns:
            File extension (without dot)
        """
        if data.startswith(b"\xff\xd8\xff"):
            return "jpg"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        elif data.startswith(b"GIF8"):
            return "gif"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "webp"
        else:
            return "jpg"  # Default
    
    def _table_to_markdown(self, table: dict) -> str:
        """Convert table data to Markdown format.
        
        Args:
            table: Table data dict
            
        Returns:
            Markdown table string
        """
        lines = []
        
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        
        if not headers and not rows:
            return ""
        
        # Header row
        if headers:
            lines.append("| " + " | ".join(str(h) for h in headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        
        # Data rows
        for row in rows:
            # Escape pipe characters
            escaped_row = [str(cell).replace("|", "\\|") for cell in row]
            lines.append("| " + " | ".join(escaped_row) + " |")
        
        return "\n".join(lines)
    
    async def cleanup_old_files(self, days_old: int = 3):
        """Clean up files older than specified days.
        
        Args:
            days_old: Delete files older than this many days
        """
        import shutil
        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        cleaned_count = 0
        
        if not self.web_content_dir.exists():
            return
        
        for date_dir in self.web_content_dir.iterdir():
            if not date_dir.is_dir():
                continue
            
            try:
                # Parse directory name as date
                dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d")
                
                if dir_date < cutoff_date:
                    # Delete old directory
                    shutil.rmtree(date_dir)
                    logger.info(f"Cleaned up old directory: {date_dir}")
                    cleaned_count += 1
                    
            except ValueError:
                # Not a date directory, skip
                continue
            except Exception as e:
                logger.warning(f"Failed to cleanup {date_dir}: {e}")
        
        logger.info(f"Cleaned up {cleaned_count} old directories")
    
    def read_markdown_file(self, markdown_path: str) -> Optional[frontmatter.Post]:
        """Read and parse a Markdown file.
        
        Args:
            markdown_path: Relative or absolute path to Markdown file
            
        Returns:
            Parsed post object or None
        """
        try:
            path = Path(markdown_path)
            if not path.is_absolute():
                path = self.workspace_path / path
            
            if not path.exists():
                logger.warning(f"Markdown file not found: {path}")
                return None
            
            return frontmatter.load(path)
        except Exception as e:
            logger.error(f"Failed to read Markdown file: {e}")
            return None
