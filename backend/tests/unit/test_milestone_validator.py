"""Tests for milestone validator and hybrid scheduling."""

import pytest
from pathlib import Path
import tempfile
import os

from src.orchestrator.milestone_validator import (
    MilestoneValidator,
    MilestoneValidation,
    get_milestone_validator,
)
from src.orchestrator.plan_context import PlanContext, PlanState


class TestMilestoneValidator:
    """Test milestone validation logic."""
    
    def test_detect_file_creation_milestone(self):
        """Test auto-detection of file creation milestones."""
        validator = MilestoneValidator()
        
        # Chinese keywords
        assert validator._detect_validation_type("创建配置文件") == "file_exists"
        assert validator._detect_validation_type("保存代码文件") == "file_exists"
        
        # English keywords
        assert validator._detect_validation_type("Create config file") == "file_exists"
        assert validator._detect_validation_type("Write file main.py") == "file_exists"
    
    def test_detect_syntax_check_milestone(self):
        """Test auto-detection of syntax check milestones."""
        validator = MilestoneValidator()
        
        assert validator._detect_validation_type("语法检查") == "syntax_check"
        assert validator._detect_validation_type("Compile Python code") == "syntax_check"
        assert validator._detect_validation_type("编译模块") == "syntax_check"
    
    def test_validate_file_exists_success(self, tmp_path):
        """Test successful file exists validation."""
        # Create a temp file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        validator = MilestoneValidator()
        result = validator.validate(
            milestone_name="创建测试文件",
            context={"file_path": str(test_file)}
        )
        
        assert result.passed is True
        assert result.validation_type == "file_exists"
        assert "exists" in result.message
    
    def test_validate_file_exists_failure(self, tmp_path):
        """Test failed file exists validation."""
        non_existent = tmp_path / "not_exists.txt"
        
        validator = MilestoneValidator()
        result = validator.validate(
            milestone_name="创建不存在的文件",
            context={"file_path": str(non_existent)}
        )
        
        assert result.passed is False
        assert "not found" in result.message
        assert result.suggestions is not None
        assert len(result.suggestions) > 0
    
    def test_validate_python_syntax_success(self, tmp_path):
        """Test successful Python syntax validation."""
        # Create valid Python file
        test_file = tmp_path / "valid.py"
        test_file.write_text("def hello():\n    return 'world'\n")
        
        validator = MilestoneValidator()
        result = validator.validate(
            milestone_name="语法检查",
            context={"file_path": str(test_file), "language": "python"}
        )
        
        assert result.passed is True
        assert "Syntax check passed" in result.message
    
    def test_validate_python_syntax_failure(self, tmp_path):
        """Test failed Python syntax validation."""
        # Create invalid Python file
        test_file = tmp_path / "invalid.py"
        test_file.write_text("def invalid(\n")  # Missing closing paren
        
        validator = MilestoneValidator()
        result = validator.validate(
            milestone_name="语法检查",
            context={"file_path": str(test_file), "language": "python"}
        )
        
        assert result.passed is False
        assert "Syntax error" in result.message
    
    def test_validate_import_success(self, tmp_path):
        """Test successful module import validation."""
        # Create a simple Python module
        test_module = tmp_path / "test_module.py"
        test_module.write_text("# Simple module\nVALUE = 42\n")
        
        validator = MilestoneValidator()
        result = validator.validate(
            milestone_name="导入模块",
            context={
                "module_name": "test_module",
                "cwd": str(tmp_path)
            }
        )
        
        assert result.passed is True
        assert "Import successful" in result.message
    
    def test_validate_import_failure(self):
        """Test failed module import validation."""
        validator = MilestoneValidator()
        result = validator.validate(
            milestone_name="导入不存在的模块",
            context={"module_name": "nonexistent_module_xyz"}
        )
        
        assert result.passed is False
        assert "Import failed" in result.message
    
    def test_global_instance(self):
        """Test global validator instance."""
        v1 = get_milestone_validator()
        v2 = get_milestone_validator()
        assert v1 is v2  # Singleton pattern


