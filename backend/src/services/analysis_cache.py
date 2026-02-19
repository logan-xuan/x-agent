"""Cache service for trace analysis results.

Stores and retrieves trace analysis results to reduce LLM calls.
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from ..utils.logger import get_logger

logger = get_logger(__name__)


class AnalysisCache:
    """Manages caching of trace analysis results."""

    def __init__(self, cache_dir: str = "../../workspace/dev/Analysis"):
        """Initialize cache service.

        Args:
            cache_dir: Directory to store cached analysis results
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "AnalysisCache initialized",
            extra={'cache_dir': str(self.cache_dir.resolve())}
        )

    def _generate_filename(self, trace_id: str, focus_areas: Optional[list[str]] = None) -> str:
        """Generate filename for cached analysis based on trace_id and focus areas.

        Args:
            trace_id: Trace ID to analyze
            focus_areas: Optional focus areas for the analysis

        Returns:
            Filename for the cached analysis file
        """
        # Create a hash of focus areas to distinguish different analysis configurations
        if focus_areas:
            focus_str = "_".join(sorted(focus_areas))
            focus_hash = hashlib.md5(focus_str.encode()).hexdigest()[:8]
            return f"analysis_{trace_id}_{focus_hash}.md"
        else:
            return f"analysis_{trace_id}.md"

    def get_cached_analysis(self, trace_id: str, focus_areas: Optional[list[str]] = None) -> Optional[Dict[str, Any]]:
        """Retrieve cached analysis result if it exists.

        Args:
            trace_id: Trace ID to analyze
            focus_areas: Optional focus areas for the analysis

        Returns:
            Cached analysis result or None if not found
        """
        filename = self._generate_filename(trace_id, focus_areas)
        cache_file = self.cache_dir / filename

        if not cache_file.exists():
            logger.debug(
                "No cached analysis found",
                extra={
                    'trace_id': trace_id,
                    'focus_areas': focus_areas,
                    'cache_file': str(cache_file)
                }
            )
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract metadata and content from markdown
            lines = content.split('\n')
            metadata = {}
            content_start_idx = 0

            # Look for metadata in the format <!-- metadata --> at the start
            if len(lines) > 0 and lines[0].startswith('<!--') and '-->' in lines[0]:
                try:
                    meta_line = lines[0][4:].split('-->')[0].strip()  # Remove <!-- and -->
                    metadata = json.loads(meta_line)
                    content_start_idx = 1
                    # Skip empty line after metadata
                    if content_start_idx < len(lines) and lines[content_start_idx].strip() == '':
                        content_start_idx += 1
                except (json.JSONDecodeError, IndexError):
                    # If metadata parsing fails, treat the whole content as analysis
                    content_start_idx = 0

            analysis_content = '\n'.join(lines[content_start_idx:]) if content_start_idx < len(lines) else ''

            result = {
                'analysis': analysis_content,
                'insights': metadata.get('insights', []),
                'suggestions': metadata.get('suggestions', []),
                'cached_at': metadata.get('cached_at'),
                'trace_id': metadata.get('trace_id', trace_id),
                'focus_areas': metadata.get('focus_areas', focus_areas),
            }

            logger.info(
                "Retrieved cached analysis",
                extra={
                    'trace_id': trace_id,
                    'focus_areas': focus_areas,
                    'cache_file': str(cache_file),
                    'insights_count': len(result['insights']),
                    'suggestions_count': len(result['suggestions'])
                }
            )

            return result

        except Exception as e:
            logger.error(
                "Failed to read cached analysis",
                extra={
                    'trace_id': trace_id,
                    'focus_areas': focus_areas,
                    'cache_file': str(cache_file),
                    'error': str(e),
                },
                exc_info=True
            )
            return None

    def cache_analysis(
        self,
        trace_id: str,
        analysis_result: Dict[str, Any],
        focus_areas: Optional[list[str]] = None
    ) -> bool:
        """Store analysis result in cache.

        Args:
            trace_id: Trace ID analyzed
            analysis_result: Analysis result to cache
            focus_areas: Optional focus areas for the analysis

        Returns:
            True if successfully cached, False otherwise
        """
        filename = self._generate_filename(trace_id, focus_areas)
        cache_file = self.cache_dir / filename

        try:
            # Prepare metadata
            metadata = {
                'trace_id': trace_id,
                'focus_areas': focus_areas or [],
                'cached_at': datetime.now().isoformat(),
                'insights_count': len(analysis_result.get('insights', [])),
                'suggestions_count': len(analysis_result.get('suggestions', [])),
            }
            metadata.update({k: v for k, v in analysis_result.items()
                           if k in ['insights', 'suggestions']})

            # Create markdown content with embedded metadata
            metadata_json = json.dumps(metadata, ensure_ascii=False)
            markdown_content = f"<!-- {metadata_json} -->\n\n{analysis_result.get('analysis', '')}"

            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)

            logger.info(
                "Analysis cached successfully",
                extra={
                    'trace_id': trace_id,
                    'focus_areas': focus_areas,
                    'cache_file': str(cache_file),
                    'insights_count': len(analysis_result.get('insights', [])),
                    'suggestions_count': len(analysis_result.get('suggestions', []))
                }
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to cache analysis",
                extra={
                    'trace_id': trace_id,
                    'focus_areas': focus_areas,
                    'cache_file': str(cache_file),
                    'error': str(e),
                },
                exc_info=True
            )
            return False

    def delete_cached_analysis(self, trace_id: str, focus_areas: Optional[list[str]] = None) -> bool:
        """Delete cached analysis for a trace.

        Args:
            trace_id: Trace ID to delete cache for
            focus_areas: Optional focus areas for the analysis

        Returns:
            True if successfully deleted or didn't exist, False if deletion failed
        """
        filename = self._generate_filename(trace_id, focus_areas)
        cache_file = self.cache_dir / filename

        if not cache_file.exists():
            logger.debug(
                "No cached analysis to delete",
                extra={
                    'trace_id': trace_id,
                    'focus_areas': focus_areas,
                    'cache_file': str(cache_file)
                }
            )
            return True

        try:
            cache_file.unlink()  # Remove the file
            logger.info(
                "Deleted cached analysis",
                extra={
                    'trace_id': trace_id,
                    'focus_areas': focus_areas,
                    'cache_file': str(cache_file)
                }
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to delete cached analysis",
                extra={
                    'trace_id': trace_id,
                    'focus_areas': focus_areas,
                    'cache_file': str(cache_file),
                    'error': str(e),
                },
                exc_info=True
            )
            return False

    def clear_all_cache(self) -> int:
        """Clear all cached analysis files.

        Returns:
            Number of files deleted
        """
        files = list(self.cache_dir.glob("analysis_*.md"))
        deleted_count = 0

        for file_path in files:
            try:
                file_path.unlink()
                deleted_count += 1
            except Exception as e:
                logger.error(
                    "Failed to delete cached analysis file",
                    extra={
                        'cache_file': str(file_path),
                        'error': str(e),
                    },
                    exc_info=True
                )

        logger.info(
            "Cleared all analysis cache",
            extra={'files_deleted': deleted_count}
        )

        return deleted_count


# Global instance
_analysis_cache: Optional[AnalysisCache] = None


def get_analysis_cache(cache_dir: str = "../../workspace/dev/Analysis") -> AnalysisCache:
    """Get or create analysis cache instance.

    Args:
        cache_dir: Directory to store cached analysis results

    Returns:
        AnalysisCache instance
    """
    global _analysis_cache

    if _analysis_cache is None:
        _analysis_cache = AnalysisCache(cache_dir)

    return _analysis_cache