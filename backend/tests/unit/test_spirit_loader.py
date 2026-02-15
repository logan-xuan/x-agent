"""Unit tests for SpiritLoader.

Tests for:
- Loading SPIRIT.md and OWNER.md
- Identity initialization detection
- Hot-reload functionality
"""

import tempfile
from pathlib import Path

import pytest

from src.memory.models import OwnerProfile, SpiritConfig
from src.memory.spirit_loader import SpiritLoader
from src.memory.md_sync import MarkdownSync


@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestSpiritLoader:
    """Tests for SpiritLoader class."""
    
    def test_detect_first_time_startup(self, temp_workspace):
        """Should detect first time startup when files don't exist."""
        loader = SpiritLoader(workspace_path=temp_workspace)
        status = loader.get_identity_status()
        
        assert status["initialized"] is False
        assert status["has_spirit"] is False
        assert status["has_owner"] is False
    
    def test_load_spirit_config(self, temp_workspace):
        """Should load SPIRIT.md correctly."""
        # Create SPIRIT.md
        spirit_path = Path(temp_workspace) / "SPIRIT.md"
        spirit_path.write_text("""# AI 人格设定

## 角色定位
测试AI助手

## 性格特征
友好、专业

## 价值观
- 诚实
- 帮助他人

## 行为准则
- 遵循指令
""")
        
        loader = SpiritLoader(workspace_path=temp_workspace)
        spirit = loader.load_spirit()
        
        assert spirit is not None
        assert spirit.role == "测试AI助手"
        assert spirit.personality == "友好、专业"
        assert "诚实" in spirit.values
        assert len(spirit.behavior_rules) == 1
    
    def test_load_owner_profile(self, temp_workspace):
        """Should load OWNER.md correctly."""
        # Create OWNER.md
        owner_path = Path(temp_workspace) / "OWNER.md"
        owner_path.write_text("""# 用户画像

## 基本信息
- 姓名: 张三
- 年龄: 30
- 职业: 工程师

## 兴趣爱好
- 编程
- 阅读
""")
        
        loader = SpiritLoader(workspace_path=temp_workspace)
        owner = loader.load_owner()
        
        assert owner is not None
        assert owner.name == "张三"
        assert owner.age == 30
        assert owner.occupation == "工程师"
        assert "编程" in owner.interests
    
    def test_initialize_identity(self, temp_workspace):
        """Should create initial identity files."""
        loader = SpiritLoader(workspace_path=temp_workspace)
        
        result = loader.initialize_identity(
            owner_name="测试用户",
            owner_occupation="开发者",
            owner_interests=["Python", "AI"],
        )
        
        assert result["success"] is True
        
        # Check files created
        assert (Path(temp_workspace) / "SPIRIT.md").exists()
        assert (Path(temp_workspace) / "OWNER.md").exists()
        
        # Check content
        owner = loader.load_owner()
        assert owner.name == "测试用户"
        assert owner.occupation == "开发者"
    
    def test_hot_reload_spirit(self, temp_workspace):
        """Should reload SPIRIT.md when file changes."""
        loader = SpiritLoader(workspace_path=temp_workspace)
        
        # Create initial file
        spirit_path = Path(temp_workspace) / "SPIRIT.md"
        spirit_path.write_text("""# AI 人格设定
## 角色定位
初始角色
""")
        
        spirit1 = loader.load_spirit()
        assert spirit1.role == "初始角色"
        
        # Modify file
        spirit_path.write_text("""# AI 人格设定
## 角色定位
修改后的角色
""")
        
        # Clear cache and reload
        loader.clear_cache()
        spirit2 = loader.load_spirit()
        assert spirit2.role == "修改后的角色"


class TestMarkdownSync:
    """Tests for MarkdownSync class."""
    
    def test_save_and_load_spirit(self, temp_workspace):
        """Should save and load SpiritConfig."""
        sync = MarkdownSync(temp_workspace)
        
        config = SpiritConfig(
            role="助手",
            personality="友好",
            values=["诚实", "专业"],
            behavior_rules=["遵循指令"],
        )
        
        assert sync.save_spirit(config) is True
        
        loaded = sync.load_spirit()
        assert loaded is not None
        assert loaded.role == "助手"
        assert loaded.personality == "友好"
        assert len(loaded.values) == 2
    
    def test_save_and_load_owner(self, temp_workspace):
        """Should save and load OwnerProfile."""
        sync = MarkdownSync(temp_workspace)
        
        profile = OwnerProfile(
            name="李四",
            age=25,
            occupation="设计师",
            interests=["设计", "摄影"],
            goals=["提升技能"],
        )
        
        assert sync.save_owner(profile) is True
        
        loaded = sync.load_owner()
        assert loaded is not None
        assert loaded.name == "李四"
        assert loaded.age == 25
        assert "设计" in loaded.interests
    
    def test_check_identity_status(self, temp_workspace):
        """Should check identity file status."""
        sync = MarkdownSync(temp_workspace)
        
        # No files
        status = sync.check_identity_status()
        assert status["initialized"] is False
        
        # Create SPIRIT.md
        sync.save_spirit(SpiritConfig())
        status = sync.check_identity_status()
        assert status["has_spirit"] is True
        assert status["has_owner"] is False
        
        # Create OWNER.md
        sync.save_owner(OwnerProfile())
        status = sync.check_identity_status()
        assert status["initialized"] is True
