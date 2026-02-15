"""Log parser for extracting and analyzing trace data from log files.

This module provides functionality to:
- Parse x-agent.log and prompt-llm.log files
- Filter logs by trace_id
- Build timeline and execution path from logs
- Aggregate related log entries
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logger import get_logger

logger = get_logger(__name__)


class LogEntry:
    """Represents a parsed log entry."""
    
    def __init__(self, raw_data: dict[str, Any]) -> None:
        self.raw_data = raw_data
        self.timestamp = raw_data.get('timestamp')
        self.level = raw_data.get('level')
        self.module = raw_data.get('module')
        self.message = raw_data.get('message', '')
        self.event = raw_data.get('event')
        self.trace_id = raw_data.get('trace_id')
        self.request_id = raw_data.get('request_id')
        self.session_id = raw_data.get('session_id')
        
        # Extract additional data from log entry
        self.data = {
            k: v for k, v in raw_data.items()
            if k not in ['timestamp', 'level', 'module', 'message', 'event', 
                        'trace_id', 'request_id', 'session_id']
        }
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp,
            'level': self.level,
            'module': self.module,
            'message': self.message,
            'event': self.event,
            'trace_id': self.trace_id,
            'request_id': self.request_id,
            'session_id': self.session_id,
            'data': self.data,
        }


class PromptLogEntry:
    """Represents a parsed LLM prompt log entry."""
    
    def __init__(self, raw_data: dict[str, Any]) -> None:
        self.raw_data = raw_data
        self.timestamp = raw_data.get('timestamp')
        self.session_id = raw_data.get('session_id')
        self.trace_id = raw_data.get('trace_id')
        self.provider = raw_data.get('provider')
        self.model = raw_data.get('model')
        self.latency_ms = raw_data.get('latency_ms')
        self.success = raw_data.get('success', True)
        self.request = raw_data.get('request', {})
        self.response = raw_data.get('response', '')
        self.token_usage = raw_data.get('token_usage')
        self.error = raw_data.get('error')
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp,
            'session_id': self.session_id,
            'trace_id': self.trace_id,
            'provider': self.provider,
            'model': self.model,
            'latency_ms': self.latency_ms,
            'success': self.success,
            'request': self.request,
            'response': self.response,
            'token_usage': self.token_usage,
            'error': self.error,
        }


class LogParser:
    """Parser for x-agent.log and prompt-llm.log files."""
    
    def __init__(self, log_dir: str = "logs") -> None:
        """Initialize log parser.
        
        Args:
            log_dir: Directory containing log files
        """
        self.log_dir = Path(log_dir)
        self.x_agent_log = self.log_dir / "x-agent.log"
        self.prompt_llm_log = self.log_dir / "prompt-llm.log"
    
    def parse_x_agent_logs(self, trace_id: str) -> list[LogEntry]:
        """Parse x-agent.log and filter by trace_id.
        
        Args:
            trace_id: Trace ID to filter logs
            
        Returns:
            List of parsed log entries matching the trace_id
        """
        if not self.x_agent_log.exists():
            logger.warning(f"Log file not found: {self.x_agent_log}")
            return []
        
        entries = []
        
        try:
            with open(self.x_agent_log, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        # Parse JSON log entry
                        data = json.loads(line)
                        
                        # Handle nested message field (some logs have double-encoded JSON)
                        if 'message' in data and isinstance(data['message'], str):
                            try:
                                message_data = json.loads(data['message'])
                                # Merge message data into main data
                                data.update(message_data)
                            except (json.JSONDecodeError, TypeError):
                                pass
                        
                        # Filter by trace_id
                        if data.get('trace_id') == trace_id:
                            entries.append(LogEntry(data))
                    
                    except json.JSONDecodeError:
                        # Skip malformed JSON lines
                        continue
        
        except Exception as e:
            logger.error(f"Error parsing x-agent log: {e}", exc_info=True)
        
        # Sort by timestamp
        entries.sort(key=lambda e: e.timestamp or '')
        
        return entries
    
    def parse_prompt_llm_logs(self, trace_id: str) -> list[PromptLogEntry]:
        """Parse prompt-llm.log and filter by trace_id.
        
        Args:
            trace_id: Trace ID to filter logs
            
        Returns:
            List of parsed prompt log entries matching the trace_id
        """
        if not self.prompt_llm_log.exists():
            logger.warning(f"Log file not found: {self.prompt_llm_log}")
            return []
        
        entries = []
        
        try:
            with open(self.prompt_llm_log, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        
                        # Filter by trace_id
                        if data.get('trace_id') == trace_id:
                            entries.append(PromptLogEntry(data))
                    
                    except json.JSONDecodeError:
                        continue
        
        except Exception as e:
            logger.error(f"Error parsing prompt-llm log: {e}", exc_info=True)
        
        # Sort by timestamp
        entries.sort(key=lambda e: e.timestamp or '')
        
        return entries
    
    def build_timeline(
        self,
        trace_id: str
    ) -> dict[str, Any]:
        """Build a timeline of events for a given trace_id.
        
        Args:
            trace_id: Trace ID to analyze
            
        Returns:
            Dictionary containing timeline and execution path
        """
        # Parse logs
        x_agent_logs = self.parse_x_agent_logs(trace_id)
        prompt_logs = self.parse_prompt_llm_logs(trace_id)
        
        # Build timeline
        timeline = []
        
        # Add x-agent log entries to timeline
        for entry in x_agent_logs:
            timeline.append({
                'timestamp': entry.timestamp,
                'source': 'x-agent',
                'module': entry.module,
                'event': entry.event or entry.message,
                'level': entry.level,
                'data': entry.data,
            })
        
        # Add prompt log entries to timeline
        for entry in prompt_logs:
            timeline.append({
                'timestamp': entry.timestamp,
                'source': 'prompt-llm',
                'module': 'llm',
                'event': 'LLM Request/Response',
                'level': 'info',
                'data': {
                    'provider': entry.provider,
                    'model': entry.model,
                    'latency_ms': entry.latency_ms,
                    'success': entry.success,
                    'token_usage': entry.token_usage,
                    'request_preview': self._preview_messages(entry.request.get('messages', [])),
                    'response_preview': entry.response[:200] if entry.response else None,
                },
            })
        
        # Sort timeline by timestamp
        timeline.sort(key=lambda e: e['timestamp'] or '')
        
        # Build execution path from timeline
        execution_path = self._build_execution_path(timeline)
        
        # Calculate total duration
        start_time = None
        end_time = None
        if timeline:
            start_time = timeline[0].get('timestamp')
            end_time = timeline[-1].get('timestamp')
        
        total_duration_ms = 0
        if start_time and end_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                total_duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
            except Exception:
                pass
        
        return {
            'trace_id': trace_id,
            'timeline': timeline,
            'execution_path': execution_path,
            'start_time': start_time,
            'end_time': end_time,
            'total_duration_ms': total_duration_ms,
        }
    
    def _preview_messages(self, messages: list[dict[str, str]], max_length: int = 100) -> str:
        """Generate a preview of messages array.
        
        Args:
            messages: List of message dictionaries
            max_length: Maximum length of preview
            
        Returns:
            Preview string
        """
        if not messages:
            return ''
        
        preview_parts = []
        for msg in messages[:3]:  # Show first 3 messages
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if len(content) > max_length:
                content = content[:max_length] + '...'
            preview_parts.append(f"{role}: {content}")
        
        if len(messages) > 3:
            preview_parts.append(f"... and {len(messages) - 3} more messages")
        
        return ' | '.join(preview_parts)
    
    def _build_execution_path(self, timeline: list[dict[str, Any]]) -> list[str]:
        """Build execution path from timeline events.
        
        Args:
            timeline: Sorted timeline of events
            
        Returns:
            List of module/function names in execution order
        """
        path = []
        seen = set()
        
        for event in timeline:
            module = event.get('module', '')
            event_name = event.get('event', '')
            
            # Extract function/method name from event
            if 'function_entry' in event_name or 'Entering' in event_name:
                # Extract function name
                func_name = event.get('data', {}).get('function')
                if func_name and func_name not in seen:
                    path.append(func_name)
                    seen.add(func_name)
            elif module and module not in seen:
                # Use module name
                path.append(module)
                seen.add(module)
        
        return path


def get_log_parser(log_dir: str = "logs") -> LogParser:
    """Get a LogParser instance.
    
    Args:
        log_dir: Directory containing log files
        
    Returns:
        LogParser instance
    """
    return LogParser(log_dir)
