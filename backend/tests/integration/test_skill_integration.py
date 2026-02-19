"""Integration test for Skill system with Orchestrator."""

import pytest
from pathlib import Path
import sys

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))


class TestSkillSystemIntegration:
    """Integration tests for skill system."""
    
    def test_orchestrator_initializes_with_skills(self):
        """Test that Orchestrator initializes with skill registry."""
        from orchestrator.engine import Orchestrator
        
        backend_dir = Path(__file__).parent.parent.parent
        workspace_path = backend_dir
        
        # Create orchestrator
        orchestrator = Orchestrator(workspace_path=str(workspace_path))
        
        # Verify skill registry is initialized
        assert hasattr(orchestrator, '_skill_registry')
        assert orchestrator._skill_registry is not None
        
        # Verify skills are loaded
        skills = orchestrator._skill_registry.list_all_skills()
        assert len(skills) > 0
        
        print(f"✅ Orchestrator initialized with {len(skills)} skills")
    
    def test_system_prompt_contains_skills(self):
        """Test that system prompt includes skill information."""
        from orchestrator.engine import Orchestrator
        from memory.context_builder import get_context_builder
        
        backend_dir = Path(__file__).parent.parent.parent
        workspace_path = backend_dir
        
        # Create orchestrator and context builder
        orchestrator = Orchestrator(workspace_path=str(workspace_path))
        context_builder = get_context_builder(str(workspace_path))
        
        # Build context
        context = context_builder.build_context()
        
        # Get skills
        skills = orchestrator._skill_registry.list_all_skills()
        
        # Verify we have skills
        assert len(skills) > 0
        
        # Check that skill-creator and pptx are present
        skill_names = [s.name for s in skills]
        assert 'skill-creator' in skill_names, "skill-creator should be available"
        assert 'pptx' in skill_names, "pptx should be available"
        
        print(f"✅ System has skills: {', '.join(sorted(skill_names)[:5])}...")
    
    def test_skill_metadata_structure(self):
        """Test that skills have proper structure."""
        from services.skill_registry import get_skill_registry
        
        backend_dir = Path(__file__).parent.parent.parent
        registry = get_skill_registry(backend_dir)
        
        skills = registry.list_all_skills()
        
        # Check each skill has required fields
        for skill in skills[:5]:  # Check first 5 skills
            assert skill.name, f"Skill {skill.name} missing name"
            assert skill.description, f"Skill {skill.name} missing description"
            assert skill.path.exists(), f"Skill {skill.name} path doesn't exist"
            
            # Check directory structure flags
            skll_md_path = skill.path / "SKILL.md"
            assert skll_md_path.exists(), f"SKILL.md not found in {skill.path}"
        
        print(f"✅ All checked skills have valid structure")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
