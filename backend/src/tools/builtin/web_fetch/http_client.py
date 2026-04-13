"""HTTP client for web content fetching.

Provides async HTTP request capabilities with:
- Custom User-Agent with rotation
- Timeout control
- Auto redirect
- SSL verification
- Anti-bot headers (referers, accept, etc.)
"""

import asyncio
import random

import httpx

from src.utils.logger import get_logger

logger = get_logger(__name__)


class HTTPClient:
    """Async HTTP client for web fetching with anti-bot capabilities."""

    # Realistic User-Agent pool to rotate and avoid detection
    USER_AGENTS = [
        # Chrome on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Firefox on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        # Safari on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        # Edge on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ]

    def __init__(
        self,
        timeout: int = 30,
        max_redirects: int = 5,
        verify_ssl: bool = True,
        rotate_user_agent: bool = True,
        max_retries: int = 1,
    ):
        """Initialize HTTP client.

        Args:
            timeout: Request timeout in seconds
            max_redirects: Maximum number of redirects to follow
            verify_ssl: Whether to verify SSL certificates
            rotate_user_agent: Whether to rotate User-Agent for each request
            max_retries: Number of retries for transient request errors
        """
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.verify_ssl = verify_ssl
        self.rotate_user_agent = rotate_user_agent
        self.max_retries = max(0, max_retries)

        logger.info(
            "HTTPClient initialized with anti-bot features",
            extra={
                "timeout": timeout,
                "max_redirects": max_redirects,
                "verify_ssl": verify_ssl,
                "rotate_user_agent": rotate_user_agent,
                "max_retries": self.max_retries,
            },
        )

    def _get_user_agent(self) -> str:
        """Get a random or default User-Agent.

        Returns:
            User-Agent string
        """
        if self.rotate_user_agent:
            return random.choice(self.USER_AGENTS)
        else:
            return self.USER_AGENTS[0]

    def _build_headers(self, user_agent: str | None = None) -> dict:
        """Build HTTP headers with realistic browser characteristics.

        Args:
            user_agent: Custom User-Agent string (optional)

        Returns:
            Headers dictionary
        """
        ua = user_agent or self._get_user_agent()

        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    async def fetch(
        self,
        url: str,
        timeout: int | None = None,
        headers: dict | None = None,
        user_agent: str | None = None,
    ) -> httpx.Response:
        """Fetch URL content.

        Args:
            url: URL to fetch
            timeout: Override default timeout
            headers: Custom headers
            user_agent: Custom User-Agent

        Returns:
            HTTP response

        Raises:
            httpx.HTTPError: On request failure
        """
        effective_timeout = timeout or self.timeout
        request_headers = self._build_headers(user_agent)
        if headers:
            request_headers.update(headers)

        logger.debug("Fetching URL", extra={"url": url, "timeout": effective_timeout})

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(effective_timeout),
                    max_redirects=self.max_redirects,
                    verify=self.verify_ssl,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(url, headers=request_headers)
                    response.raise_for_status()

                    logger.info(
                        "URL fetched successfully",
                        extra={
                            "url": url,
                            "status_code": response.status_code,
                            "content_length": len(response.content),
                            "attempt": attempt + 1,
                        },
                    )

                    return response
            except httpx.RequestError as exc:
                if attempt >= self.max_retries:
                    raise

                logger.warning(
                    "URL fetch failed with transient request error, retrying",
                    extra={
                        "url": url,
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(0)

    async def download(
        self,
        url: str,
        timeout: int = 10,
    ) -> bytes:
        """Download binary content (for images).

        Args:
            url: URL to download
            timeout: Download timeout

        Returns:
            Binary content
        """
        try:
            # Validate URL format
            if not url.startswith(("http://", "https://")):
                logger.debug(f"Invalid URL format (skipping): {url}")
                return b""

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                return response.content
        except httpx.RequestError as e:
            # Network error, DNS failure, etc.
            logger.debug(f"Download failed (network error): {url} - {type(e).__name__}")
            return b""
        except Exception as e:
            # Other errors
            logger.debug(f"Download failed: {url} - {type(e).__name__}: {str(e)[:100]}")
            return b""
