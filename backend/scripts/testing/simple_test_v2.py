#!/usr/bin/env python3
"""Simple test for Plan v2.0 components."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "backend" / "src"
sys.path.insert(0, str(src_path))

print("=" * 60)
print("Plan v2.0 Components Import Test")
print("=" * 60)

# Test 1: Models
print("\n1. Testing models.plan...")
try:
    from orchestrator.models.plan import (
        StructuredPlan,
        PlanStep,
        Milestone,
        ToolConstraints,
        StepValidation,
    )
    print("   ✅ models.plan imported successfully")
    
    # Test creating a simple plan
    plan = StructuredPlan(
        version="2.0",
        goal="Test goal",
        skill_binding="pdf",
        tool_constraints=ToolConstraints(
            allowed=["run_in_terminal"],
            forbidden=["web_search"]
        ),
    )
    print(f"   ✅ Created StructuredPlan: {plan.goal}")
    print(f"   ✅ Skill binding: {plan.skill_binding}")
    print(f"   ✅ Tool constraints: allowed={plan.tool_constraints.allowed}, forbidden={plan.tool_constraints.forbidden}")
    
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Validators
print("\n2. Testing validators...")
try:
    from orchestrator.validators.tool_validator import ToolConstraintValidator
    from orchestrator.validators.milestone_validator import MilestoneValidator
    print("   ✅ Validators imported successfully")
    
    # Test tool validator
    validator = ToolConstraintValidator(plan)
    is_allowed, reason = validator.is_tool_allowed("run_in_terminal")
    print(f"   ✅ ToolValidator created, run_in_terminal allowed: {is_allowed}")
    
    is_allowed, reason = validator.is_tool_allowed("web_search")
    print(f"   ✅ web_search allowed: {is_allowed} (should be False)")
    
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Check if engine imports work
print("\n3. Testing engine imports...")
try:
    # Try importing without going through __init__.py
    from orchestrator.structured_planner import StructuredPlanner
    print("   ✅ StructuredPlanner imported successfully")
except Exception as e:
    print(f"   ⚠️  StructuredPlanner import issue: {e}")

try:
    from orchestrator.plan_context import PlanState
    print("   ✅ PlanContext imported successfully")
    
    # Test PlanState with structured_plan field
    state = PlanState(
        original_plan="Test plan",
        current_step=1,
        total_steps=3,
    )
    print(f"   ✅ PlanState created: current_step={state.current_step}")
    print(f"   ✅ Has structured_plan field: {hasattr(state, 'structured_plan')}")
    
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Import test completed!")
print("=" * 60)
