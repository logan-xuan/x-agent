"""Trace analysis API endpoints.

Provides endpoints for:
- Fetching raw trace data from logs
- Getting flow graph data for visualization
- Analyzing traces with LLM
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...services.log_parser import get_log_parser
from ...services.code_analyzer import get_code_analyzer
from ...services.flow_builder import get_flow_builder
from ...services.trace_analyzer import get_trace_analyzer
from ...utils.logger import get_logger

router = APIRouter(prefix="/trace", tags=["trace"])
logger = get_logger(__name__)


# ============================================================================
# Response Models
# ============================================================================

class TraceRawDataResponse(BaseModel):
    """Raw trace data from logs."""
    trace_id: str
    session_id: str | None = None
    x_agent_logs: list[dict[str, Any]]
    prompt_llm_logs: list[dict[str, Any]]
    start_time: str | None = None
    end_time: str | None = None
    total_duration_ms: int = 0


class FlowNode(BaseModel):
    """React Flow node definition."""
    id: str
    type: str
    data: dict[str, Any]
    position: dict[str, float]


class FlowEdge(BaseModel):
    """React Flow edge definition."""
    id: str
    source: str
    target: str
    label: str | None = None
    animated: bool = False


class TraceFlowResponse(BaseModel):
    """Flow graph data for visualization."""
    nodes: list[FlowNode]
    edges: list[FlowEdge]
    metadata: dict[str, Any]


class AnalysisRequest(BaseModel):
    """Request for trace analysis."""
    focus_areas: list[str] = Field(default_factory=list, description="Areas to focus on: performance, error, llm_usage")
    include_suggestions: bool = Field(default=True, description="Include optimization suggestions")


class Insight(BaseModel):
    """Analysis insight."""
    type: str  # performance, error, optimization
    title: str
    description: str
    location: str | None = None
    severity: str | None = None  # low, medium, high


class AnalysisResponse(BaseModel):
    """Trace analysis result."""
    analysis: str
    insights: list[Insight]
    suggestions: list[str]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/{trace_id}/raw", response_model=TraceRawDataResponse)
async def get_trace_raw_data(
    trace_id: str,
    log_dir: str = Query(default="logs", description="Log directory path")
) -> TraceRawDataResponse:
    """Get raw trace data from log files.
    
    Args:
        trace_id: Trace ID to query
        log_dir: Directory containing log files
        
    Returns:
        Raw trace data including both x-agent and prompt-llm logs
    """
    try:
        # Resolve log directory path
        backend_dir = Path(__file__).parent.parent.parent.parent
        log_path = (backend_dir / log_dir).resolve()
        
        logger.info(
            f"Fetching trace data",
            extra={
                'trace_id': trace_id,
                'log_dir': str(log_path),
            }
        )
        
        # Parse logs
        parser = get_log_parser(str(log_path))
        timeline_data = parser.build_timeline(trace_id)
        
        # Get individual logs
        x_agent_logs = parser.parse_x_agent_logs(trace_id)
        prompt_logs = parser.parse_prompt_llm_logs(trace_id)
        
        # Extract session_id from logs
        session_id = None
        if x_agent_logs:
            session_id = x_agent_logs[0].session_id
        elif prompt_logs:
            session_id = prompt_logs[0].session_id
        
        return TraceRawDataResponse(
            trace_id=trace_id,
            session_id=session_id,
            x_agent_logs=[log.to_dict() for log in x_agent_logs],
            prompt_llm_logs=[log.to_dict() for log in prompt_logs],
            start_time=timeline_data.get('start_time'),
            end_time=timeline_data.get('end_time'),
            total_duration_ms=timeline_data.get('total_duration_ms', 0),
        )
    
    except Exception as e:
        logger.error(
            f"Failed to fetch trace data",
            extra={
                'trace_id': trace_id,
                'error': str(e),
                'error_type': type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to fetch trace data: {str(e)}")


@router.get("/{trace_id}/flow", response_model=TraceFlowResponse)
async def get_trace_flow(
    trace_id: str,
    detail_level: str = Query(default="high", description="Detail level: high, medium, detailed"),
    log_dir: str = Query(default="logs", description="Log directory path")
) -> TraceFlowResponse:
    """Get flow graph data for trace visualization.
    
    Args:
        trace_id: Trace ID to query
        detail_level: Level of detail (high, medium, detailed)
        log_dir: Directory containing log files
        
    Returns:
        Flow graph with nodes and edges for React Flow
    """
    try:
        # Resolve log directory path
        backend_dir = Path(__file__).parent.parent.parent.parent
        log_path = (backend_dir / log_dir).resolve()
        
        logger.info(
            f"Building trace flow",
            extra={
                'trace_id': trace_id,
                'detail_level': detail_level,
                'log_dir': str(log_path),
            }
        )
        
        # Use flow builder to generate graph
        flow_builder = get_flow_builder(log_dir=str(log_path))
        flow_data = flow_builder.build_flow(trace_id, detail_level=detail_level)  # type: ignore
        
        return TraceFlowResponse(
            nodes=[FlowNode(**node) for node in flow_data['nodes']],
            edges=[FlowEdge(**edge) for edge in flow_data['edges']],
            metadata=flow_data['metadata'],
        )
    
    except Exception as e:
        logger.error(
            f"Failed to build trace flow",
            extra={
                'trace_id': trace_id,
                'error': str(e),
                'error_type': type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to build trace flow: {str(e)}")


@router.post("/{trace_id}/analyze", response_model=AnalysisResponse)
async def analyze_trace(
    trace_id: str,
    request: AnalysisRequest,
    log_dir: str = Query(default="logs", description="Log directory path")
) -> AnalysisResponse:
    """Analyze trace with LLM to identify issues and optimization opportunities.
    
    Args:
        trace_id: Trace ID to analyze
        request: Analysis request with options
        log_dir: Directory containing log files
        
    Returns:
        Analysis result with insights and suggestions
    """
    try:
        logger.info(
            f"Analyzing trace with LLM",
            extra={
                'trace_id': trace_id,
                'focus_areas': request.focus_areas,
            }
        )
        
        # Resolve log directory path
        backend_dir = Path(__file__).parent.parent.parent.parent
        log_path = (backend_dir / log_dir).resolve()
        
        # Use trace analyzer for LLM-based analysis
        from ...main import get_llm_router
        llm_router = get_llm_router()
        analyzer = get_trace_analyzer(llm_router=llm_router, log_dir=str(log_path))
        
        # Perform analysis
        result = await analyzer.analyze(
            trace_id,
            focus_areas=request.focus_areas,
        )
        
        # Convert insights to Insight model
        insights = [
            Insight(
                type=insight.get('type', 'optimization'),
                title=insight.get('title', ''),
                description=insight.get('description', ''),
                location=insight.get('location'),
                severity=insight.get('severity'),
            )
            for insight in result.get('insights', [])
        ]
        
        return AnalysisResponse(
            analysis=result.get('analysis', ''),
            insights=insights,
            suggestions=result.get('suggestions', []),
        )
    
    except Exception as e:
        logger.error(
            f"Failed to analyze trace",
            extra={
                'trace_id': trace_id,
                'error': str(e),
                'error_type': type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to analyze trace: {str(e)}")
