"""Agent Core REST API 路由.

提供 Agent 日志查询接口，用于开发者调试面板。

Endpoints:
- GET /api/v1/agent/logs - 查询通用日志
- GET /api/v1/agent/llm-calls - 查询 LLM 调用列表
- GET /api/v1/agent/llm-calls/{call_id} - 获取 LLM 调用详情
- GET /api/v1/agent/tool-calls - 查询工具调用列表
- GET /api/v1/agent/tool-calls/{call_id} - 获取工具调用详情
- GET /api/v1/agent/traces - 获取所有 trace_id 列表
- GET /api/v1/agent/traces/{trace_id} - 获取指定 trace 的完整日志
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..logger import AgentLogger
from ..types import LogCategory, LogLevel

router = APIRouter(prefix="/agent", tags=["Agent Logs"])

# 全局 logger 实例（将在 main.py 中注入）
_logger: AgentLogger | None = None


def set_logger(logger: AgentLogger) -> None:
    """设置全局 logger 实例."""
    global _logger
    _logger = logger


def get_logger() -> AgentLogger:
    """获取全局 logger 实例."""
    global _logger
    if _logger is None:
        # 如果没有设置，创建一个默认的
        _logger = AgentLogger()
    return _logger


# ============================================================
# Response Models
# ============================================================

class LogEntryResponse(BaseModel):
    """日志条目响应模型."""
    id: str
    trace_id: str | None
    level: str
    category: str
    event: str
    message: str
    data: dict[str, Any]
    timestamp: str
    duration_ms: float | None
    error: str | None


class LLMCallResponse(BaseModel):
    """LLM 调用响应模型."""
    call_id: str
    trace_id: str | None
    model: str
    provider: str | None
    status: str
    start_time: str
    end_time: str | None
    duration_ms: float | None
    message_count: int
    estimated_tokens: int | None
    usage: dict[str, int] | None
    stop_reason: str | None
    error: str | None
    # 详细内容（可选）
    system_prompt: str | None = None
    messages: list[dict] | None = None
    tools: list[dict] | None = None
    response_content: Any | None = None


class ToolCallResponse(BaseModel):
    """工具调用响应模型."""
    call_id: str
    trace_id: str | None
    llm_call_id: str | None
    tool_name: str
    tool_call_id: str | None
    status: str
    start_time: str
    end_time: str | None
    duration_ms: float | None
    arguments: dict[str, Any]
    result: Any | None
    is_error: bool
    error: str | None


class TraceOverview(BaseModel):
    """Trace 概览."""
    trace_id: str
    first_event: str
    last_event: str
    log_count: int
    llm_call_count: int
    tool_call_count: int
    total_duration_ms: float | None
    has_error: bool


class TraceDetailResponse(BaseModel):
    """Trace 详情响应."""
    trace_id: str
    logs: list[LogEntryResponse]
    llm_calls: list[LLMCallResponse]
    tool_calls: list[ToolCallResponse]


class PaginatedResponse(BaseModel):
    """分页响应."""
    items: list[Any]
    total: int
    limit: int
    offset: int


# ============================================================
# Helper Functions
# ============================================================

def _format_datetime(dt: datetime | None) -> str | None:
    """格式化日期时间为 ISO 字符串."""
    return dt.isoformat() if dt else None


def _log_entry_to_response(entry) -> LogEntryResponse:
    """转换 LogEntry 为响应模型."""
    return LogEntryResponse(
        id=entry.id or "",
        trace_id=entry.trace_id,
        level=entry.level.value if hasattr(entry.level, 'value') else str(entry.level),
        category=entry.category.value if hasattr(entry.category, 'value') else str(entry.category),
        event=entry.event,
        message=entry.message,
        data=entry.data or {},
        timestamp=entry.timestamp.isoformat() if entry.timestamp else "",
        duration_ms=entry.duration_ms,
        error=entry.error,
    )


def _llm_call_to_response(log, include_content: bool = False) -> LLMCallResponse:
    """转换 LLMCallLog 为响应模型."""
    response = LLMCallResponse(
        call_id=log.call_id or "",
        trace_id=log.trace_id,
        model=log.model,
        provider=log.provider,
        status=log.status,
        start_time=_format_datetime(log.start_time) or "",
        end_time=_format_datetime(log.end_time),
        duration_ms=log.duration_ms,
        message_count=log.message_count,
        estimated_tokens=log.estimated_tokens,
        usage=log.usage,
        stop_reason=log.stop_reason,
        error=log.error,
    )

    if include_content:
        response.system_prompt = log.system_prompt if hasattr(log, 'system_prompt') else None
        response.messages = log.messages
        response.tools = log.tools if hasattr(log, 'tools') else None
        response.response_content = log.response_content

    return response


def _tool_call_to_response(log) -> ToolCallResponse:
    """转换 ToolCallLog 为响应模型."""
    return ToolCallResponse(
        call_id=log.call_id or "",
        trace_id=log.trace_id,
        llm_call_id=log.llm_call_id,
        tool_name=log.tool_name,
        tool_call_id=log.tool_call_id,
        status=log.status,
        start_time=_format_datetime(log.start_time) or "",
        end_time=_format_datetime(log.end_time),
        duration_ms=log.duration_ms,
        arguments=log.arguments or {},
        result=log.result,
        is_error=log.is_error,
        error=log.error,
    )


# ============================================================
# Endpoints
# ============================================================

@router.get("/logs", response_model=PaginatedResponse)
async def get_logs(
    trace_id: str | None = Query(None, description="按 trace_id 过滤"),
    category: str | None = Query(None, description="按分类过滤 (agent_loop, llm_call, tool_exec, etc.)"),
    level: str | None = Query(None, description="按级别过滤 (debug, info, warn, error)"),
    limit: int = Query(100, ge=1, le=500, description="返回数量上限"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
) -> PaginatedResponse:
    """查询通用日志.
    
    支持按 trace_id、category、level 过滤，支持分页。
    """
    logger = get_logger()

    # 转换字符串参数为枚举
    category_enum = None
    if category:
        try:
            category_enum = LogCategory(category)
        except ValueError:
            pass

    level_enum = None
    if level:
        try:
            level_enum = LogLevel(level)
        except ValueError:
            pass

    logs = logger.get_logs(
        trace_id=trace_id,
        category=category_enum,
        level=level_enum,
        limit=limit,
        offset=offset,
    )

    # 获取总数（简化处理，实际可能需要优化）
    all_logs = logger.get_logs(
        trace_id=trace_id,
        category=category_enum,
        level=level_enum,
        limit=10000,
        offset=0,
    )

    return PaginatedResponse(
        items=[_log_entry_to_response(e) for e in logs],
        total=len(all_logs),
        limit=limit,
        offset=offset,
    )


@router.get("/llm-calls", response_model=PaginatedResponse)
async def get_llm_calls(
    trace_id: str | None = Query(None, description="按 trace_id 过滤"),
    limit: int = Query(50, ge=1, le=100, description="返回数量上限"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
) -> PaginatedResponse:
    """查询 LLM 调用列表."""
    logger = get_logger()

    if trace_id:
        calls = logger.get_llm_calls_by_trace(trace_id)
    else:
        # 获取所有 LLM 调用
        calls = list(logger._llm_calls)

    # 按时间倒序
    calls.sort(key=lambda c: c.start_time or datetime.min, reverse=True)

    total = len(calls)
    calls = calls[offset:offset + limit]

    return PaginatedResponse(
        items=[_llm_call_to_response(c) for c in calls],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/llm-calls/{call_id}", response_model=LLMCallResponse)
async def get_llm_call_detail(call_id: str) -> LLMCallResponse:
    """获取 LLM 调用详情（包含完整消息内容）."""
    logger = get_logger()

    log = logger.get_llm_call(call_id)
    if not log:
        raise HTTPException(status_code=404, detail=f"LLM call not found: {call_id}")

    return _llm_call_to_response(log, include_content=True)


@router.get("/tool-calls", response_model=PaginatedResponse)
async def get_tool_calls(
    trace_id: str | None = Query(None, description="按 trace_id 过滤"),
    llm_call_id: str | None = Query(None, description="按 LLM call_id 过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回数量上限"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
) -> PaginatedResponse:
    """查询工具调用列表."""
    logger = get_logger()

    if llm_call_id:
        calls = logger.get_tool_calls_by_llm(llm_call_id)
    elif trace_id:
        calls = logger.get_tool_calls_by_trace(trace_id)
    else:
        calls = list(logger._tool_calls)

    # 按时间倒序
    calls.sort(key=lambda c: c.start_time or datetime.min, reverse=True)

    total = len(calls)
    calls = calls[offset:offset + limit]

    return PaginatedResponse(
        items=[_tool_call_to_response(c) for c in calls],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tool-calls/{call_id}", response_model=ToolCallResponse)
async def get_tool_call_detail(call_id: str) -> ToolCallResponse:
    """获取工具调用详情."""
    logger = get_logger()

    log = logger.get_tool_call(call_id)
    if not log:
        raise HTTPException(status_code=404, detail=f"Tool call not found: {call_id}")

    return _tool_call_to_response(log)


@router.get("/traces", response_model=list[TraceOverview])
async def get_traces(
    limit: int = Query(20, ge=1, le=100, description="返回数量上限"),
) -> list[TraceOverview]:
    """获取所有 trace 概览列表."""
    logger = get_logger()

    # 收集所有 trace_id
    trace_ids = set()

    for log in logger._logs:
        if log.trace_id:
            trace_ids.add(log.trace_id)

    for llm in logger._llm_calls:
        if llm.trace_id:
            trace_ids.add(llm.trace_id)

    results = []
    for trace_id in trace_ids:
        logs = logger.get_logs(trace_id=trace_id, limit=1000)
        llm_calls = logger.get_llm_calls_by_trace(trace_id)
        tool_calls = logger.get_tool_calls_by_trace(trace_id)

        if not logs:
            continue

        # 计算时间范围
        timestamps = [l.timestamp for l in logs if l.timestamp]
        first_time = min(timestamps) if timestamps else None
        last_time = max(timestamps) if timestamps else None

        # 计算总耗时
        total_duration = None
        if first_time and last_time:
            total_duration = (last_time - first_time).total_seconds() * 1000

        # 检查是否有错误
        has_error = any(l.level == LogLevel.ERROR for l in logs)

        results.append(TraceOverview(
            trace_id=trace_id,
            first_event=_format_datetime(first_time) or "",
            last_event=_format_datetime(last_time) or "",
            log_count=len(logs),
            llm_call_count=len(llm_calls),
            tool_call_count=len(tool_calls),
            total_duration_ms=total_duration,
            has_error=has_error,
        ))

    # 按最后事件时间倒序
    results.sort(key=lambda r: r.last_event, reverse=True)

    return results[:limit]


@router.get("/traces/{trace_id}", response_model=TraceDetailResponse)
async def get_trace_detail(trace_id: str) -> TraceDetailResponse:
    """获取指定 trace 的完整日志."""
    logger = get_logger()

    logs = logger.get_logs(trace_id=trace_id, limit=1000)
    llm_calls = logger.get_llm_calls_by_trace(trace_id)
    tool_calls = logger.get_tool_calls_by_trace(trace_id)

    if not logs and not llm_calls and not tool_calls:
        raise HTTPException(status_code=404, detail=f"Trace not found: {trace_id}")

    return TraceDetailResponse(
        trace_id=trace_id,
        logs=[_log_entry_to_response(l) for l in logs],
        llm_calls=[_llm_call_to_response(c, include_content=True) for c in llm_calls],
        tool_calls=[_tool_call_to_response(c) for c in tool_calls],
    )


@router.delete("/logs")
async def clear_logs() -> dict[str, str]:
    """清空所有日志（仅用于调试）."""
    logger = get_logger()
    logger.clear()
    return {"status": "ok", "message": "All logs cleared"}


@router.get("/stats")
async def get_stats() -> dict[str, Any]:
    """获取日志统计信息."""
    logger = get_logger()

    return {
        "log_count": logger.log_count,
        "llm_call_count": logger.llm_call_count,
        "tool_call_count": logger.tool_call_count,
        "max_logs": logger.DEFAULT_MAX_LOGS,
        "max_llm_calls": logger.DEFAULT_MAX_LLM_CALLS,
        "max_tool_calls": logger.DEFAULT_MAX_TOOL_CALLS,
    }
