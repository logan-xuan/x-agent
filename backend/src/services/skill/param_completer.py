"""ParamCompleter - 智能参数补全。

从上下文提取参数、应用默认值、
报告缺失的必需参数。
"""

import re
from dataclasses import dataclass, field
from typing import Any

from ...models.skill import SkillManifest
from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CompletionResult:
    """参数补全结果。"""

    params: dict[str, Any]
    missing_params: list[str]
    is_complete: bool
    extracted_from_context: dict[str, Any] = field(default_factory=dict)
    applied_defaults: dict[str, Any] = field(default_factory=dict)


# 从文本中提取常见值的正则模式
FILE_PATH_PATTERN = re.compile(
    r'(?:^|[\s"])(/[^\s"]+\.\w+|[A-Za-z]:\\[^\s"]+\.\w+|[\w.-]+\.\w{1,5})(?:[\s"]|$)'
)


class ParamCompleter:
    """智能参数补全服务。

    组合多种策略填充技能参数:
    1. 使用显式提供的参数
    2. 从用户输入上下文中提取值
    3. 应用 schema 中的默认值
    4. 报告仍然缺失的必需参数

    示例:
        completer = ParamCompleter()
        result = completer.complete(
            manifest=skill,
            provided_params={"source_file": "report.md"},
            user_input="转换为 pdf",
        )

        if result.is_complete:
            # 所有参数已就绪
            execute(result.params)
        else:
            # 向用户询问缺失的参数
            print(f"缺失: {result.missing_params}")
    """

    def get_missing_params(
        self,
        manifest: SkillManifest,
        params: dict[str, Any],
    ) -> list[str]:
        """获取缺失的必需参数列表。

        Args:
            manifest: 包含 input_schema 的技能清单
            params: 当前可用参数

        Returns:
            缺失的必需参数名称列表
        """
        if not manifest.input_schema:
            return []

        required = manifest.input_schema.get("required", [])
        return [p for p in required if p not in params]

    def apply_defaults(
        self,
        manifest: SkillManifest,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """为缺失参数应用 schema 中的默认值。

        Args:
            manifest: 包含 input_schema 的技能清单
            params: 当前可用参数

        Returns:
            应用默认值后的新参数字典
        """
        result = dict(params)

        if not manifest.input_schema:
            return result

        properties = manifest.input_schema.get("properties", {})

        for prop_name, prop_def in properties.items():
            if prop_name not in result and "default" in prop_def:
                result[prop_name] = prop_def["default"]

        return result

    def extract_from_context(
        self,
        user_input: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """从用户输入上下文中提取参数值。

        使用启发式规则将 schema 属性与文本片段匹配。

        Args:
            user_input: 原始用户输入文本
            schema: 输入 schema 定义

        Returns:
            提取到的参数值字典
        """
        extracted: dict[str, Any] = {}

        if not schema:
            return extracted

        properties = schema.get("properties", {})

        for prop_name, prop_def in properties.items():
            value = self._extract_value(user_input, prop_name, prop_def)
            if value is not None:
                extracted[prop_name] = value

        return extracted

    def complete(
        self,
        manifest: SkillManifest,
        provided_params: dict[str, Any],
        user_input: str = "",
    ) -> CompletionResult:
        """使用所有策略补全参数。

        策略执行顺序:
        1. 以显式提供的参数为基础
        2. 从用户输入上下文中提取
        3. 应用 schema 默认值
        4. 检查仍然缺失的必需参数

        Args:
            manifest: 技能清单
            provided_params: 显式提供的参数
            user_input: 用于上下文提取的用户输入

        Returns:
            包含补全参数和缺失列表的 CompletionResult
        """
        # 以提供的参数为基础
        params = dict(provided_params)

        # 从上下文提取
        extracted: dict[str, Any] = {}
        if user_input and manifest.input_schema:
            extracted = self.extract_from_context(user_input, manifest.input_schema)
            # 仅添加尚未提供的参数
            for key, value in extracted.items():
                if key not in params:
                    params[key] = value

        # 应用默认值
        applied_defaults: dict[str, Any] = {}
        if manifest.input_schema:
            before_keys = set(params.keys())
            params = self.apply_defaults(manifest, params)
            applied_defaults = {k: v for k, v in params.items() if k not in before_keys}

        # 检查缺失
        missing = self.get_missing_params(manifest, params)

        return CompletionResult(
            params=params,
            missing_params=missing,
            is_complete=len(missing) == 0,
            extracted_from_context=extracted,
            applied_defaults=applied_defaults,
        )

    def _extract_value(
        self,
        text: str,
        prop_name: str,
        prop_def: dict[str, Any],
    ) -> Any:
        """从文本中提取单个参数值。

        Args:
            text: 用户输入文本
            prop_name: 属性名称
            prop_def: schema 中的属性定义

        Returns:
            提取到的值或 None
        """
        prop_type = prop_def.get("type", "string")

        # 优先检查枚举值
        if "enum" in prop_def:
            return self._extract_enum(text, prop_def["enum"])

        # 按类型提取
        if prop_type == "string":
            return self._extract_string(text, prop_name, prop_def)
        elif prop_type == "integer":
            return self._extract_integer(text, prop_name)
        elif prop_type == "number":
            return self._extract_number(text, prop_name)
        elif prop_type == "boolean":
            return self._extract_boolean(text, prop_name)

        return None

    def _extract_enum(self, text: str, enum_values: list[str]) -> str | None:
        """从文本中提取枚举值。"""
        text_lower = text.lower()
        for value in enum_values:
            if value.lower() in text_lower:
                return value
        return None

    def _extract_string(
        self,
        text: str,
        prop_name: str,
        prop_def: dict[str, Any],
    ) -> str | None:
        """从文本中提取字符串值。"""
        description = prop_def.get("description", "").lower()

        # 检查是否为文件路径
        if any(kw in description for kw in ["file", "path", "directory"]):
            match = FILE_PATH_PATTERN.search(text)
            if match:
                return match.group(1)

        return None

    def _extract_integer(self, text: str, prop_name: str) -> int | None:
        """从文本中提取整数值。"""
        numbers = re.findall(r"\b(\d+)\b", text)
        if numbers:
            # 返回第一个合理范围内的数字
            for num_str in numbers:
                num = int(num_str)
                if 1 <= num <= 10000:
                    return num
        return None

    def _extract_number(self, text: str, prop_name: str) -> float | None:
        """从文本中提取数值。"""
        numbers = re.findall(r"\b(\d+\.?\d*)\b", text)
        if numbers:
            return float(numbers[0])
        return None

    def _extract_boolean(self, text: str, prop_name: str) -> bool | None:
        """从文本中提取布尔值。"""
        text_lower = text.lower()

        true_keywords = ["yes", "true", "enable", "on"]
        false_keywords = ["no", "false", "disable", "off"]

        for kw in true_keywords:
            if kw in text_lower:
                return True

        for kw in false_keywords:
            if kw in text_lower:
                return False

        return None
