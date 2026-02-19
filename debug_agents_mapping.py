#!/usr/bin/env python3
"""Debug script to see exactly where each section and content is mapped."""

import tempfile
from pathlib import Path

def debug_agents_mapping():
    """Debug how AGENTS.md sections are being processed."""

    # Create a complete AGENTS.md with ALL sections (including those mentioned in the query)
    agents_content = """# AGENTS.md - 你的工作空间

这个文件夹是你的家。像对待家一样对待它。

## 首次启动

如果存在 `BOOTSTRAP.md`，那是你的"出生证明"。遵循它的指引，弄清楚你是谁，然后删除它。你不会再需要它。

## 每次会话开始时

在做任何事之前，请先：
1. 阅读 `SPIRIT.md` —— 这定义了你是谁
2. 阅读 `OWNER.md` —— 这定义了你在帮助谁
3. 阅读 `memory/YYYY-MM-DD.md`（今天 + 昨天）获取近期上下文
4. **如果处于主会话中**（与人类用户的直接对话）：还需阅读 `MEMORY.md`

无需请求许可。直接去做。

## 记忆系统

每次会话你都会"重置"。以下文件提供连续性：
- **每日笔记：** `memory/YYYY-MM-DD.md`（如无 `memory` 目录请创建）—— 记录当日原始日志
- **长期记忆：** `MEMORY.md` —— 你精心整理的记忆，类似人类的长期记忆

记录重要的内容：决策、上下文、需要记住的事项。除非被要求，否则无需记录秘密。

### MEMORY.md - 你的长期记忆
- **仅在主会话中加载**（与人类用户的直接对话）
- **在共享上下文（如 Discord、群聊、与其他人的会话）中禁止加载**
- 出于**安全考虑** —— 包含不应泄露给陌生人的个人上下文
- 在主会话中，你可以自由**读取、编辑和更新** MEMORY.md
- 记录重要事件、思考、决策、观点、经验教训
- 这是你提炼后的记忆精华，而非原始日志
- 随时间推移，回顾每日文件，将值得保留的内容更新至 MEMORY.md

### 动手写下来 - 拒绝"脑记"！
- **记忆是有限的** —— 想记住什么，就**写入文件**
- "脑记"无法在会话重启后保留。文件可以。
- 当有人说"记住这个" → 更新 `memory/YYYY-MM-DD.md` 或相关文件
- 当你学到经验 → 更新 AGENTS.md、TOOLS.md 或相关技能文档
- 当你犯错 → 记录下来，避免未来的你重蹈覆辙
- **文字 > 大脑**

## 安全准则

- 永远不要泄露私有数据
- 未经确认，不要执行破坏性命令
- 优先使用 `trash` 而非 `rm`（可恢复优于永久消失）
- 不确定时，先询问

## 外部操作 vs 内部操作

**可自由执行：**
- 读取文件、探索、整理、学习
- 搜索网络、查看日历
- 在工作空间内进行操作

**需先询问：**
- 发送邮件、推文、公开帖子
- 任何会离开本机的操作
- 任何你不确定的操作

**避免三连击：** 不要对同一条消息用多个碎片化回复。一次深思熟虑的回应胜过三次零碎发言。

参与，但不主导。

**为何重要：**
表情反应是轻量级的社交信号。人类频繁使用它们来表达"我看到了，我认可你"，而不增加聊天噪音。你也该如此。

**切勿过度：** 每条消息最多一个反应。选择最贴切的一个。

## 工具

技能模块为你提供工具。需要时请查阅对应 `SKILL.md`。将本地笔记（如摄像头名称、SSH 详情、语音偏好）保存在 `TOOLS.md` 中。

### 记忆维护
每隔几天，利用一次心跳执行：
1. 阅读近期 `memory/YYYY-MM-DD.md` 文件
2. 识别值得长期保留的重要事件、经验或洞察
3. 将提炼后的内容更新至 `MEMORY.md`
4. 清理 MEMORY.md 中已过时、不再相关的信息

如同人类回顾日记并更新心智模型：每日文件是原始笔记，MEMORY.md 是提炼后的智慧。

目标：在不惹人厌的前提下提供帮助。每天适度"报到"几次，完成有用的后台工作，同时尊重安静时间。

## 打造你的风格

这是起点。随着你摸索出适合自己的方式，可添加个人化的惯例、风格和规则。
"""

    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_path = Path(temp_dir)
        agents_file = workspace_path / "AGENTS.md"
        agents_file.write_text(agents_content, encoding='utf-8')

        print("Original AGENTS.md content:")
        print(agents_content)
        print("\n" + "="*50 + "\n")

        # Import and debug the policy engine to check how rules are parsed
        import sys
        sys.path.insert(0, str(Path(__file__).parent / "backend"))

        from src.orchestrator.policy_engine import PolicyEngine

        print("Testing PolicyEngine...")
        engine = PolicyEngine(str(workspace_path))

        # Get the raw policy bundle to examine
        policy = engine.policy
        print(f"Hard constraints: {len(policy.hard_constraints)}")
        print(f"Soft guidelines: {len(policy.soft_guidelines)}")
        print(f"Identity rules: {len(policy.identity_rules)}")
        print()

        print("Hard Constraints:")
        for i, rule in enumerate(policy.hard_constraints):
            print(f"  {i+1}. Section: '{rule.source_section}'")
            print(f"     Type: {rule.type.value}")
            print(f"     Content preview: {rule.content[:100]}...")
            print(f"     Has prompt text: {bool(rule.prompt_text)}")
            if rule.prompt_text:
                print(f"     Prompt text: {rule.prompt_text}")
            print()

        print("Soft Guidelines:")
        for i, rule in enumerate(policy.soft_guidelines):
            print(f"  {i+1}. Section: '{rule.source_section}'")
            print(f"     Type: {rule.type.value}")
            print(f"     Content preview: {rule.content[:100]}...")
            print(f"     Has prompt text: {bool(rule.prompt_text)}")
            if rule.prompt_text:
                print(f"     Prompt text: {rule.prompt_text}")
            print()

        print("Identity Rules:")
        for i, rule in enumerate(policy.identity_rules):
            print(f"  {i+1}. Section: '{rule.source_section}'")
            print(f"     Type: {rule.type.value}")
            print(f"     Content preview: {rule.content[:100]}...")
            print(f"     Has prompt text: {bool(rule.prompt_text)}")
            if rule.prompt_text:
                print(f"     Prompt text: {rule.prompt_text}")
            print()

        # Also test the guidelines generation
        print("Generated guidelines:")
        guidelines = engine.build_system_prompt_guidelines()
        print(guidelines)


if __name__ == "__main__":
    debug_agents_mapping()