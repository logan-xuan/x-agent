"""Flow graph builder for trace visualization.

Combines log data and code structure to generate React Flow compatible graphs.
"""

from typing import Any, Literal
from pathlib import Path

from .log_parser import get_log_parser
from .code_analyzer import get_code_analyzer
from ..utils.logger import get_logger

logger = get_logger(__name__)

DetailLevel = Literal["high", "medium", "detailed"]


class FlowNode:
    """React Flow node."""
    
    def __init__(
        self,
        node_id: str,
        node_type: str,
        label: str,
        data: dict[str, Any],
        position: dict[str, float],
    ):
        self.id = node_id
        self.type = node_type
        self.label = label
        self.data = data
        self.position = position
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'type': self.type,
            'data': {
                'label': self.label,
                **self.data,
            },
            'position': self.position,
        }


class FlowEdge:
    """React Flow edge."""
    
    def __init__(
        self,
        edge_id: str,
        source: str,
        target: str,
        label: str | None = None,
        animated: bool = False,
        edge_type: str = "default",
    ):
        self.id = edge_id
        self.source = source
        self.target = target
        self.label = label
        self.animated = animated
        self.type = edge_type
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'id': self.id,
            'source': self.source,
            'target': self.target,
            'type': self.type,
        }
        if self.label:
            result['label'] = self.label
        if self.animated:
            result['animated'] = True
        return result


