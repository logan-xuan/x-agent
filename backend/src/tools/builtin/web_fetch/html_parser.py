"""HTML Parser using BeautifulSoup.

Provides HTML parsing capabilities with:
- DOM tree parsing
- Tag extraction
- Text cleaning
"""

from bs4 import BeautifulSoup, Tag
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HTMLParser:
    """Parse HTML content."""
    
    def __init__(self, parser: str = "lxml"):
        """Initialize HTML parser.
        
        Args:
            parser: Parser to use (lxml, html5lib, etc.)
        """
        self.parser = parser
        logger.info(f"HTMLParser initialized with parser: {parser}")
    
    def parse(self, html_content: str) -> BeautifulSoup:
        """Parse HTML content.
        
        Args:
            html_content: Raw HTML string
            
        Returns:
            BeautifulSoup object
        """
        soup = BeautifulSoup(html_content, self.parser)
        return soup
    
    def remove_unwanted_tags(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Remove script, style, and other unwanted tags.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Cleaned BeautifulSoup object
        """
        unwanted_tags = ["script", "style", "noscript", "iframe", "svg"]
        
        for tag_name in unwanted_tags:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        
        return soup
    
    def get_title(self, soup: BeautifulSoup) -> str:
        """Extract page title.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Page title
        """
        # Try <title> tag first
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            return title_tag.string.strip()
        
        # Try Open Graph title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()
        
        # Try <h1> tag
        h1_tag = soup.find("h1")
        if h1_tag:
            return h1_tag.get_text(strip=True)
        
        return ""
    
    def get_meta_description(self, soup: BeautifulSoup) -> str:
        """Get meta description.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Meta description
        """
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return meta_desc["content"].strip()
        return ""
    
    def get_language(self, soup: BeautifulSoup) -> Optional[str]:
        """Detect page language.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Language code (e.g., 'zh-CN', 'en')
        """
        # Check <html lang="">
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            return html_tag["lang"]
        
        # Check meta language
        meta_lang = soup.find("meta", attrs={"http-equiv": "Content-Language"})
        if meta_lang and meta_lang.get("content"):
            return meta_lang["content"]
        
        return None
