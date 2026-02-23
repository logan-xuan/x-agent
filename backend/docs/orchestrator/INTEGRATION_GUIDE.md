# Plan v2.0 快速集成指南

## 🎯 目标

将现有的 `light_planner` 升级为 `structured_planner`，并在 `engine.py` 中集成工具约束和里程碑验证。

---

## 📝 步骤 1: 修改 engine.py 导入

**文件**: `backend/src/orchestrator/engine.py`

在文件顶部添加导入：

```python
# 在现有 import 后添加
from .structured_planner import get_structured_planner
from .validators import ToolConstraintValidator, MilestoneValidator
from .models.plan import StructuredPlan
```

---

## 📝 步骤 2: 初始化验证器

**位置**: `process_request` 方法开始处

```python
async def process_request(
    self,
    session_id: str,
    user_message: str,
    session_type: SessionType | str = SessionType.MAIN,
    stream: bool = True,
) -> AsyncGenerator[dict[str, Any], None]:
    start_time = time.time()
    
    if isinstance(session_type, str):
        session_type = SessionType(session_type)
    
    logger.info("Processing request", extra={...})
    
    # ===== 新增：技能命令解析 =====
    skill_name, arguments = TaskAnalyzer.parse_skill_command(user_message)
    
    # ===== 新增：生成结构化计划（如果有技能）=====
    structured_plan = None
    tool_validator = None
    milestone_validator = None
    
    if skill_name:
        # 生成结构化计划
        planner = get_structured_planner()
        structured_plan = await planner.generate(
            goal=user_message,
            skill_name=skill_name
        )
        
        # 初始化管理器
        tool_validator = ToolConstraintValidator(structured_plan)
        milestone_validator = MilestoneValidator(structured_plan)
        
        logger.info(
            "Structured plan generated",
            extra={
                "skill_binding": structured_plan.skill_binding,
                "steps_count": len(structured_plan.steps),
                "allowed_tools": structured_plan.tool_constraints.allowed if structured_plan.tool_constraints else [],
            }
        )
    
    # 原有的 Task Analysis
    analysis = self._task_analyzer.analyze(user_message)
    ...
```

---

## 📝 步骤 3: 在 ReAct Loop 前注入计划

**位置**: `_build_messages` 方法

```python
async def _build_messages(
    self,
    context: Any,
    user_message: str,
    policy: Any,
    relevant_memories: list[str] | None = None,
    session_id: str | None = None,
    plan_state: PlanState | None = None,
    skill_context_msg: dict | None = None,
    structured_plan: StructuredPlan | None = None,  # 新增参数
) -> tuple[list, dict]:
    
    messages = []
    system_parts = []
    
    # ===== 新增：注入结构化计划到 System Prompt =====
    if structured_plan:
        system_parts.append(structured_plan.to_prompt())
    
    # 原有的其他 system parts...
    ...
```

---

## 📝 步骤 4: 在工具调用时验证

**位置**: `react_loop.py` 中的工具调用逻辑

```python
# 在调用工具之前添加验证
async for event in self._react_loop.run_streaming(...):
    if event_type == "tool_call":
        tool_name = event.get("name")
        
        # ===== 新增：工具约束验证 =====
        if tool_validator:
            is_allowed, reason = tool_validator.is_tool_allowed(tool_name)
            if not is_allowed:
                logger.error(f"Tool blocked by constraints: {reason}")
                
                # 发送错误事件给前端
                yield {
                    "type": "error",
                    "error": f"工具 '{tool_name}' 不被允许使用：{reason}",
                }
                
                # 检查是否需要重规划
                if tool_validator.should_trigger_replan():
                    logger.warning("Too many tool violations, triggering replan")
                    # TODO: 触发重规划逻辑
                
                continue  # 跳过这次工具调用
        
        # 原有的工具执行逻辑...
        ...
```

---

## 📝 步骤 5: 在工具结果后检查里程碑

**位置**: `react_loop.py` 中收到 tool_result 后

