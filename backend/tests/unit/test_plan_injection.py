"""Unit tests for TaskAnalyzer - Core tests for plan injection decision."""

import pytest
from orchestrator.task_analyzer import TaskAnalyzer, TaskAnalysis


class TestTaskAnalyzer:
    """任务复杂度分析器测试"""

    def test_simple_task_no_plan(self):
        """简单任务不需要计划"""
        analyzer = TaskAnalyzer()
        result = analyzer.analyze("读取 config.yaml 文件")
        assert result.complexity == "simple"
        assert result.needs_plan == False

    def test_complex_task_needs_plan(self):
        """复杂任务需要计划"""
        analyzer = TaskAnalyzer()
        result = analyzer.analyze("先分析项目结构，然后找到配置文件，最后修改配置项")
        assert result.complexity == "complex"
        assert result.needs_plan == True

    def test_multi_step_keywords(self):
        """多步骤关键词识别"""
        analyzer = TaskAnalyzer()
        result = analyzer.analyze("第一步创建目录，第二步下载文件，最后解压")
        assert "multi_step" in str(result.indicators)
        assert result.needs_plan == True

    def test_conditional_keywords(self):
        """条件判断关键词识别"""
        analyzer = TaskAnalyzer()
        result = analyzer.analyze("检查文件是否存在，如果不存在就创建")
        assert "conditional" in str(result.indicators)
        assert result.needs_plan == True

    def test_empty_message(self):
        """空消息处理"""
        analyzer = TaskAnalyzer()
        result = analyzer.analyze("")
        assert result.complexity == "simple"
        assert result.needs_plan == False
        assert result.confidence == 0.0

    def test_long_message_complexity(self):
        """长消息复杂度判断"""
        analyzer = TaskAnalyzer()
        long_msg = "这是一个很长的任务描述。" * 50  # > 200 字符
        result = analyzer.analyze(long_msg)
        assert result.confidence >= 0.3  # 长度加分


class TestPlanContext:
    """计划上下文管理测试"""

    def test_build_react_context(self):
        """构建 ReAct 上下文"""
        from orchestrator.plan_context import PlanContext, PlanState
        
        context = PlanContext()
        state = PlanState(
            original_plan="1. 步骤一\n2. 步骤二\n3. 步骤三",
            current_step=2,
            total_steps=3,
            completed_steps=["步骤一: 完成"],
            failed_count=0,
            last_adjustment=None,
        )
        result = context.build_react_context(state)
        assert "【当前计划】" in result
        assert "【已完成】" in result
        assert "【进度】" in result

    def test_should_replan_on_failures(self):
        """连续失败触发重规划"""
        from orchestrator.plan_context import PlanContext, PlanState
        
        context = PlanContext()
        state = PlanState(
            original_plan="1. 步骤一\n2. 步骤二",
            current_step=1,
            total_steps=2,
            completed_steps=[],
            failed_count=2,  # 达到阈值
            last_adjustment=None,
        )
        need_replan, reason = context.should_replan(state)
        assert need_replan == True
        assert "连续失败" in reason

    def test_no_replan_on_success(self):
        """成功后不重规划"""
        from orchestrator.plan_context import PlanContext, PlanState
        
        context = PlanContext()
        state = PlanState(
            original_plan="1. 步骤一",
            current_step=1,
            total_steps=1,
            completed_steps=[],
            failed_count=0,
            last_adjustment=None,
        )
        need_replan, reason = context.should_replan(state)
        assert need_replan == False

    def test_update_from_tool_result_success(self):
        """工具成功结果更新"""
        from orchestrator.plan_context import PlanContext, PlanState
        
        context = PlanContext()
        state = PlanState(
            original_plan="1. 步骤一",
            current_step=1,
            total_steps=1,
            completed_steps=[],
            failed_count=1,  # 之前失败过
            last_adjustment=None,
        )
        context.update_from_tool_result(state, "read_file", True, "读取成功")
        assert state.failed_count == 0  # 重置
        assert len(state.completed_steps) == 1

    def test_update_from_tool_result_failure(self):
        """工具失败结果更新"""
        from orchestrator.plan_context import PlanContext, PlanState
        
        context = PlanContext()
        state = PlanState(
            original_plan="1. 步骤一",
            current_step=1,
            total_steps=1,
            completed_steps=[],
            failed_count=0,
            last_adjustment=None,
        )
        context.update_from_tool_result(state, "read_file", False, "文件不存在")
        assert state.failed_count == 1