class FlowBuilder:
    """Builds React Flow graphs from trace data."""
    
    # Node type mapping based on module paths and operation types
    NODE_TYPE_MAP = {
        'api': 'api',
        'middleware': 'middleware',
        'agent': 'agent',
        'core.agent': 'agent',
        'llm': 'llm',
        'router': 'llm',
        'memory': 'memory',
        'vector_store': 'memory',
        'context_builder': 'memory',
        'service': 'service',
        'plugin': 'plugin',
        'tool': 'tool',
        'skill': 'skill',
        'command': 'command',
        'react': 'react_loop',
        'reasoning': 'react_loop',
        'plan': 'plan_mode',
        'planner': 'plan_mode',
    }
    
    # Layout configuration
    NODE_WIDTH = 250
    NODE_HEIGHT = 100
    HORIZONTAL_SPACING = 100
    VERTICAL_SPACING = 120
    
    def __init__(self, log_dir: str = "logs", src_dir: str = "src"):
        """Initialize flow builder.
        
        Args:
            log_dir: Directory containing log files
            src_dir: Source code directory for code analysis
        """
        self.log_parser = get_log_parser(log_dir)
        
        # Resolve src_dir path
        backend_dir = Path(__file__).parent.parent.parent
        resolved_src_dir = (backend_dir / src_dir).resolve()
        self.code_analyzer = get_code_analyzer(str(resolved_src_dir))
        
        logger.info(
            "FlowBuilder initialized",
            extra={
                'log_dir': log_dir,
                'src_dir': str(resolved_src_dir),
            }
        )
    
    def build_flow(
        self,
        trace_id: str,
        detail_level: DetailLevel = "high",
    ) -> dict[str, Any]:
        """Build flow graph for a trace.
        
        Args:
            trace_id: Trace ID to build flow for
            detail_level: Level of detail (high, medium, detailed)
                - high: Show only major steps (API, Agent, LLM)
                - medium: Include middleware and services
                - detailed: Show all events including utilities
        
        Returns:
            Dictionary with nodes, edges, and metadata
        """
        logger.info(
            f"Building flow graph",
            extra={
                'trace_id': trace_id,
                'detail_level': detail_level,
            }
        )
        
        # Get timeline data
        timeline_data = self.log_parser.build_timeline(trace_id)
        timeline = timeline_data.get('timeline', [])
        
        if not timeline:
            logger.warning(f"No timeline data found for trace_id={trace_id}")
            return {
                'nodes': [],
                'edges': [],
                'metadata': {
                    'trace_id': trace_id,
                    'error': 'No data found for this trace_id',
                }
            }
        
        # Filter events based on detail level
        filtered_timeline = self._filter_timeline(timeline, detail_level)
        
        # Build nodes
        nodes = self._build_nodes(filtered_timeline, detail_level)
        
        # Build edges
        edges = self._build_edges(nodes, filtered_timeline)
        
        # Apply layout
        self._apply_layout(nodes, filtered_timeline)
        
        # Build metadata
        metadata = self._build_metadata(trace_id, timeline_data, nodes, edges)
        
        logger.info(
            f"Flow graph built successfully",
            extra={
                'trace_id': trace_id,
                'node_count': len(nodes),
                'edge_count': len(edges),
            }
        )
        
        return {
            'nodes': [node.to_dict() for node in nodes],
            'edges': [edge.to_dict() for edge in edges],
            'metadata': metadata,
        }
    
    def _filter_timeline(
        self,
        timeline: list[dict[str, Any]],
        detail_level: DetailLevel,
    ) -> list[dict[str, Any]]:
        """Filter timeline events based on detail level."""
        if detail_level == "detailed":
            return timeline
        
        # For high and medium levels, filter out noise
        filtered = []
        for event in timeline:
            module = event.get('module', '').lower()
            event_name = event.get('event', '').lower()
            
            # Always include these
            if any(keyword in module for keyword in ['api', 'agent', 'llm', 'router']):
                filtered.append(event)
                continue
            
            # Include for medium level
            if detail_level == "medium":
                if any(keyword in module for keyword in ['middleware', 'memory', 'service']):
                    filtered.append(event)
                    continue
            
            # Include important events
            if any(keyword in event_name for keyword in ['started', 'completed', 'error', 'failed']):
                filtered.append(event)
                continue
        
        return filtered if filtered else timeline[:10]  # Fallback: show first 10 events
    
    def _build_nodes(
        self,
        timeline: list[dict[str, Any]],
        detail_level: DetailLevel,
    ) -> list[FlowNode]:
        """Build nodes from timeline events."""
        nodes = []
        seen_keys = set()  # Track unique nodes to avoid duplicates
        
        for idx, event in enumerate(timeline):
            module = event.get('module', 'unknown')
            event_name = event.get('event') or event.get('message', 'Unknown')
            source = event.get('source', 'x-agent')
            
            # Create unique key for deduplication
            # For high level, group by module; for detailed, make each event unique
            if detail_level == "high":
                node_key = f"{module}"
            else:
                node_key = f"{module}-{idx}"
            
            if node_key in seen_keys and detail_level != "detailed":
                continue
            
            seen_keys.add(node_key)

            # Get operation type from enriched data
            event_data = event.get('data', {})
            operation_type = event_data.get('operation_type')

            # Determine node type using enhanced method
            node_type = self._get_node_type(module, source, operation_type)

            # Create label - if it's a specialized operation, use the operation type as the label
            if operation_type:
                if detail_level == "high":
                    label = self._get_operation_display_name(operation_type)
                else:
                    label = self._get_detailed_operation_label(operation_type, event_data, event_name)
            else:
                if detail_level == "high":
                    label = self._get_module_display_name(module)
                else:
                    label = self._truncate_label(event_name, 50)

            # Prepare node data
            node_data = {
                'module': module,
                'timestamp': event.get('timestamp'),
                'level': event.get('level'),
                'source': source,
                'operation_type': operation_type,  # Add operation type for frontend identification
            }

            # Add extra data based on detail level
            if detail_level != "high":
                node_data.update(event_data)
                if source == 'prompt-llm':
                    # Include LLM specific data
                    node_data['provider'] = event_data.get('provider')
                    node_data['model'] = event_data.get('model')
                    node_data['latency_ms'] = event_data.get('latency_ms')

            node_id = f"node-{len(nodes)}"
            node = FlowNode(
                node_id=node_id,
                node_type=node_type,
                label=label,
                data=node_data,
                position={'x': 0, 'y': 0},  # Will be set by layout
            )
            nodes.append(node)
        
        return nodes
    
    def _build_edges(
        self,
        nodes: list[FlowNode],
        timeline: list[dict[str, Any]],
    ) -> list[FlowEdge]:
        """Build edges connecting nodes."""
        edges = []
        
        for i in range(len(nodes) - 1):
            source_node = nodes[i]
            target_node = nodes[i + 1]
            
            # Determine if edge should be animated (for async operations)
            animated = False
            if i < len(timeline):
                event = timeline[i]
                if 'async' in str(event.get('event', '')).lower():
                    animated = True
            
            # Create edge label if there's timing info
            label = None
            if i < len(timeline) - 1:
                # Try to calculate duration between events
                curr_time = timeline[i].get('timestamp')
                next_time = timeline[i + 1].get('timestamp')
                if curr_time and next_time:
                    # Time format: "2026-02-14 19:41:39.327644"
                    from datetime import datetime
                    try:
                        t1 = datetime.fromisoformat(curr_time)
                        t2 = datetime.fromisoformat(next_time)
                        duration_ms = int((t2 - t1).total_seconds() * 1000)
                        if duration_ms > 10:  # Only show if > 10ms
                            label = f"{duration_ms}ms"
                    except (ValueError, TypeError):
                        pass
            
            edge = FlowEdge(
                edge_id=f"e-{source_node.id}-{target_node.id}",
                source=source_node.id,
                target=target_node.id,
                label=label,
                animated=animated,
            )
            edges.append(edge)
        
        return edges
    
    def _apply_layout(
        self,
        nodes: list[FlowNode],
        timeline: list[dict[str, Any]],
    ) -> None:
        """Apply layout algorithm to position nodes.
        
        Uses a simple vertical timeline layout to avoid edge crossings.
        Nodes are arranged in execution order with slight horizontal
        offset based on type for visual clarity.
        """
        # Horizontal offset by node type for visual distinction
        type_x_offset = {
            'api': 0,
            'middleware': 50,
            'agent': 100,
            'memory': 150,
            'llm': 200,
            'service': 100,
            'plugin': 150,
            'tool': 150,
            'skill': 160,
            'command': 170,
            'memory_store': 180,
            'memory_query': 190,
            'react_loop': 200,
            'plan_mode': 210,
            'default': 100,
        }
        
        # Base position
        base_x = 250
        y_position = 50
        
        for i, node in enumerate(nodes):
            node_type = node.type
            x_offset = type_x_offset.get(node_type, 100)
            
            # Simple vertical layout with type-based horizontal offset
            x = base_x + x_offset
            y = y_position + i * self.VERTICAL_SPACING
            
            node.position = {'x': float(x), 'y': float(y)}
    
    def _build_metadata(
        self,
        trace_id: str,
        timeline_data: dict[str, Any],
        nodes: list[FlowNode],
        edges: list[FlowEdge],
    ) -> dict[str, Any]:
        """Build metadata for the flow graph."""
        return {
            'trace_id': trace_id,
            'total_nodes': len(nodes),
            'total_edges': len(edges),
            'start_time': timeline_data.get('start_time'),
            'end_time': timeline_data.get('end_time'),
            'total_duration_ms': timeline_data.get('total_duration_ms', 0),
            'execution_path': timeline_data.get('execution_path', []),
            'node_types': list(set(node.type for node in nodes)),
        }
    
    def _get_node_type(self, module: str, source: str, operation_type: str = None) -> str:
        """Determine node type from module path, source, and operation type."""
        # Prioritize operation type from enriched log data
        if operation_type:
            operation_type_lower = operation_type.lower()
            if operation_type_lower in ['tool_call']:
                return 'tool'
            elif operation_type_lower in ['skill_call']:
                return 'skill'
            elif operation_type_lower in ['command']:
                return 'command'
            elif operation_type_lower in ['memory_store']:
                return 'memory_store'
            elif operation_type_lower in ['memory_query']:
                return 'memory_query'
            elif operation_type_lower in ['react_loop']:
                return 'react_loop'
            elif operation_type_lower in ['plan_mode']:
                return 'plan_mode'

        if source == 'prompt-llm':
            return 'llm'

        module_lower = module.lower()
        for keyword, node_type in self.NODE_TYPE_MAP.items():
            if keyword in module_lower:
                return node_type

        return 'default'
    
    def _get_module_display_name(self, module: str) -> str:
        """Get a clean display name for a module."""
        # Extract last meaningful part
        parts = module.split('.')
        if len(parts) >= 2:
            return f"{parts[-2]}.{parts[-1]}"
        return module
    
    def _truncate_label(self, label: str, max_length: int) -> str:
        """Truncate label to maximum length."""
        if len(label) <= max_length:
            return label
        return label[:max_length - 3] + "..."

    def _get_operation_display_name(self, operation_type: str) -> str:
        """Get a clean display name for an operation type."""
        operation_names = {
            'tool_call': 'Tool Call',
            'skill_call': 'Skill Call',
            'command': 'Command',
            'memory_store': 'Memory Store',
            'memory_query': 'Memory Query',
            'react_loop': 'ReAct Loop',
            'plan_mode': 'Plan Mode',
        }
        return operation_names.get(operation_type, operation_type.replace('_', ' ').title())

    def _get_detailed_operation_label(self, operation_type: str, event_data: dict, event_name: str) -> str:
        """Get a detailed label for specialized operations."""
        if operation_type == 'tool_call':
            tool_name = event_data.get('tool_name', 'Unknown Tool')
            return f"Tool: {tool_name}"
        elif operation_type == 'skill_call':
            skill_name = event_data.get('skill_name', 'Unknown Skill')
            return f"Skill: {skill_name}"
        elif operation_type == 'command':
            command = event_data.get('command', 'Command Executed')
            return f"Cmd: {command[:30]}..." if command and len(command) > 30 else f"Cmd: {command}"
        elif operation_type == 'memory_store':
            memory_type = event_data.get('memory_type', 'Memory')
            return f"Store {memory_type}"
        elif operation_type == 'memory_query':
            query = event_data.get('query', 'Memory Query')
            return f"Query: {query[:30]}..." if query and len(query) > 30 else f"Query: {query}"
        elif operation_type == 'react_loop':
            step_type = event_data.get('step_type', 'Step')
            return f"ReAct {step_type.title()}"
        elif operation_type == 'plan_mode':
            plan_action = event_data.get('plan_action', 'Plan Action')
            return f"Plan: {plan_action[:30]}..." if plan_action and len(plan_action) > 30 else f"Plan: {plan_action}"
        else:
            return self._truncate_label(event_name, 50)


# Global instance cache
_flow_builder: FlowBuilder | None = None


def get_flow_builder(log_dir: str = "logs", src_dir: str = "src") -> FlowBuilder:
    """Get or create flow builder instance.
    
    Args:
        log_dir: Directory containing log files
        src_dir: Source code directory
        
    Returns:
        FlowBuilder instance
    """
    global _flow_builder
    if _flow_builder is None:
        _flow_builder = FlowBuilder(log_dir=log_dir, src_dir=src_dir)
    return _flow_builder
