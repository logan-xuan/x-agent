"""Milestone validator for X-Agent plan execution.

Validates key milestones during plan execution to ensure quality.
Provides hybrid scheduling: soft guidance with hard validation at critical points.
"""

from dataclasses import dataclass
from typing import Literal

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MilestoneValidation:
    """Milestone validation result
    
    Attributes:
        passed: Whether validation passed
        milestone_name: Name of the milestone
        validation_type: Type of validation performed
        message: Validation message
        suggestions: Suggestions for fixing if failed
    """
    passed: bool
    milestone_name: str
    validation_type: Literal["file_exists", "syntax_check", "import_test", "run_command", "custom"]
    message: str
    suggestions: list[str] | None = None


class MilestoneValidator:
    """Validates key milestones during plan execution
    
    Core functionality:
    1. Define validation rules for critical steps
    2. Execute validation after milestone completion
    3. Provide actionable feedback on failure
    """
    
    # Built-in validation commands
    VALIDATION_COMMANDS = {
        "python_syntax": "python -m py_compile {file}",
        "typescript_syntax": "npx tsc --noEmit {file}",
        "file_exists": "test -f {file}",
        "dir_exists": "test -d {path}",
        "import_python": "python -c 'import {module}'",
    }
    
    def validate(self, milestone_name: str, context: dict) -> MilestoneValidation:
        """Validate a milestone
        
        Args:
            milestone_name: Name/description of the milestone
            context: Context information (file paths, module names, etc.)
            
        Returns:
            MilestoneValidation result
        """
        # Auto-detect validation type based on milestone name
        validation_type = self._detect_validation_type(milestone_name)
        
        if validation_type == "file_exists":
            return self._validate_file_exists(milestone_name, context)
        elif validation_type == "syntax_check":
            return self._validate_syntax(milestone_name, context)
        elif validation_type == "import_test":
            return self._validate_import(milestone_name, context)
        else:
            # Default: assume success for soft validation
            return MilestoneValidation(
                passed=True,
                milestone_name=milestone_name,
                validation_type="custom",
                message="Milestone completed (soft validation)"
            )
    
    def _detect_validation_type(self, milestone_name: str) -> str:
        """Detect validation type from milestone name
        
        Args:
            milestone_name: Milestone description
            
        Returns:
            Validation type keyword
        """
        name_lower = milestone_name.lower()
        
        # File creation milestones
        if any(kw in name_lower for kw in ["创建", "create", "write file", "保存", "生成文件"]):
            return "file_exists"
        
        # Code syntax milestones
        if any(kw in name_lower for kw in ["语法检查", "syntax", "compile", "编译", "py_compile"]):
            return "syntax_check"
        
        # Module import milestones
        if any(kw in name_lower for kw in ["导入", "import", "模块加载", "module load"]):
            return "import_test"
        
        return "custom"
    
    def _validate_file_exists(self, milestone_name: str, context: dict) -> MilestoneValidation:
        """Validate file exists
        
        Args:
            milestone_name: Milestone description
            context: Must contain 'file_path' key
            
        Returns:
            Validation result
        """
        import os
        
        file_path = context.get("file_path")
        if not file_path:
            return MilestoneValidation(
                passed=False,
                milestone_name=milestone_name,
                validation_type="file_exists",
                message="Missing file_path in context",
                suggestions=["Provide file_path in context"]
            )
        
        exists = os.path.exists(file_path)
        
        if exists:
            return MilestoneValidation(
                passed=True,
                milestone_name=milestone_name,
                validation_type="file_exists",
                message=f"File exists: {file_path}"
            )
        else:
            return MilestoneValidation(
                passed=False,
                milestone_name=milestone_name,
                validation_type="file_exists",
                message=f"File not found: {file_path}",
                suggestions=[
                    f"Check if file was created at {file_path}",
                    "Verify file path is correct",
                    "Try creating the file again"
                ]
            )
    
    def _validate_syntax(self, milestone_name: str, context: dict) -> MilestoneValidation:
        """Validate code syntax
        
        Args:
            milestone_name: Milestone description
            context: Must contain 'file_path' and optionally 'language'
            
        Returns:
            Validation result
        """
        import subprocess
        
        file_path = context.get("file_path")
        language = context.get("language", "python")
        
        if not file_path:
            return MilestoneValidation(
                passed=False,
                milestone_name=milestone_name,
                validation_type="syntax_check",
                message="Missing file_path in context",
                suggestions=["Provide file_path in context"]
            )
        
        # Build validation command
        if language == "python":
            cmd = f"python -m py_compile {file_path}"
        elif language == "typescript":
            cmd = f"npx tsc --noEmit {file_path}"
        else:
            logger.warning(f"Unknown language: {language}, skipping syntax check")
            return MilestoneValidation(
                passed=True,
                milestone_name=milestone_name,
                validation_type="syntax_check",
                message=f"Language {language} not supported, skipping validation"
            )
        
        # Execute validation
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return MilestoneValidation(
                    passed=True,
                    milestone_name=milestone_name,
                    validation_type="syntax_check",
                    message=f"Syntax check passed: {file_path}"
                )
            else:
                return MilestoneValidation(
                    passed=False,
                    milestone_name=milestone_name,
                    validation_type="syntax_check",
                    message=f"Syntax error: {result.stderr.strip()}",
                    suggestions=[
                        "Review the syntax error message",
                        "Fix the reported issues",
                        "Try compiling again"
                    ]
                )
                
        except subprocess.TimeoutExpired:
            return MilestoneValidation(
                passed=False,
                milestone_name=milestone_name,
                validation_type="syntax_check",
                message="Syntax check timeout",
                suggestions=["File may be too large", "Try manual inspection"]
            )
        except Exception as e:
            return MilestoneValidation(
                passed=False,
                milestone_name=milestone_name,
                validation_type="syntax_check",
                message=f"Validation failed: {str(e)}",
                suggestions=["Check if compiler/interpreter is installed"]
            )
    
    def _validate_import(self, milestone_name: str, context: dict) -> MilestoneValidation:
        """Validate module import
        
        Args:
            milestone_name: Milestone description
            context: Must contain 'module_name' key
            
        Returns:
            Validation result
        """
        import subprocess
        import os
        
        module_name = context.get("module_name")
        if not module_name:
            return MilestoneValidation(
                passed=False,
                milestone_name=milestone_name,
                validation_type="import_test",
                message="Missing module_name in context",
                suggestions=["Provide module_name in context"]
            )
        
        # Execute import test
        cmd = f"python -c 'import {module_name}'"
        
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=context.get("cwd", os.getcwd())
            )
            
            if result.returncode == 0:
                return MilestoneValidation(
                    passed=True,
                    milestone_name=milestone_name,
                    validation_type="import_test",
                    message=f"Import successful: {module_name}"
                )
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                return MilestoneValidation(
                    passed=False,
                    milestone_name=milestone_name,
                    validation_type="import_test",
                    message=f"Import failed: {error_msg}",
                    suggestions=[
                        "Check if module file exists",
                        "Verify module name is correct",
                        "Check for import errors in the module",
                        "Ensure dependencies are installed"
                    ]
                )
                
        except subprocess.TimeoutExpired:
            return MilestoneValidation(
                passed=False,
                milestone_name=milestone_name,
                validation_type="import_test",
                message="Import test timeout",
                suggestions=["Module may have circular imports", "Try manual inspection"]
            )
        except Exception as e:
            return MilestoneValidation(
                passed=False,
                milestone_name=milestone_name,
                validation_type="import_test",
                message=f"Import test failed: {str(e)}",
                suggestions=["Check Python environment"]
            )


# Global instance
_validator_instance: MilestoneValidator | None = None


def get_milestone_validator() -> MilestoneValidator:
    """Get global MilestoneValidator instance
    
    Returns:
        MilestoneValidator instance
    """
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = MilestoneValidator()
    return _validator_instance
