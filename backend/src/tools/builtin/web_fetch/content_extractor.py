"""Content Extractor for web pages.

Extracts main content, images, and tables from HTML.
Uses heuristics based on text density and link density.
"""

from bs4 import BeautifulSoup, Tag, NavigableString
from typing import Optional
import re
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContentExtractor:
    """Extract main content from HTML."""
    
    def __init__(self):
        """Initialize content extractor."""
        logger.info("ContentExtractor initialized")
    
    def extract_body(self, soup: BeautifulSoup) -> str:
        """Extract main body content as HTML.
        
        Uses heuristics to find the most relevant content container.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            HTML string of main content
        """
        # Remove unwanted elements first
        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.decompose()
        
        # Try to find article or main content containers
        candidates = []
        
        # Semantic tags
        for tag_name in ["article", "main"]:
            for element in soup.find_all(tag_name):
                score = self._calculate_content_score(element)
                if score > 0:
                    candidates.append((score, element))
        
        # Common content divs by class/id
        content_patterns = [
            r"content", r"article", r"post", r"entry", r"main",
            r"text", r"body", r"story", r"news"
        ]
        
        for div in soup.find_all("div"):
            # Check class and id attributes
            class_str = " ".join(div.get("class", []))
            id_str = div.get("id", "")
            
            is_content = any(
                re.search(pattern, class_str, re.I) or 
                re.search(pattern, id_str, re.I)
                for pattern in content_patterns
            )
            
            if is_content:
                score = self._calculate_content_score(div)
                if score > 0:
                    candidates.append((score, div))
        
        # Select best candidate
        if candidates:
            best_score, best_element = max(candidates, key=lambda x: x[0])
            logger.debug(f"Best content candidate score: {best_score}")
            return self._clean_element(best_element)
        
        # Fallback to body
        body = soup.find("body")
        if body:
            return self._clean_element(body)
        
        # Last resort: entire document
        return str(soup)
    
    def _calculate_content_score(self, element: Tag) -> int:
        """Calculate content quality score.
        
        Higher score = more likely to be main content.
        
        Args:
            element: HTML element
            
        Returns:
            Score (higher is better)
        """
        text = element.get_text(strip=True)
        
        # No text = no score
        if not text:
            return 0
        
        text_length = len(text)
        
        # Base score from text length
        score = text_length // 10
        
        # Bonus for semantic tags
        if element.name in ["article", "main", "section"]:
            score += 50
        
        # Penalty for high link density
        links_text = ""
        for a in element.find_all("a"):
            links_text += a.get_text(strip=True)
        
        if links_text:
            link_density = len(links_text) / text_length
            if link_density > 0.5:  # More than 50% links
                score -= int(score * link_density * 0.5)
        
        # Bonus for paragraphs
        p_count = len(element.find_all("p"))
        score += p_count * 10
        
        # Penalty for very short content
        if text_length < 200:
            score -= 50
        
        return max(0, score)
    
    def _clean_element(self, element: Tag) -> str:
        """Clean element and return as HTML string.
        
        Args:
            element: HTML element
            
        Returns:
            Cleaned HTML string
        """
        # Remove empty tags
        for tag in element.find_all():
            if not tag.get_text(strip=True) and tag.name not in ["br", "hr", "img"]:
                tag.decompose()
        
        return str(element)
    
    def extract_images(
        self,
        soup: BeautifulSoup,
        max_images: int = 20,
    ) -> list[dict]:
        """Extract image information.
        
        Args:
            soup: BeautifulSoup object
            max_images: Maximum number of images to extract
            
        Returns:
            List of image info dicts
        """
        images = []
        
        for img_tag in soup.find_all("img")[:max_images]:
            src = img_tag.get("src") or img_tag.get("data-src")
            if not src:
                continue
            
            # Skip tiny images (icons, ads)
            width = img_tag.get("width")
            height = img_tag.get("height")
            
            if width and int(width) < 50:
                continue
            if height and int(height) < 50:
                continue
            
            image_info = {
                "url": src,
                "alt": img_tag.get("alt", ""),
                "title": img_tag.get("title", ""),
            }
            
            if width:
                image_info["width"] = int(width)
            if height:
                image_info["height"] = int(height)
            
            # Mark first image as primary
            if len(images) == 0:
                image_info["is_primary"] = True
            else:
                image_info["is_primary"] = False
            
            images.append(image_info)
        
        logger.info(f"Extracted {len(images)} images")
        return images
    
    def extract_tables(self, soup: BeautifulSoup) -> list[dict]:
        """Extract table data.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            List of table data dicts
        """
        tables = []
        
        for table_tag in soup.find_all("table"):
            try:
                table_data = self._parse_table(table_tag)
                if table_data["rows"]:  # Only include non-empty tables
                    tables.append(table_data)
            except Exception as e:
                logger.warning(f"Failed to parse table: {e}")
        
        logger.info(f"Extracted {len(tables)} tables")
        return tables
    
    def _parse_table(self, table_tag: Tag) -> dict:
        """Parse single table.
        
        Args:
            table_tag: Table HTML element
            
        Returns:
            Table data dict
        """
        headers = []
        rows = []
        
        # Extract header
        header_row = table_tag.find("thead")
        if not header_row:
            header_row = table_tag.find("tr")
        
        if header_row:
            for cell in header_row.find_all(["th", "td"]):
                headers.append(cell.get_text(strip=True))
        
        # Extract data rows
        tbody = table_tag.find("tbody")
        data_rows = tbody.find_all("tr") if tbody else table_tag.find_all("tr")[1:]
        
        for row in data_rows:
            cells = [cell.get_text(strip=True) for cell in row.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        
        # Get caption if exists
        caption_tag = table_tag.find("caption")
        caption = caption_tag.get_text(strip=True) if caption_tag else None
        
        return {
            "headers": headers,
            "rows": rows,
            "caption": caption,
            "row_count": len(rows),
            "col_count": len(headers) if headers else (len(rows[0]) if rows else 0),
        }
