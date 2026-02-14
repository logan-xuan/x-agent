"""Configuration validation with detailed error messages."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import re

from pydantic import ValidationError

from .models import Config, ModelConfig


class ValidationSeverity(str, Enum):
    """Validation issue severity."""
    ERROR = "error"      # Must fix before running
    WARNING = "warning"  # Should fix but can run
    INFO = "info"        # Informational


@dataclass
class ValidationIssue:
    """Single validation issue."""
    field: str
    message: str
    severity: ValidationSeverity
    suggestion: Optional[str] = None
    value: Optional[Any] = None


@dataclass
class ValidationResult:
    """Result of configuration validation."""
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    
    @property
    def errors(self) -> list[ValidationIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]
    
    @property
    def warnings(self) -> list[ValidationIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "is_valid": self.is_valid,
            "errors": [
                {
                    "field": e.field,
                    "message": e.message,
                    "suggestion": e.suggestion,
                }
                for e in self.errors
            ],
            "warnings": [
                {
                    "field": w.field,
                    "message": w.message,
                    "suggestion": w.suggestion,
                }
                for w in self.warnings
            ],
        }


class ConfigValidator:
    """Validates configuration with detailed feedback."""
    
    # Known provider base URLs
    KNOWN_PROVIDERS = {
        "openai": "https://api.openai.com/v1",
        "bailian": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }
    
    # API Key patterns (for validation, not actual keys)
    API_KEY_PATTERNS = {
        "openai": r"^sk-[a-zA-Z0-9]{20,}$",
        "bailian": r"^sk-[a-zA-Z0-9]{16,}$",
    }
    
    def validate(self, config: Config) -> ValidationResult:
        """Validate configuration and return detailed results.
        
        Args:
            config: Configuration to validate
            
        Returns:
            ValidationResult with all issues found
        """
        result = ValidationResult(is_valid=True)
        
        # Validate models
        self._validate_models(config, result)
        
        # Validate server config
        self._validate_server(config, result)
        
        # Set final validity
        result.is_valid = len(result.errors) == 0
        
        return result
    
    def _validate_models(self, config: Config, result: ValidationResult) -> None:
        """Validate model configurations."""
        if not config.models:
            result.issues.append(ValidationIssue(
                field="models",
                message="No models configured",
                severity=ValidationSeverity.ERROR,
                suggestion="Add at least one model configuration in x-agent.yaml",
            ))
            return
        
        # Check primary model
        primaries = [m for m in config.models if m.is_primary]
        if len(primaries) == 0:
            result.issues.append(ValidationIssue(
                field="models",
                message="No primary model configured",
                severity=ValidationSeverity.ERROR,
                suggestion="Set is_primary: true for one model",
            ))
        elif len(primaries) > 1:
            result.issues.append(ValidationIssue(
                field="models",
                message=f"Multiple primary models found: {[m.name for m in primaries]}",
                severity=ValidationSeverity.ERROR,
                suggestion="Only one model should have is_primary: true",
            ))
        
        # Validate each model
        for model in config.models:
            self._validate_model(model, result)
        
        # Check for duplicate names
        names = [m.name for m in config.models]
        duplicates = [n for n in names if names.count(n) > 1]
        if duplicates:
            result.issues.append(ValidationIssue(
                field="models",
                message=f"Duplicate model names: {set(duplicates)}",
                severity=ValidationSeverity.ERROR,
                suggestion="Each model must have a unique name",
            ))
    
    def _validate_model(self, model: ModelConfig, result: ValidationResult) -> None:
        """Validate a single model configuration."""
        prefix = f"models.{model.name}"
        
        # Check API key format
        key = model.api_key.get_secret_value()
        if key.startswith("sk-your-") or "your-" in key.lower():
            result.issues.append(ValidationIssue(
                field=f"{prefix}.api_key",
                message="API key appears to be a placeholder",
                severity=ValidationSeverity.ERROR,
                suggestion=f"Replace with your actual {model.provider} API key",
                value="***REDACTED***",
            ))
        
        # Check if API key matches expected pattern
        pattern = self.API_KEY_PATTERNS.get(model.provider)
        if pattern and not re.match(pattern, key):
            result.issues.append(ValidationIssue(
                field=f"{prefix}.api_key",
                message=f"API key format doesn't match expected {model.provider} pattern",
                severity=ValidationSeverity.WARNING,
                suggestion=f"Verify your {model.provider} API key is correct",
            ))
        
        # Check base URL
        base_url = str(model.base_url)
        expected_url = self.KNOWN_PROVIDERS.get(model.provider)
        if expected_url and base_url != expected_url:
            result.issues.append(ValidationIssue(
                field=f"{prefix}.base_url",
                message=f"Non-standard base URL for {model.provider}",
                severity=ValidationSeverity.INFO,
                suggestion=f"Standard URL is {expected_url}",
            ))
        
        # Check timeout
        if model.timeout < 10:
            result.issues.append(ValidationIssue(
                field=f"{prefix}.timeout",
                message="Timeout is very low, may cause failures",
                severity=ValidationSeverity.WARNING,
                suggestion="Consider increasing timeout to at least 30 seconds",
            ))
        
        # Check for backup without priority
        if not model.is_primary and model.priority == 0:
            result.issues.append(ValidationIssue(
                field=f"{prefix}.priority",
                message="Backup model has default priority (0)",
                severity=ValidationSeverity.INFO,
                suggestion="Set explicit priority for predictable failover order",
            ))
    
    def _validate_server(self, config: Config, result: ValidationResult) -> None:
        """Validate server configuration."""
        # Check CORS
        if not config.server.cors_origins:
            result.issues.append(ValidationIssue(
                field="server.cors_origins",
                message="No CORS origins configured",
                severity=ValidationSeverity.WARNING,
                suggestion="Add frontend URL (e.g., http://localhost:5173)",
            ))
        
        # Check port
        if config.server.port < 1024:
            result.issues.append(ValidationIssue(
                field="server.port",
                message="Port below 1024 requires root privileges",
                severity=ValidationSeverity.WARNING,
                suggestion="Use a port above 1024 (default: 8000)",
            ))
    
    def validate_from_pydantic_error(self, error: ValidationError) -> ValidationResult:
        """Convert Pydantic validation error to ValidationResult.
        
        Args:
            error: Pydantic ValidationError
            
        Returns:
            ValidationResult with detailed issues
        """
        result = ValidationResult(is_valid=False)
        
        for err in error.errors():
            loc = ".".join(str(x) for x in err["loc"])
            result.issues.append(ValidationIssue(
                field=loc,
                message=err["msg"],
                severity=ValidationSeverity.ERROR,
                value=str(err.get("input", ""))[:50] if err.get("input") else None,
            ))
        
        return result


# Global validator instance
validator = ConfigValidator()


def validate_config(config: Config) -> ValidationResult:
    """Validate configuration with detailed feedback.
    
    Args:
        config: Configuration to validate
        
    Returns:
        ValidationResult with all issues found
    """
    return validator.validate(config)
