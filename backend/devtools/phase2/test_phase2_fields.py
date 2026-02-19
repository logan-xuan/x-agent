#!/usr/bin/env python3
"""Test script for Phase 2 features."""

import sys
from pathlib import Path

# Add backend src to path
backend_src = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(backend_src))

from src.services.skill_registry import SkillRegistry
from src.services.skill_parser import SkillParser
from src.models.skill import SkillMetadata

def test_skill_metadata_fields():
    """Test that Phase 2 fields are available in SkillMetadata."""
    print("=" * 80)
    print("Testing SkillMetadata Phase 2 Fields")
    print("=" * 80)
    
    # Create a skill with Phase 2 fields
    skill = SkillMetadata(
        name="test-skill",
        description="Test skill for Phase 2",
        path=Path("/tmp/test"),
        argument_hint="[command] [filename]",
        allowed_tools=["read_file", "write_file"],
        disable_model_invocation=True,
        user_invocable=True,
        context="fork",
        license="MIT"
    )
    
    print(f"\n✅ Created skill with Phase 2 fields:")
    print(f"  - argument_hint: {skill.argument_hint}")
    print(f"  - allowed_tools: {skill.allowed_tools}")
    print(f"  - disable_model_invocation: {skill.disable_model_invocation}")
    print(f"  - user_invocable: {skill.user_invocable}")
    print(f"  - context: {skill.context}")
    print(f"  - license: {skill.license}")
    
    # Test to_dict
    skill_dict = skill.to_dict()
    print(f"\n✅ to_dict() includes all fields:")
    for key, value in skill_dict.items():
        if value is not None:
            print(f"  - {key}: {value}")

def test_skill_parser():
    """Test that SkillParser can parse Phase 2 fields from YAML."""
    print("\n" + "=" * 80)
    print("Testing SkillParser Phase 2 Parsing")
    print("=" * 80)
    
    # Create a temporary SKILL.md with Phase 2 fields
    test_md = """---
name: phase2-test
description: "Test skill for Phase 2 features"
argument-hint: "[command] [filename]"
allowed-tools: [read_file, write_file, run_in_terminal]
disable-model-invocation: false
user-invocable: true
context: fork
license: Apache-2.0
---

# Phase 2 Test Skill

This is a test skill for Phase 2 features.
"""
    
    # Write to temp file
    temp_dir = Path("/tmp/phase2_test")
    temp_dir.mkdir(exist_ok=True)
    skill_md = temp_dir / "SKILL.md"
    skill_md.write_text(test_md)
    
    # Parse it
    parser = SkillParser()
    try:
        metadata = parser.parse(skill_md)
        
        print(f"\n✅ Successfully parsed Phase 2 fields:")
        print(f"  - name: {metadata.name}")
        print(f"  - argument_hint: {metadata.argument_hint}")
        print(f"  - allowed_tools: {metadata.allowed_tools}")
        print(f"  - disable_model_invocation: {metadata.disable_model_invocation}")
        print(f"  - user_invocable: {metadata.user_invocable}")
        print(f"  - context: {metadata.context}")
        print(f"  - license: {metadata.license}")
        
    except Exception as e:
        print(f"\n❌ Failed to parse: {e}")
    finally:
        # Cleanup
        skill_md.unlink()
        temp_dir.rmdir()

def test_registry_discovery():
    """Test that SkillRegistry discovers skills with Phase 2 fields."""
    print("\n" + "=" * 80)
    print("Testing SkillRegistry Discovery")
    print("=" * 80)
    
    registry = SkillRegistry(workspace_path=Path("/Users/xuan.lx/Documents/x-agent/x-agent/workspace"))
    
    skills = registry.list_all_skills()
    
    print(f"\n✅ Discovered {len(skills)} skills:")
    
    for skill in skills[:5]:  # Show first 5
        print(f"\n  {skill.name}:")
        print(f"    - description: {skill.description[:60]}...")
        print(f"    - argument_hint: {skill.argument_hint or 'N/A'}")
        print(f"    - allowed_tools: {skill.allowed_tools or 'All tools'}")
        print(f"    - user_invocable: {skill.user_invocable}")
        print(f"    - has_scripts: {skill.has_scripts}")

if __name__ == '__main__':
    print("Phase 2 Feature Tests\n")
    
    test_skill_metadata_fields()
    test_skill_parser()
    test_registry_discovery()
    
    print("\n" + "=" * 80)
    print("✅ All Phase 2 field tests completed!")
    print("=" * 80)
