"""LLM-based trace analysis service.

Provides intelligent analysis of trace data using LLM.
"""

from typing import Any
from pathlib import Path

from ..services.log_parser import get_log_parser
from ..services.llm.router import LLMRouter
from ..services.analysis_cache import get_analysis_cache
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TraceAnalyzer:
    """Analyzes trace data using LLM for intelligent insights."""
    
    ANALYSIS_PROMPT = """你是一个专业的系统性能和错误分析专家。请分析以下trace数据，找出问题并提供优化建议。

## Trace信息
- Trace ID: {trace_id}
- 总耗时: {total_duration_ms}ms
- 事件数量: {event_count}
- 执行路径: {execution_path}

## 日志摘要
{x_agent_summary}

## LLM调用记录
{llm_summary}

## 分析要求
请从以下几个方面进行分析：
1. **性能分析**：识别慢操作和潜在瓶颈
2. **错误分析**：发现错误和异常情况
3. **LLM使用分析**：评估token使用和调用效率
4. **优化建议**：提供具体的改进建议

请以JSON格式输出分析结果，格式如下：
{{
  "analysis": "整体分析报告（Markdown格式）",
  "insights": [
    {{
      "type": "performance|error|optimization|llm_usage",
      "title": "问题标题",
      "description": "详细描述",
      "location": "相关模块或位置",
      "severity": "low|medium|high"
    }}
  ],
  "suggestions": ["具体建议1", "具体建议2"]
}}

注意：
- 只输出JSON，不要有其他内容
- insights数组最多5条
- suggestions数组最多5条
"""

    def __init__(self, llm_router: LLMRouter, log_dir: str = "logs"):
        """Initialize trace analyzer.
        
        Args:
            llm_router: LLM router instance for making LLM calls
            log_dir: Directory containing log files
        """
        self.llm_router = llm_router
        self.log_parser = get_log_parser(log_dir)
        
        logger.info(
            "TraceAnalyzer initialized",
            extra={'log_dir': log_dir}
        )
    
    def _build_call_chain_diagram(
        self,
        timeline_data: dict[str, Any],
        prompt_logs: list[Any],
    ) -> str:
        """Build an ASCII-style call chain diagram.
        
        Args:
            timeline_data: Timeline data with execution path
            prompt_logs: LLM call logs
            
        Returns:
            ASCII diagram string
        """
        execution_path = timeline_data.get('execution_path', [])
        timeline = timeline_data.get('timeline', [])
        
        if not execution_path:
            return "无执行路径数据"
        
        lines = []
        lines.append("```")
        lines.append("┌─────────────────────────────────────────────────────────────┐")
        lines.append("│                    调用链路图                                │")
        lines.append("└─────────────────────────────────────────────────────────────┘")
        lines.append("")
        
        # Node type icons
        type_icons = {
            'api': '🌐',
            'middleware': '⚙️',
            'agent': '🤖',
            'memory': '🧠',
            'llm': '✨',
            'service': '📦',
            'default': '📍',
        }
        
        # Build nodes with timing
        for i, module in enumerate(execution_path):
            # Determine node type
            module_lower = module.lower()
            node_type = 'default'
            if 'api' in module_lower:
                node_type = 'api'
            elif 'middleware' in module_lower:
                node_type = 'middleware'
            elif 'agent' in module_lower:
                node_type = 'agent'
            elif 'memory' in module_lower or 'context' in module_lower:
                node_type = 'memory'
            elif 'llm' in module_lower or 'router' in module_lower:
                node_type = 'llm'
            
            icon = type_icons.get(node_type, '📍')
            
            # Get short name
            short_name = module.split('.')[-1] if '.' in module else module
            
            # Get timing info if available
            timing = ""
            if i < len(timeline):
                event = timeline[i]
                timestamp = event.get('timestamp')
                if timestamp:
                    # Extract time part
                    time_part = timestamp.split('T')[1] if 'T' in timestamp else timestamp.split(' ')[1] if ' ' in timestamp else timestamp
                    timing = f" [{time_part.split('.')[0]}]"
            
            # Build node line
            if i == 0:
                # First node
                lines.append(f"    {icon} {short_name}{timing}")
            else:
                # Subsequent nodes with arrow
                lines.append(f"    │")
                lines.append(f"    ▼")
                lines.append(f"    {icon} {short_name}{timing}")
        
        # Add LLM call details if present
        if prompt_logs:
            lines.append("")
            lines.append("    ┌─────────────────────────────┐")
            lines.append("    │      LLM 调用详情           │")
            lines.append("    └─────────────────────────────┘")
            
            for log in prompt_logs[:3]:  # Show max 3 LLM calls
                model = getattr(log, 'model', 'unknown') or 'unknown'
                latency = getattr(log, 'latency_ms', 0) or 0
                tokens = 0
                token_usage = getattr(log, 'token_usage', None)
                if token_usage:
                    tokens = token_usage.get('total_tokens', 0) if isinstance(token_usage, dict) else getattr(token_usage, 'total_tokens', 0)
                
                lines.append(f"    │  📨 {model}")
                lines.append(f"    │     ⏱️  {latency}ms | 🔢 {tokens} tokens")
            
            if len(prompt_logs) > 3:
                lines.append(f"    │  ... 还有 {len(prompt_logs) - 3} 次调用")
        
        # Add summary
        lines.append("")
        lines.append("    ┌─────────────────────────────┐")
        total_duration = timeline_data.get('total_duration_ms', 0)
        lines.append(f"    │  总耗时: {total_duration}ms")
        lines.append(f"    │  节点数: {len(execution_path)}")
        lines.append(f"    │  LLM调用: {len(prompt_logs)}次")
        lines.append("    └─────────────────────────────┘")
        lines.append("```")
        
        return "\n".join(lines)
    
    def __init__(self, llm_router: LLMRouter, log_dir: str = "logs", cache_enabled: bool = True):
        """Initialize trace analyzer.

        Args:
            llm_router: LLM router instance for making LLM calls
            log_dir: Directory containing log files
            cache_enabled: Whether to use analysis caching
        """
        self.llm_router = llm_router
        self.log_parser = get_log_parser(log_dir)
        self.cache_enabled = cache_enabled

        if cache_enabled:
            self.cache = get_analysis_cache()

        logger.info(
            "TraceAnalyzer initialized",
            extra={'log_dir': log_dir, 'cache_enabled': cache_enabled}
        )

    async def analyze(
        self,
        trace_id: str,
        focus_areas: list[str] | None = None,
        force_reanalyze: bool = False,
    ) -> dict[str, Any]:
        """Analyze a trace using LLM.

        Args:
            trace_id: Trace ID to analyze
            focus_areas: Optional areas to focus on (performance, error, llm_usage)
            force_reanalyze: Whether to force reanalysis even if cached version exists

        Returns:
            Analysis result with insights and suggestions
        """
        logger.info(
            f"Starting trace analysis",
            extra={
                'trace_id': trace_id,
                'focus_areas': focus_areas,
                'force_reanalyze': force_reanalyze,
                'cache_enabled': self.cache_enabled,
            }
        )

        # Check cache if enabled and not forcing reanalysis
        if self.cache_enabled and not force_reanalyze:
            cached_result = self.cache.get_cached_analysis(trace_id, focus_areas)
            if cached_result:
                logger.info(
                    "Returning cached analysis result",
                    extra={'trace_id': trace_id, 'cached_at': cached_result.get('cached_at')}
                )
                return cached_result

        # Get trace data
        timeline_data = self.log_parser.build_timeline(trace_id)
        x_agent_logs = self.log_parser.parse_x_agent_logs(trace_id)
        prompt_logs = self.log_parser.parse_prompt_llm_logs(trace_id)

        if not x_agent_logs and not prompt_logs:
            return {
                'analysis': '未找到该trace的日志数据',
                'insights': [],
                'suggestions': ['请检查trace_id是否正确'],
            }

        # Build summaries
        x_agent_summary = self._build_x_agent_summary(x_agent_logs[:20])  # Limit to first 20
        llm_summary = self._build_llm_summary(prompt_logs)

        # Build prompt
        prompt = self.ANALYSIS_PROMPT.format(
            trace_id=trace_id,
            total_duration_ms=timeline_data.get('total_duration_ms', 0),
            event_count=len(timeline_data.get('timeline', [])),
            execution_path=' → '.join(timeline_data.get('execution_path', [])),
            x_agent_summary=x_agent_summary,
            llm_summary=llm_summary,
        )

        # Add focus areas if specified
        if focus_areas:
            focus_instruction = f"\n\n请重点关注以下方面：{', '.join(focus_areas)}"
            prompt = prompt + focus_instruction
        
        try:
            # Call LLM
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm_router.chat(messages, stream=False)

            # Parse response
            response_text = response.content

            # Try to extract JSON from response
            result = self._parse_llm_response(response_text)

            # Build call chain diagram
            call_chain_diagram = self._build_call_chain_diagram(timeline_data, prompt_logs)

            # Prepend call chain diagram to analysis
            if result.get('analysis'):
                result['analysis'] = f"{call_chain_diagram}\n\n{result['analysis']}"

            logger.info(
                f"LLM analysis completed",
                extra={
                    'trace_id': trace_id,
                    'insights_count': len(result.get('insights', [])),
                    'suggestions_count': len(result.get('suggestions', [])),
                }
            )

            # Cache the result if caching is enabled
            if self.cache_enabled:
                self.cache.cache_analysis(trace_id, result, focus_areas)
                logger.info(
                    f"Cached analysis for trace",
                    extra={'trace_id': trace_id}
                )

            return result

        except Exception as e:
            logger.error(
                f"LLM analysis failed",
                extra={
                    'trace_id': trace_id,
                    'error': str(e),
                },
                exc_info=True,
            )

            # Return fallback analysis
            result = self._fallback_analysis(trace_id, timeline_data, x_agent_logs, prompt_logs)

            # Cache the fallback result if caching is enabled
            if self.cache_enabled:
                self.cache.cache_analysis(trace_id, result, focus_areas)
                logger.info(
                    f"Cached fallback analysis for trace",
                    extra={'trace_id': trace_id}
                )

            return result
    
    def _build_x_agent_summary(self, logs: list[Any]) -> str:
        """Build a summary of x-agent logs."""
        if not logs:
            return "无x-agent日志"
        
        summary_lines = []
        for log in logs[:20]:
            timestamp = getattr(log, 'timestamp', None) or "N/A"
            module = getattr(log, 'module', 'unknown') or 'unknown'
            event = getattr(log, 'event', None) or (getattr(log, 'message', '')[:50] if getattr(log, 'message', None) else "N/A")
            level = getattr(log, 'level', 'info') or 'info'
            
            summary_lines.append(f"- [{timestamp}] {module}: {event} ({level})")
        
        return "\n".join(summary_lines)
    
    def _build_llm_summary(self, logs: list[Any]) -> str:
        """Build a summary of LLM call logs."""
        if not logs:
            return "无LLM调用记录"
        
        summary_lines = []
        for log in logs:
            latency = getattr(log, 'latency_ms', 0) or 0
            model = getattr(log, 'model', 'unknown') or 'unknown'
            provider = getattr(log, 'provider', 'unknown') or 'unknown'
            success = "成功" if getattr(log, 'success', False) else "失败"
            
            token_info = ""
            token_usage = getattr(log, 'token_usage', None)
            if token_usage:
                total_tokens = token_usage.get('total_tokens', 0) if isinstance(token_usage, dict) else getattr(token_usage, 'total_tokens', 0)
                token_info = f", Tokens: {total_tokens}"
            
            summary_lines.append(
                f"- {model} ({provider}): {latency}ms, {success}{token_info}"
            )
        
        return "\n".join(summary_lines)
    
    def _parse_llm_response(self, response_text: str) -> dict[str, Any]:
        """Parse LLM response to extract analysis result."""
        import json
        import re
        
        # Try to find JSON in the response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return {
                    'analysis': result.get('analysis', response_text),
                    'insights': result.get('insights', []),
                    'suggestions': result.get('suggestions', []),
                }
            except json.JSONDecodeError:
                pass
        
        # If no JSON found, use the whole response as analysis
        return {
            'analysis': response_text,
            'insights': [],
            'suggestions': [],
        }
    
    def _fallback_analysis(
        self,
        trace_id: str,
        timeline_data: dict[str, Any],
        x_agent_logs: list[Any],
        prompt_logs: list[Any],
    ) -> dict[str, Any]:
        """Generate fallback analysis when LLM fails."""
        insights = []
        suggestions = []
        
        total_duration = timeline_data.get('total_duration_ms', 0)
        timeline = timeline_data.get('timeline', [])
        
        # Performance analysis
        if total_duration > 5000:
            insights.append({
                'type': 'performance',
                'title': '慢请求检测',
                'description': f'该请求耗时 {total_duration}ms，超过建议阈值(5000ms)',
                'severity': 'high',
            })
            suggestions.append('考虑优化LLM调用或添加缓存机制')
        
        # LLM usage analysis
        for log in prompt_logs:
            token_usage = getattr(log, 'token_usage', None)
            if token_usage:
                total_tokens = token_usage.get('total_tokens', 0) if isinstance(token_usage, dict) else getattr(token_usage, 'total_tokens', 0)
                if total_tokens > 4000:
                    insights.append({
                        'type': 'optimization',
                        'title': 'Token使用较高',
                        'description': f'LLM调用使用了 {total_tokens} tokens',
                        'location': getattr(log, 'model', 'unknown'),
                        'severity': 'medium',
                    })
                    suggestions.append('考虑优化prompt长度或使用更小的上下文窗口')
            
            latency = getattr(log, 'latency_ms', None)
            if latency and latency > 3000:
                insights.append({
                    'type': 'performance',
                    'title': 'LLM响应较慢',
                    'description': f'LLM调用耗时 {latency}ms',
                    'location': getattr(log, 'model', 'unknown'),
                    'severity': 'medium',
                })
        
        # Error analysis
        for log in x_agent_logs:
            if log.level == 'error':
                insights.append({
                    'type': 'error',
                    'title': '发现错误日志',
                    'description': log.message[:200] if log.message else 'Unknown error',
                    'location': log.module,
                    'severity': 'high',
                })
        
        analysis_text = f"""## Trace分析报告

**Trace ID**: {trace_id}
**总耗时**: {total_duration}ms
**事件数量**: {len(timeline)}

### 执行路径
{' → '.join(timeline_data.get('execution_path', []))}

### 发现的问题
- 发现 {len(insights)} 个需要关注的问题
- 生成 {len(suggestions)} 条优化建议

*注意：这是基础分析结果，LLM分析暂时不可用。*
"""
        
        # Build call chain diagram
        call_chain_diagram = self._build_call_chain_diagram(timeline_data, prompt_logs)
        
        return {
            'analysis': f"{call_chain_diagram}\n\n{analysis_text}",
            'insights': insights[:5],
            'suggestions': suggestions[:5],
        }


# Global instance
_trace_analyzer: TraceAnalyzer | None = None


def get_trace_analyzer(llm_router: LLMRouter | None = None, log_dir: str = "logs", cache_enabled: bool = True) -> TraceAnalyzer:
    """Get or create trace analyzer instance.

    Args:
        llm_router: LLM router instance
        log_dir: Directory containing log files
        cache_enabled: Whether to use analysis caching

    Returns:
        TraceAnalyzer instance
    """
    global _trace_analyzer

    if _trace_analyzer is None:
        if llm_router is None:
            from ..main import get_llm_router
            llm_router = get_llm_router()
        _trace_analyzer = TraceAnalyzer(llm_router, log_dir, cache_enabled)

    return _trace_analyzer