```python
elif event_type == "tool_result":
    tool_call_id = event.get("tool_call_id")
    result = event.get("result")
    
    # 原有的 tool_result 处理...
    
    # ===== 新增：里程碑检查 =====
    if milestone_validator and result:
        # 获取当前步骤 ID（需要从上下文中获取）
        current_step_id = get_current_step_id()  # TODO: 实现这个函数
        
        output = result.get("output", "") if isinstance(result, dict) else str(result)
        
        passed, message = milestone_validator.check_milestone(current_step_id, output)
        
        if not passed:
            logger.error(f"Milestone validation failed: {message}")
            
            # 发送警告事件
            yield {
                "type": "milestone_failed",
                "milestone_name": ...,
                "reason": message,
            }
            
            # TODO: 可以考虑触发重规划
    
    # 继续原有的处理逻辑...
    ...
```

---

## 📝 步骤 6: 添加监控日志

**位置**: `process_request` 结束时

```python
# 在请求完成时记录统计信息
if tool_validator or milestone_validator:
    stats = {
        "tool_violations": tool_validator.violation_count if tool_validator else 0,
        "milestone_progress": milestone_validator.get_progress() if milestone_validator else {},
    }
    
    logger.info(
        "Plan execution statistics",
        extra=stats
    )
```

---

## 🧪 测试步骤

### 1. 单元测试

创建测试文件 `tests/unit/test_structured_planner.py`:

```python
import pytest
from orchestrator.structured_planner import get_structured_planner
from orchestrator.validators import ToolConstraintValidator

async def test_skill_based_plan():
    """测试基于技能的计划生成"""
    planner = get_structured_planner()
    
    plan = await planner.generate(
        goal="打开 https://www.baidu.com",
        skill_name="pdf"
    )
    
    assert plan.skill_binding == "pdf"
    assert plan.tool_constraints is not None
    assert len(plan.steps) >= 1

def test_tool_constraint_validator():
    """测试工具约束验证器"""
    from orchestrator.models.plan import StructuredPlan, ToolConstraints
    
    plan = StructuredPlan(
        skill_binding="pdf",
        tool_constraints=ToolConstraints(
            allowed=["run_in_terminal"],
            forbidden=["web_search"]
        )
    )
    
    validator = ToolConstraintValidator(plan)
    
    # 应该允许 run_in_terminal
    allowed, _ = validator.is_tool_allowed("run_in_terminal")
    assert allowed is True
    
    # 应该禁止 web_search
    allowed, reason = validator.is_tool_allowed("web_search")
    assert allowed is False
    assert reason is not None
```

### 2. 集成测试

使用真实的用户请求测试：

```bash
# 测试 pdf 技能
/pdf convert file.pdf to word

# 观察日志：
# - Structured plan generated
# - Tool constraint validation
# - Milestone checks
```

---

## ⚠️ 注意事项

### 1. 向后兼容

- 保留 `light_planner.py` 用于简单任务
- 只有检测到 `/command` 时才使用 `structured_planner`

### 2. 降级机制

如果 LLM 生成计划失败，自动降级到简单的默认计划：

```python
try:
    plan = await planner.generate(...)
except Exception as e:
    logger.warning(f"Plan generation failed: {e}, using fallback")
    plan = planner._generate_fallback_plan(...)
```

### 3. 性能优化

- 缓存技能元数据（已有）
- 考虑缓存生成的计划（TODO）

---

## 📊 预期效果

### Before (v1.0)

```
用户：/pdf ...
  ↓
Plan: 文本建议（无约束力）
  ↓
LLM: 调用 web_search ❌
  ↓
结果：无法完成任务
```

### After (v2.0)

```
用户：/pdf ...
  ↓
Plan: 结构化计划（skill_binding + tool_constraints）
  ↓
验证器：阻止 web_search ✅
  ↓
LLM: 调用 run_in_terminal → pdftotext CLI ✅
  ↓
里程碑：检查每一步 ✅
  ↓
结果：成功完成任务
```

---

## 🚀 立即开始

1. ✅ 已创建核心文件：
   - `models/plan.py`
   - `structured_planner.py`
   - `validators/tool_validator.py`
   - `validators/milestone_validator.py`

2. ⏳ 待集成：
   - 修改 `engine.py`（按步骤 2-3）
   - 修改 `react_loop.py`（按步骤 4-5）
   - 添加监控日志（按步骤 6）

3. 🧪 测试验证：
   - 运行单元测试
   - 执行集成测试
   - 收集真实用户反馈

---

## 📞 需要帮助？

参考完整文档：`PLAN_V2_UPGRADE.md`
