"""Test Skill system functionality."""

import pytest
from pathlib import Path
import sys

# Import skill modules (using relative imports for pytest)
try:
    from src.models.skill import SkillMetadata
    from src.services.skill_parser import SkillParser, SkillParseError
    from src.services.skill_registry import SkillRegistry
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from models.skill import SkillMetadata
    from services.skill_parser import SkillParser, SkillParseError
    from services.skill_registry import SkillRegistry


class TestSkillMetadata:
    """Test SkillMetadata model."""
    
    def test_valid_metadata_creation(self):
        """Test creating valid metadata."""
        metadata = SkillMetadata(
            name="test-skill",
            description="A test skill for validation",
            path=Path("/tmp/test"),
        )
        
        assert metadata.name == "test-skill"
        assert metadata.description == "A test skill for validation"
        assert metadata.path == Path("/tmp/test")
        assert metadata.has_scripts is False
        assert metadata.has_references is False
        assert metadata.has_assets is False
    
    def test_invalid_name_uppercase(self):
        """Test that uppercase names are rejected."""
        with pytest.raises(ValueError, match="lowercase"):
            SkillMetadata(
                name="Invalid-Name",
                description="Test",
                path=Path("/tmp"),
            )
    
    def test_invalid_empty_description(self):
        """Test that empty descriptions are rejected."""
        with pytest.raises(ValueError, match="description is required"):
            SkillMetadata(
                name="test",
                description="",
                path=Path("/tmp"),
            )
    
    def test_name_too_long(self):
        """Test that long names are rejected."""
        long_name = "a" * 65
        with pytest.raises(ValueError, match="too long"):
            SkillMetadata(
                name=long_name,
                description="Test",
                path=Path("/tmp"),
            )
    
    def test_to_dict_conversion(self):
        """Test dictionary conversion."""
        metadata = SkillMetadata(
            name="test-skill",
            description="Test description",
            path=Path("/tmp/test"),
            has_scripts=True,
        )
        
        data = metadata.to_dict()
        
        assert data["name"] == "test-skill"
        assert data["description"] == "Test description"
        assert data["has_scripts"] is True
        
        # Test from_dict
        restored = SkillMetadata.from_dict(data)
        assert restored.name == metadata.name
        assert restored.description == metadata.description


class TestSkillParser:
    """Test SkillParser functionality."""
    
    def test_parse_skill_creator(self):
        """Test parsing skill-creator SKILL.md."""
        parser = SkillParser()
        
        # Find skill-creator
        backend_dir = Path(__file__).parent.parent.parent
        skill_creator_md = backend_dir / "src" / "skills" / "skill-creator" / "SKILL.md"
        
        if not skill_creator_md.exists():
            pytest.skip(f"skill-creator SKILL.md not found: {skill_creator_md}")
        
        metadata = parser.parse(skill_creator_md)
        
        assert metadata.name == "skill-creator"
        assert len(metadata.description) > 0
        assert "skill" in metadata.description.lower() or "create" in metadata.description.lower()
    
    def test_parse_pptx(self):
        """Test parsing pptx SKILL.md."""
        parser = SkillParser()
        
        # Find pptx
        backend_dir = Path(__file__).parent.parent.parent
        pptx_md = backend_dir / "src" / "skills" / "pptx" / "SKILL.md"
        
        if not pptx_md.exists():
            pytest.skip(f"pptx SKILL.md not found: {pptx_md}")
        
        metadata = parser.parse(pptx_md)
        
        assert metadata.name == "pptx"
        assert len(metadata.description) > 0
        assert "powerpoint" in metadata.description.lower() or "pptx" in metadata.description.lower()


class TestSkillRegistry:
    """Test SkillRegistry discovery and management."""
    
    def test_discover_skills(self):
        """Test skill discovery."""
        backend_dir = Path(__file__).parent.parent.parent
        registry = SkillRegistry(backend_dir)
        
        skills = registry.list_all_skills()
        
        assert len(skills) > 0, "Should discover at least one skill"
        
        skill_names = [s.name for s in skills]
        print(f"Discovered skills: {sorted(skill_names)}")
    
    def test_get_specific_skill(self):
        """Test retrieving specific skill metadata."""
        backend_dir = Path(__file__).parent.parent.parent
        registry = SkillRegistry(backend_dir)
        
        # Try to get skill-creator
        skill_creator = registry.get_skill_metadata("skill-creator")
        
        if skill_creator:
            assert skill_creator.name == "skill-creator"
            assert len(skill_creator.description) > 0
        else:
            pytest.fail("skill-creator not found")
    
    def test_registry_cache(self):
        """Test that registry caching works."""
        backend_dir = Path(__file__).parent.parent.parent
        registry = SkillRegistry(backend_dir)
        
        # First call (loads and caches)
        skills1 = registry.list_all_skills()
        
        # Second call (should use cache)
        skills2 = registry.list_all_skills()
        
        assert len(skills1) == len(skills2)
        assert skills1 is not skills2  # Should be different list objects
        assert [s.name for s in skills1] == [s.name for s in skills2]
    
    def test_registry_stats(self):
        """Test registry statistics."""
        backend_dir = Path(__file__).parent.parent.parent
        registry = SkillRegistry(backend_dir)
        
        stats = registry.get_stats()
        
        assert "skills_count" in stats
        assert "cache_valid" in stats
        assert isinstance(stats["skills_count"], int)


class TestSkillPriorityOverride:
    """Test skill priority overriding."""
    
    def test_override_mechanism(self):
        """Test that higher priority skills override lower priority ones."""
        # This test would require setting up test skills in different directories
        # For now, we verify the mechanism exists in the code
        backend_dir = Path(__file__).parent.parent.parent
        registry = SkillRegistry(backend_dir)
        
        # The _discover_all_skills method should handle overriding
        skills = registry._discover_all_skills()
        
        # Verify no duplicate names
        skill_names = [s.name for s in skills]
        assert len(skill_names) == len(set(skill_names)), "Should have no duplicate skill names"
