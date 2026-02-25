"""工具语义映射表

澄清 Plan 中的语义标签与实际调用的工具之间的关系。

核心设计原则:
1. 真实工具可以直接调用 (web_search, write_file, run_in_terminal)
2. 语义标签需要分解为真实工具的组合 (pdf_create → write_file + run_in_terminal)
3. 禁止纯验证步骤 (verify_file 已废弃)
"""

from typing import Literal


class ToolSemanticMap:
    """工具语义映射表"""
    
    # === 真实工具（直接调用）===
    BUILTIN_TOOLS = {
        "web_search": {
            "type": "builtin_tool",
            "module": "src.tools.builtin.aliyun_web_search",
            "description": "阿里云 web search API",
            "can_call_directly": True
        },
        "write_file": {
            "type": "builtin_tool", 
            "module": "src.tools.builtin.file_ops",
            "description": "写入文件到本地",
            "can_call_directly": True
        },
        "run_in_terminal": {
            "type": "builtin_tool",
            "module": "src.tools.builtin.terminal",
            "description": "执行终端命令",
            "can_call_directly": True
        },
        "read_file": {
            "type": "builtin_tool",
            "module": "src.tools.builtin.file_ops",
            "description": "读取文件内容",
            "can_call_directly": True
        },
        "fetch_web_content": {
            "type": "builtin_tool",
            "module": "src.tools.builtin.fetch_web_content",
            "description": "抓取网页内容",
            "can_call_directly": True
        },
        "memory": {
            "type": "builtin_tool",
            "module": "src.services.smart_memory",
            "description": "记忆存储和检索",
            "can_call_directly": True
        },
        "browser_use": {
            "type": "builtin_tool",
            "module": "src.tools.browser_use",
            "description": "浏览器自动化",
            "can_call_directly": True
        },
        "list_dir": {
            "type": "builtin_tool",
            "module": "src.tools.builtin.file_ops",
            "description": "列出目录内容",
            "can_call_directly": True,
            "warning": "仅用于必要场景，不应作为纯验证步骤"
        }
    }
    
    # === 语义标签（需分解为真实工具）===
    SEMANTIC_LABELS = {
        "pdf_create": {
            "type": "semantic_label",
            "decomposition": [
                {"tool": "write_file", "action": "创建 Python 脚本"},
                {"tool": "run_in_terminal", "action": "执行脚本"}
            ],
            "skill_constraint": "pdf_skill_guidelines",
            "implementation_guide": "Python + reportlab，禁用 Node.js PDFKit",
            "example_code": """
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 注册中文字体
font = TTFont('Chinese', '/System/Library/Fonts/STHeiti Light.ttc', subfontIndex=0)
pdfmetrics.registerFont(font)

# 创建 PDF
c = canvas.Canvas("report.pdf", pagesize=letter)
c.setFont('Chinese', 14)
c.drawString(100, 750, "Title")
c.save()
"""
        },
        "pptx_create": {
            "type": "semantic_label",
            "decomposition": [
                {"tool": "write_file", "action": "创建 Node.js 脚本"},
                {"tool": "run_in_terminal", "action": "执行脚本"}
            ],
            "skill_constraint": "pptx_skill_guidelines",
            "implementation_guide": "Node.js + PptxGenJS",
            "example_code": """
const pptx = require('pptxgenjs');
let pres = new pptx.Presentation();
pres.addSlide().addText("Hello World!");
pres.writeFile({ fileName: "demo.pptx" });
"""
        },
        "docx_create": {
            "type": "semantic_label",
            "decomposition": [
                {"tool": "write_file", "action": "创建 Python 脚本"},
                {"tool": "run_in_terminal", "action": "执行脚本"}
            ],
            "skill_constraint": "docx_skill_guidelines",
            "implementation_guide": "Python + python-docx",
        }
    }
    
    # === 已废弃的标签（禁止使用）===
    DEPRECATED_LABELS = {
        "verify_file": {
            "type": "deprecated_label",
            "reason": "验证应内建到 step 中，不应独立",
            "alternative": "在 step description 中说明如何验证",
            "example": "❌ list_dir: 验证 PDF 是否生成 → ✅ 脚本执行成功即验证通过"
        },
        "validate": {
            "type": "deprecated_label",
            "reason": "纯验证步骤违反 YAGNI 原则",
            "alternative": "验证逻辑前置到 step expected_output 中"
        }
    }
    
    @classmethod
    def get_tool_info(cls, tool_name: str) -> dict | None:
        """获取工具信息
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具信息字典，如果不存在则返回 None
        """
        # 先在真实工具中查找
        if tool_name in cls.BUILTIN_TOOLS:
            return cls.BUILTIN_TOOLS[tool_name]
        
        # 再在语义标签中查找
        if tool_name in cls.SEMANTIC_LABELS:
            return cls.SEMANTIC_LABELS[tool_name]
        
        # 检查是否是已废弃的标签
        # ✅ 优化：不抛异常，而是返回警告信息
        if tool_name in cls.DEPRECATED_LABELS:
            deprecated_info = cls.DEPRECATED_LABELS[tool_name]
            return {
                "type": "deprecated_label",
                "name": tool_name,
                "reason": deprecated_info["reason"],
                "alternative": deprecated_info["alternative"],
                "warning": f"⚠️ 工具 '{tool_name}' 已废弃：{deprecated_info['reason']}. 替代方案：{deprecated_info['alternative']}"
            }
        
        return None
    
    @classmethod
    def is_builtin_tool(cls, tool_name: str) -> bool:
        """判断是否为真实工具
        
        Args:
            tool_name: 工具名称
            
        Returns:
            True 如果是真实工具，False 如果是语义标签
        """
        return tool_name in cls.BUILTIN_TOOLS
    
    @classmethod
    def is_semantic_label(cls, tool_name: str) -> bool:
        """判断是否为语义标签
        
        Args:
            tool_name: 工具名称
            
        Returns:
            True 如果是语义标签，False 如果是真实工具
        """
        return tool_name in cls.SEMANTIC_LABELS
    
    @classmethod
    def decompose_semantic_label(cls, label: str) -> list[dict] | None:
        """分解语义标签为真实工具组合
        
        Args:
            label: 语义标签名称
            
        Returns:
            工具分解列表，如果不是语义标签则返回 None
        """
        if label not in cls.SEMANTIC_LABELS:
            return None
        
        return cls.SEMANTIC_LABELS[label]["decomposition"]
    
    @classmethod
    def validate_plan_steps(cls, steps: list[dict]) -> tuple[bool, list[str]]:
        """验证计划步骤是否符合规范
        
        Args:
            steps: 计划步骤列表
            
        Returns:
            (是否有效，错误消息列表)
        """
        errors = []
        
        for i, step in enumerate(steps):
            tool = step.get("tool", "")
            
            # 检查是否使用了已废弃的工具
            if tool in cls.DEPRECATED_LABELS:
                deprecated = cls.DEPRECATED_LABELS[tool]
                errors.append(
                    f"Step {i+1}: 使用了已废弃的工具 '{tool}'. "
                    f"{deprecated['reason']}. 建议：{deprecated['alternative']}"
                )
            
            # 检查是否使用了未分解的语义标签
            # ✅ 修复：移除对'decomposed'字段的检查，因为 Plan 模型中没有这个字段
            # 语义标签应该在 Prompt 中引导 LLM 分解，而不是在这里强制检查
            
            # 检查虚构的工具（既不是真实工具也不是语义标签）
            if tool not in cls.BUILTIN_TOOLS and tool not in cls.SEMANTIC_LABELS and tool not in cls.DEPRECATED_LABELS:
                errors.append(
                    f"Step {i+1}: 使用了虚构的工具 '{tool}'. "
                    f"请使用真实工具：{list(cls.BUILTIN_TOOLS.keys())} 或语义标签：{list(cls.SEMANTIC_LABELS.keys())}"
                )
        
        return len(errors) == 0, errors


# 便捷函数
def get_tool_info(tool_name: str) -> dict | None:
    """获取工具信息的便捷函数"""
    return ToolSemanticMap.get_tool_info(tool_name)


def is_builtin_tool(tool_name: str) -> bool:
    """判断是否为真实工具的便捷函数"""
    return ToolSemanticMap.is_builtin_tool(tool_name)


def decompose_semantic_label(label: str) -> list[dict] | None:
    """分解语义标签的便捷函数"""
    return ToolSemanticMap.decompose_semantic_label(label)


def validate_plan_steps(steps: list[dict]) -> tuple[bool, list[str]]:
    """验证计划步骤的便捷函数"""
    return ToolSemanticMap.validate_plan_steps(steps)
