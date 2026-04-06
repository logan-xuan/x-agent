"""Unit tests for configuration validation warnings."""

from src.config.models import Config, ModelConfig
from src.config.validator import validate_config


def test_config_validator_warns_when_no_backup_model_is_configured():
    config = Config(
        models=[
            ModelConfig(
                name="primary",
                provider="bailian",
                base_url="https://coding.dashscope.aliyuncs.com/v1",
                api_key="sk-test-primary-key-1234567890",
                model_id="glm-5",
                is_primary=True,
            )
        ]
    )

    result = validate_config(config)

    assert result.is_valid is True
    assert any(issue.message == "No backup model configured" for issue in result.warnings)


def test_config_validator_does_not_warn_when_backup_model_exists():
    config = Config(
        models=[
            ModelConfig(
                name="primary",
                provider="bailian",
                base_url="https://coding.dashscope.aliyuncs.com/v1",
                api_key="sk-test-primary-key-1234567890",
                model_id="glm-5",
                is_primary=True,
            ),
            ModelConfig(
                name="backup",
                provider="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test-backup-key-1234567890",
                model_id="gpt-4o-mini",
                is_primary=False,
                priority=1,
            ),
        ]
    )

    result = validate_config(config)

    assert result.is_valid is True
    assert all(issue.message != "No backup model configured" for issue in result.warnings)
