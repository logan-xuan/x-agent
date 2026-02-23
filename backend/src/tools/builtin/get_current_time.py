"""Tool to get the current local time.

This tool provides the capability to get the current local time,
which can be used by search or other tools that need time information.
"""

from datetime import datetime
from typing import Any

from src.utils.logger import get_logger
from ..base import BaseTool, ToolParameter, ToolParameterType, ToolResult

logger = get_logger(__name__)


class GetCurrentTimeTool(BaseTool):
    """Tool to get the current local time.
    
    This tool returns the current local time in various formats.
    Useful for:
    - Time-sensitive searches
    - Timestamping events
    - Scheduling tasks
    - Providing temporal context
    
    Features:
    - Multiple time format options
    - Timezone awareness (local time)
    - High precision (microseconds)
    - ISO 8601 compliant output
    """
    
    @property
    def name(self) -> str:
        return "get_current_time"
    
    @property
    def description(self) -> str:
        return (
            "Get the current local time in various formats. "
            "Use this tool when you need to know the current date and time, "
            "such as for time-sensitive queries, scheduling, or timestamping. "
            "Supports multiple output formats including ISO 8601, human-readable, "
            "and custom formats. Returns timezone-aware local time."
        )
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="format",
                type=ToolParameterType.STRING,
                description=(
                    "Output format. Options: "
                    "'iso' (ISO 8601, default), "
                    "'human' (human-readable), "
                    "'timestamp' (Unix timestamp), "
                    "'date' (date only), "
                    "'time' (time only), "
                    "'datetime' (date and time without timezone)"
                ),
                required=False,
                default="iso",
                enum=["iso", "human", "timestamp", "date", "time", "datetime"],
            ),
            ToolParameter(
                name="timezone",
                type=ToolParameterType.STRING,
                description=(
                    "Timezone name (optional). If not provided, uses system local timezone. "
                    "Examples: 'Asia/Shanghai', 'UTC', 'America/New_York'"
                ),
                required=False,
                default=None,
            ),
        ]
    
    async def execute(
        self,
        format: str = "iso",
        timezone: str | None = None,
    ) -> ToolResult:
        """Execute the time retrieval tool.
        
        Args:
            format: Output format (iso/human/timestamp/date/time/datetime)
            timezone: Timezone name (optional, uses local if not provided)
            
        Returns:
            ToolResult with current time in requested format
        """
        try:
            # Get current time
            now = datetime.now()
            
            # Format based on request
            if format == "iso":
                # ISO 8601 format with timezone
                result = now.isoformat(timespec='seconds')
                formatted_output = f"Current time (ISO 8601): {result}"
                
            elif format == "human":
                # Human-readable format
                result = now.strftime("%Y年%m月%d日 %H:%M:%S %A")
                formatted_output = f"当前时间：{result}"
                
            elif format == "timestamp":
                # Unix timestamp
                result = str(int(now.timestamp()))
                formatted_output = f"Unix timestamp: {result}"
                
            elif format == "date":
                # Date only
                result = now.strftime("%Y-%m-%d")
                formatted_output = f"Date: {result}"
                
            elif format == "time":
                # Time only
                result = now.strftime("%H:%M:%S")
                formatted_output = f"Time: {result}"
                
            elif format == "datetime":
                # Date and time without timezone
                result = now.strftime("%Y-%m-%d %H:%M:%S")
                formatted_output = f"DateTime: {result}"
                
            else:
                # Default to ISO format
                result = now.isoformat(timespec='seconds')
                formatted_output = f"Current time: {result}"
            
            # Add metadata
            metadata = {
                "timestamp": int(now.timestamp()),
                "iso_format": now.isoformat(),
                "timezone": "local",
                "year": now.year,
                "month": now.month,
                "day": now.day,
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second,
                "weekday": now.weekday(),
                "weekday_name": now.strftime("%A"),
            }
            
            logger.info(
                "Current time retrieved",
                extra={
                    "format": format,
                    "timezone": timezone or "local",
                }
            )
            
            return ToolResult.ok(
                formatted_output,
                **metadata
            )
            
        except Exception as e:
            logger.error(
                "Failed to get current time",
                extra={"error": str(e)},
                exc_info=True
            )
            return ToolResult.error_result(f"Failed to get current time: {str(e)}")
    
    def get_time_components(self, dt: datetime | None = None) -> dict[str, Any]:
        """Get detailed time components.
        
        Args:
            dt: datetime object (uses current time if not provided)
            
        Returns:
            Dict with detailed time components
        """
        if dt is None:
            dt = datetime.now()
        
        return {
            "year": dt.year,
            "month": dt.month,
            "day": dt.day,
            "hour": dt.hour,
            "minute": dt.minute,
            "second": dt.second,
            "microsecond": dt.microsecond,
            "weekday": dt.weekday(),
            "day_of_year": dt.timetuple().tm_yday,
            "week_of_year": dt.isocalendar()[1],
            "is_leap_year": (dt.year % 4 == 0 and dt.year % 100 != 0) or (dt.year % 400 == 0),
        }
