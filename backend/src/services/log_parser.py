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
                    'full_request': entry.request,  # Include full request data
                    'full_response': entry.response,  # Include full response data
                },
            })

        # Enhance timeline with special operation detection and enriched metadata
        timeline = self._enrich_timeline_data(timeline)
        
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

    def _enrich_timeline_data(self, timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich timeline data with special operation detection and detailed metadata.

        Detects and enhances special operations like tool calls, skill calls, commands,
        memory operations, ReAct loops, and Plan modes with detailed metadata.

        Args:
            timeline: Sorted timeline of events

        Returns:
            Enriched timeline with additional metadata for special operations
        """
        enriched_timeline = []

        for event in timeline:
            module = event.get('module', '').lower()
            event_name = event.get('event', '').lower()
            data = event.get('data', {})

            # Enhance LLM event with full request/response
            if event.get('source') == 'prompt-llm':
                # Already enriched in build_timeline method
                enriched_timeline.append(event)
                continue

            # Detect and enrich different types of operations
            enhanced_event = event.copy()
            enhanced_data = data.copy()

            # Detect tool calls
            if ('tool' in module and 'call' in event_name) or \
               any(key in data for key in ['tool_name', 'tool_call', 'tool_args']) or \
               'run_tool' in event_name or 'execute_tool' in event_name:

                enhanced_data['operation_type'] = 'tool_call'
                enhanced_data['tool_name'] = data.get('tool_name') or data.get('name') or 'unknown'
                enhanced_data['tool_args'] = data.get('arguments') or data.get('tool_args')
                enhanced_data['result'] = data.get('result')

                # Add timing information if available
                if data.get('duration_ms'):
                    enhanced_data['duration_ms'] = data.get('duration_ms')
                if data.get('start_time'):
                    enhanced_data['start_time'] = data.get('start_time')
                if data.get('end_time'):
                    enhanced_data['end_time'] = data.get('end_time')

            # Detect skill calls
            elif ('skill' in module and 'call' in event_name) or \
                 'skill_call' in event_name or 'execute_skill' in event_name or \
                 data.get('skill_name'):

                enhanced_data['operation_type'] = 'skill_call'
                enhanced_data['skill_name'] = data.get('skill_name') or data.get('name') or 'unknown'
                enhanced_data['skill_args'] = data.get('arguments') or data.get('args')
                enhanced_data['result'] = data.get('result')

            # Detect command execution
            elif ('command' in event_name) or ('terminal' in module) or \
                 any(key in data for key in ['command', 'cmd', 'shell_command']) or \
                 'execute' in event_name:

                enhanced_data['operation_type'] = 'command'
                enhanced_data['command'] = data.get('command') or data.get('cmd') or data.get('shell_command')
                enhanced_data['command_output'] = data.get('output')
                enhanced_data['command_error'] = data.get('error')
                enhanced_data['success'] = data.get('success', True)

            # Detect memory operations
            elif ('memory' in module and any(op in event_name for op in ['store', 'save', 'create', 'update'])) or \
                 any(key in data for key in ['memory_store', 'memory_save', 'memory_create']) or \
                 ('memory' in module and 'write' in event_name):

                enhanced_data['operation_type'] = 'memory_store'
                enhanced_data['memory_type'] = data.get('memory_type') or 'memory_entry'
                enhanced_data['memory_content'] = data.get('content') or data.get('data')
                enhanced_data['memory_id'] = data.get('id')

            elif ('memory' in module and 'query' in event_name) or \
                 ('memory' in module and 'search' in event_name) or \
                 any(key in data for key in ['memory_query', 'memory_search', 'memory_get']) or \
                 ('vector_store' in module):

                enhanced_data['operation_type'] = 'memory_query'
                enhanced_data['query'] = data.get('query') or data.get('search_term')
                enhanced_data['results_count'] = data.get('results_count') or data.get('count')
                enhanced_data['query_results'] = data.get('results')

            # Detect ReAct loop operations
            elif any(keyword in event_name for keyword in ['react', 'think', 'observe', 'act', 'reason']) or \
                 any(keyword in module for keyword in ['react', 'reasoning']):

                enhanced_data['operation_type'] = 'react_loop'
                enhanced_data['step_type'] = data.get('step_type') or 'think'  # think, observe, act
                enhanced_data['thought'] = data.get('thought') or data.get('reasoning')
                enhanced_data['action'] = data.get('action')
                enhanced_data['observation'] = data.get('observation')

            # Detect Plan Mode operations
            elif any(keyword in event_name for keyword in ['plan', 'planning', 'generate_plan', 'execute_plan']) or \
                 any(keyword in module for keyword in ['plan', 'planner']):

                enhanced_data['operation_type'] = 'plan_mode'
                enhanced_data['plan_step'] = data.get('step')
                enhanced_data['plan_action'] = data.get('action') or data.get('activity')
                enhanced_data['plan_status'] = data.get('status')

            # Update event with enhanced data
            enhanced_event['data'] = enhanced_data
            enriched_timeline.append(enhanced_event)

        return enriched_timeline


def get_log_parser(log_dir: str = "logs") -> LogParser:
    """Get a LogParser instance.
    
    Args:
        log_dir: Directory containing log files
        
    Returns:
        LogParser instance
    """
    return LogParser(log_dir)
