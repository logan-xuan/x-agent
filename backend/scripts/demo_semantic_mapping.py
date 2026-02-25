#!/usr/bin/env python3
"""演示工具语义映射表的功能."""

import sys
from pathlib import Path

# Add both src and tools to path
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Import directly from the module file
import importlib.util
spec = importlib.util.spec_from_file_location(
    "semantic_mapping",
    str(Path(__file__).parent.parent / "src" / "tools" / "semantic_mapping.py")
)
semantic_mapping = importlib.util.module_from_spec(spec)
spec.loader.exec_module(semantic_mapping)

# Get functions
ToolSemanticMap = semantic_mapping.ToolSemanticMap
get_tool_info = semantic_mapping.get_tool_info
is_builtin_tool = semantic_mapping.is_builtin_tool
decompose_semantic_label = semantic_mapping.decompose_semantic_label
validate_plan_steps = semantic_mapping.validate_plan_steps


def main():
    print("=" * 60)
    print("工具语义映射表演示")
    print("=" * 60)
    
    # 1. 真实工具识别
    print("\n1️⃣  真实工具识别:")
    for tool in ["web_search", "write_file", "run_in_terminal", "pdf_create"]:
        result = is_builtin_tool(tool)
        status = "✅" if result else "❌ (语义标签)"
        print(f"   {status} {tool}")
    
    # 2. 语义标签分解
    print("\n2️⃣  语义标签分解:")
    for label in ["pdf_create", "pptx_create"]:
        decomposition = decompose_semantic_label(label)
        if decomposition:
            print(f"   📄 {label}:")
            for step in decomposition:
                print(f"      → {step['tool']}: {step['action']}")
    
    # 3. 获取工具详细信息
    print("\n3️⃣  工具详细信息:")
    pdf_info = get_tool_info("pdf_create")
    if pdf_info:
        print(f"   📄 pdf_create:")
        print(f"      类型：{pdf_info['type']}")
        print(f"      实现指南：{pdf_info.get('implementation_guide', 'N/A')}")
    
    # 4. 已废弃工具检查
    print("\n4️⃣  已废弃工具:")
    for deprecated in ["verify_file", "validate"]:
        try:
            get_tool_info(deprecated)
            print(f"   ❌ {deprecated} (应该抛出异常)")
        except ValueError as e:
            print(f"   ✅ {deprecated}: {str(e)[:50]}...")
    
    # 5. 计划步骤验证
    print("\n5️⃣  计划步骤验证:")
    
    # 正确的计划
    valid_plan = [
        {"id": "step_1", "name": "搜索信息", "tool": "web_search"},
        {"id": "step_2", "name": "撰写报告", "tool": "write_file"},
        {"id": "step_3", "name": "生成 PDF", "tool": "write_file + run_in_terminal"}
    ]
    
    is_valid, errors = validate_plan_steps(valid_plan)
    print(f"   ✅ 正确计划：{'通过' if is_valid else '失败'}")
    
    # 错误的计划（使用已废弃工具）
    invalid_plan = [
        {"id": "step_1", "name": "搜索信息", "tool": "web_search"},
        {"id": "step_2", "name": "验证 PDF", "tool": "verify_file"}  # ❌ 已废弃
    ]
    
    is_valid, errors = validate_plan_steps(invalid_plan)
    print(f"   ❌ 错误计划：{'通过' if is_valid else '失败'}")
    if not is_valid:
        for error in errors:
            print(f"      错误：{error[:80]}...")
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
