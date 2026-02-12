import requests
from typing import Dict, Any
from pydantic import BaseModel, Field
from .base_tool import BaseTool


class WebSearchToolArgs(BaseModel):
    query: str = Field(description="The search query to execute")


class WebSearchTool(BaseTool):
    """Tool for performing web searches and retrieving results."""

    def __init__(self):
        super().__init__(
            name="web-search",
            description="Perform a web search to find information on a topic",
            args_schema=WebSearchToolArgs
        )

    def _run(self, query: str, **kwargs) -> str:
        """
        Execute a web search using DuckDuckGo API.

        Args:
            query: The search query to execute

        Returns:
            Search results as a string
        """
        try:
            # Using DuckDuckGo Instant Answer API (free and doesn't require API key)
            url = "https://api.duckduckgo.com/"
            params = {
                'q': query,
                'format': 'json',
                'no_html': '1',
                'skip_disambig': '1'
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Format the results
            results = []
            if data.get('Abstract'):
                results.append(f"Summary: {data['Abstract']}")
            if data.get('AbstractURL'):
                results.append(f"Source: {data['AbstractURL']}")

            if data.get('RelatedTopics'):
                topics = data['RelatedTopics'][:3]  # Limit to first 3 topics
                for topic in topics:
                    if 'Text' in topic and 'FirstURL' in topic:
                        results.append(f"- {topic['Text']}: {topic['FirstURL']}")

            if not results:
                return f"No clear results found for '{query}'. Try rephrasing your search."

            return "\n".join(results)

        except requests.exceptions.RequestException as e:
            return f"Error performing web search: {str(e)}"
        except Exception as e:
            return f"Unexpected error during web search: {str(e)}"