"""ManifestParser - 技能清单解析器，支持 manifest.json 和 SKILL.md。

支持两种格式:
1. manifest.json（首选）- 完整 JSON 格式，支持 schema 校验
2. SKILL.md（降级）- YAML frontmatter，兼容旧格式
"""

import json
from pathlib import Path
from typing import Any

import yaml

from ...models.skill import (
    SkillManifest,
)
from ...utils.logger import get_logger

logger = get_logger(__name__)


class ManifestParseError(Exception):
    """清单解析失败时抛出的异常。"""

    pass


class ManifestParser:
    """技能清单解析器。

    优先解析 manifest.json，降级使用 SKILL.md。
    有 JSON Schema 时自动进行校验。

    示例:
        parser = ManifestParser()
        manifest = parser.parse(Path("/path/to/skill-dir"))
    """

    def __init__(self, schema_path: Path | None = None) -> None:
        """初始化解析器。

        Args:
            schema_path: JSON Schema 文件路径（可选，用于校验）
        """
        self._schema: dict[str, Any] | None = None
        self._schema_validator: Any = None

        # 加载 schema（如果提供）
        if schema_path and schema_path.exists():
            self._load_schema(schema_path)
        else:
            # 尝试默认 schema 位置
            default_schema = Path(__file__).parent / "schemas" / "manifest-schema.json"
            if default_schema.exists():
                self._load_schema(default_schema)

        logger.debug(
            "ManifestParser initialized", extra={"schema_loaded": self._schema is not None}
        )

    def _load_schema(self, schema_path: Path) -> None:
        """加载用于校验的 JSON Schema。"""
        try:
            import jsonschema

            with open(schema_path) as f:
                self._schema = json.load(f)

            # 创建校验器
            self._schema_validator = jsonschema.Draft7Validator(self._schema)
            logger.info(f"Loaded manifest schema from {schema_path}")
        except ImportError:
            logger.warning("jsonschema 未安装，校验已禁用")
        except Exception as e:
            logger.warning(f"加载 schema 失败: {e}")

    def parse(self, skill_dir: Path) -> SkillManifest:
        """从技能目录解析清单。

        优先尝试 manifest.json，降级使用 SKILL.md。

        Args:
            skill_dir: 技能目录路径

        Returns:
            解析后的 SkillManifest 对象

        Raises:
            ManifestParseError: 解析失败时抛出
        """
        if not skill_dir.exists():
            raise ManifestParseError(f"Skill directory not found: {skill_dir}")

        if not skill_dir.is_dir():
            raise ManifestParseError(f"Not a directory: {skill_dir}")

        manifest_json = skill_dir / "manifest.json"
        skill_md = skill_dir / "SKILL.md"

        # 优先尝试 manifest.json
        if manifest_json.exists():
            data = self._parse_manifest_json(manifest_json)
        elif skill_md.exists():
            data = self._parse_skill_md(skill_md)
        else:
            raise ManifestParseError(
                f"No manifest found in {skill_dir} (expected manifest.json or SKILL.md)"
            )

        # 检测目录结构
        data["path"] = skill_dir
        data["has_scripts"] = (skill_dir / "scripts").exists()
        data["has_references"] = (skill_dir / "references").exists()
        data["has_assets"] = (skill_dir / "assets").exists()

        # 创建并校验 SkillManifest
        try:
            manifest = SkillManifest.from_dict(data)
        except ValueError as e:
            raise ManifestParseError(f"Invalid manifest data: {e}") from e

        logger.info(
            f"已解析清单: {manifest.skill_id}",
            extra={
                "path": str(skill_dir),
                "version": manifest.version,
                "has_scripts": manifest.has_scripts,
            },
        )

        return manifest

    def _parse_manifest_json(self, manifest_path: Path) -> dict[str, Any]:
        """解析 manifest.json 文件。

        Args:
            manifest_path: manifest.json 文件路径

        Returns:
            解析后的字典

        Raises:
            ManifestParseError: 解析失败时抛出
        """
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ManifestParseError(f"Invalid JSON in {manifest_path}: {e}") from e
        except Exception as e:
            raise ManifestParseError(f"Failed to read {manifest_path}: {e}") from e

        # 根据 schema 校验
        if self._schema_validator:
            errors = list(self._schema_validator.iter_errors(data))
            if errors:
                # 报告第一个错误
                error = errors[0]
                field = ".".join(str(p) for p in error.path) or "root"
                raise ManifestParseError(f"Schema validation failed for {field}: {error.message}")

        # 校验必需字段
        required = ["skill_id", "name", "version", "description"]
        missing = [f for f in required if f not in data]
        if missing:
            raise ManifestParseError(f"Missing required fields: {', '.join(missing)}")

        return data

    def _parse_skill_md(self, skill_md_path: Path) -> dict[str, Any]:
        """解析 SKILL.md 文件（降级格式）。

        提取 YAML frontmatter 并转换为清单格式。

        Args:
            skill_md_path: SKILL.md 文件路径

        Returns:
            清单格式的字典

        Raises:
            ManifestParseError: 解析失败时抛出
        """
        try:
            content = skill_md_path.read_text(encoding="utf-8")
        except Exception as e:
            raise ManifestParseError(f"Failed to read {skill_md_path}: {e}") from e

        # 解析 YAML frontmatter
        if not content.strip().startswith("---"):
            raise ManifestParseError(
                f"SKILL.md must start with YAML frontmatter (---): {skill_md_path}"
            )

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ManifestParseError(f"Invalid YAML frontmatter format: {skill_md_path}")

        yaml_content = parts[1].strip()

        try:
            frontmatter = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise ManifestParseError(f"Invalid YAML in SKILL.md: {e}") from e

        if not isinstance(frontmatter, dict):
            raise ManifestParseError(f"YAML frontmatter must be a mapping: {skill_md_path}")

        # 校验必需字段
        if "name" not in frontmatter:
            raise ManifestParseError("SKILL.md must contain 'name' field")
        if "description" not in frontmatter:
            raise ManifestParseError("SKILL.md must contain 'description' field")

        # 将 SKILL.md 格式转换为清单格式
        data = self._convert_skill_md_to_manifest(frontmatter)

        return data

    def _convert_skill_md_to_manifest(self, frontmatter: dict[str, Any]) -> dict[str, Any]:
        """将 SKILL.md frontmatter 转换为清单格式。

        处理字段名差异（kebab-case vs snake_case）。
        """
        # 映射 SKILL.md 字段到清单字段
        data: dict[str, Any] = {
            "skill_id": frontmatter.get("name"),  # 使用 name 作为 skill_id
            "name": frontmatter.get("name"),
            "version": frontmatter.get("version", "1.0.0"),  # 默认版本
            "description": frontmatter.get("description"),
        }

        # kebab-case 到 snake_case 映射
        field_mapping = {
            "auto-trigger": "auto_trigger",
            "user-invocable": "user_invocable",
            "disable-model-invocation": "disable_model_invocation",
            "argument-hint": "argument_hint",
            "allowed-tools": "allowed_tools",
            "forbidden-tools": "forbidden_tools",
            "requires-bins": "requires_bins",
            "requires-env": "requires_env",
            "requires-config": "requires_config",
            "description-detail": "description_detail",
            "input-schema": "input_schema",
            "output-schema": "output_schema",
            "risk-level": "risk_level",
            "data-access": "data_access",
            "side-effect": "side_effect",
            "approval-mode": "approval_mode",
            "supports-dry-run": "supports_dry_run",
            "supports-rollback": "supports_rollback",
            "timeout-ms": "timeout_ms",
            "max-retries": "max_retries",
        }

        for kebab_key, snake_key in field_mapping.items():
            if kebab_key in frontmatter:
                data[snake_key] = frontmatter[kebab_key]

        # 直接复制其余字段（已是 snake_case 或其他格式）
        direct_fields = [
            "vendor",
            "tags",
            "domains",
            "examples",
            "keywords",
            "priority",
            "routing",
            "emoji",
            "homepage",
            "license",
            "context",
        ]
        for field in direct_fields:
            if field in frontmatter:
                data[field] = frontmatter[field]

        return data


def parse_manifest(skill_dir: Path) -> SkillManifest:
    """解析技能清单的便捷函数。

    Args:
        skill_dir: 技能目录路径

    Returns:
        解析后的 SkillManifest
    """
    parser = ManifestParser()
    return parser.parse(skill_dir)