class TestPlanContextWithMilestones:
    """Test plan context with milestone validation."""
    
    def test_should_validate_milestone_keywords(self):
        """Test milestone keyword detection."""
        context = PlanContext()
        
        # File creation keywords
        assert context.should_validate_milestone("创建配置文件") is True
        assert context.should_validate_milestone("Create main.py file") is True
        
        # Syntax check keywords
        assert context.should_validate_milestone("语法检查") is True
        assert context.should_validate_milestone("Compile the code") is True
        
        # Import keywords
        assert context.should_validate_milestone("导入模块") is True
        assert context.should_validate_milestone("Import utils module") is True
        
        # Regular steps (no validation)
        assert context.should_validate_milestone("分析项目结构") is False
        assert context.should_validate_milestone("Search for files") is False
    
    def test_plan_state_tracks_milestones(self):
        """Test that PlanState tracks validated milestones."""
        state = PlanState(
            original_plan="1. Step 1\n2. Step 2",
            current_step=1,
            total_steps=2,
        )
        
        assert state.milestones_validated == []
        
        # Simulate milestone validation
        state.milestones_validated.append("创建文件")
        state.milestones_validated.append("语法检查")
        
        assert len(state.milestones_validated) == 2
    
    def test_plan_context_validate_milestone_integration(self, tmp_path):
        """Test milestone validation through PlanContext."""
        context = PlanContext()
        state = PlanState(
            original_plan="1. 创建测试文件",
            current_step=1,
            total_steps=1,
        )
        
        # Create temp file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        
        # Validate milestone
        passed, msg = context.validate_milestone(
            state,
            milestone_name="创建测试文件",
            context={"file_path": str(test_file)}
        )
        
        assert passed is True
        assert len(state.milestones_validated) == 1
        assert "创建测试文件" in state.milestones_validated


class TestHybridScheduling:
    """Test hybrid scheduling (soft guidance + hard validation)."""
    
    def test_full_workflow_simulation(self, tmp_path):
        """Simulate complete workflow with milestone validation."""
        # Setup
        plan_context = PlanContext()
        plan_state = PlanState(
            original_plan="""
1. 分析项目目录结构
2. 创建配置文件 config.py
3. 语法检查
4. 导入模块验证
""",
            current_step=1,
            total_steps=4,
        )
        
        # Step 1: No validation needed (regular step)
        assert plan_context.should_validate_milestone("分析项目目录结构") is False
        
        plan_context.update_from_tool_result(
            plan_state,
            tool_name="list_dir",
            success=True,
            output="Found: backend/, frontend/"
        )
        assert plan_state.current_step == 2
        
        # Step 2: Validation needed (file creation)
        assert plan_context.should_validate_milestone("创建配置文件 config.py") is True
        
        # Simulate file creation
        config_file = tmp_path / "config.py"
        config_file.write_text("# Config\nDEBUG = True\n")
        
        passed, msg = plan_context.validate_milestone(
            plan_state,
            milestone_name="创建配置文件 config.py",
            context={"file_path": str(config_file)}
        )
        assert passed is True
        # Check milestone was recorded (full milestone name is stored)
        assert any("创建配置文件" in m for m in plan_state.milestones_validated)
        
        plan_context.update_from_tool_result(
            plan_state,
            tool_name="write_file",
            success=True,
            output=f"Created: {config_file}"
        )
        assert plan_state.current_step == 3
        
        # Step 3: Validation needed (syntax check)
        assert plan_context.should_validate_milestone("语法检查") is True
        
        passed, msg = plan_context.validate_milestone(
            plan_state,
            milestone_name="语法检查",
            context={"file_path": str(config_file), "language": "python"}
        )
        assert passed is True
        
        # Simulate tool execution for syntax check
        plan_context.update_from_tool_result(
            plan_state,
            tool_name="py_compile",
            success=True,
            output="Syntax OK"
        )
        
        # Step 4: Validation needed (import test)
        assert plan_context.should_validate_milestone("导入模块验证") is True
        
        passed, msg = plan_context.validate_milestone(
            plan_state,
            milestone_name="导入模块验证",
            context={
                "module_name": "config",
                "cwd": str(tmp_path)
            }
        )
        assert passed is True
        
        # Simulate tool execution for import test
        plan_context.update_from_tool_result(
            plan_state,
            tool_name="import_test",
            success=True,
            output="Import successful"
        )
        
        # Verify all milestones tracked
        assert len(plan_state.milestones_validated) == 3
        assert plan_state.current_step == 4  # All 4 steps completed
        assert len(plan_state.completed_steps) == 4  # All tool executions recorded
    
    def test_milestone_failure_triggers_replan(self, tmp_path):
        """Test that milestone failure triggers replan logic."""
        plan_context = PlanContext()
        plan_state = PlanState(
            original_plan="1. 创建关键文件",
            current_step=1,
            total_steps=1,
        )
        
        # Simulate milestone validation failure
        non_existent = tmp_path / "not_exists.py"
        
        passed, msg = plan_context.validate_milestone(
            plan_state,
            milestone_name="创建关键文件",
            context={"file_path": str(non_existent)}
        )
        
        assert passed is False
        
        # Manually increment failed_count (as engine.py would do)
        plan_state.failed_count += 1
        
        # Check if replan should be triggered
        need_replan, reason = plan_context.should_replan(plan_state)
        # Not yet - need 2 failures
        assert need_replan is False
        
        # Second failure
        plan_state.failed_count += 1
        need_replan, reason = plan_context.should_replan(plan_state)
        assert need_replan is True
        assert "连续失败" in reason
