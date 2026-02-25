"""Task Completion Analysis Models

Data models for universal task completion detection.
"""
from dataclasses import dataclass, field


@dataclass
class TaskCompletionAnalysis:
    """Analysis result for task completion detection.
    
    Attributes:
        should_conclude: Whether to prompt LLM for final_answer
        type: Type of completion (e.g., "文件生成", "数据检索", "构建完成")
        confidence: Confidence score (0.0-1.0)
        reasons: List of reasons supporting the conclusion
        guidance: Specific guidance for what to include in final_answer
        requires_llm_verification: Whether LLM verification is needed
    """
    should_conclude: bool = False
    type: str = "未知"
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    guidance: str = "请总结任务完成情况。"
    requires_llm_verification: bool = False


@dataclass
class LLMVerificationResult:
    """Result from LLM-based task completion verification.
    
    Attributes:
        is_complete: Whether LLM determines task is complete
        confidence: LLM's confidence in its assessment (0.0-1.0)
        reasons: LLM's reasoning for its assessment
        missing_elements: What's still missing (if incomplete)
        suggestions: Suggestions for improving the response
    """
    is_complete: bool = False
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    missing_elements: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
