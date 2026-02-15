"""Unit tests for Identity API.

Tests for:
- GET /api/v1/memory/identity/status
- POST /api/v1/memory/identity/init
- GET/PUT /api/v1/memory/identity/spirit
- GET/PUT /api/v1/memory/identity/owner
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestIdentityAPI:
    """Tests for Identity API endpoints."""
    
    @patch("src.memory.md_sync.get_md_sync")
    def test_get_identity_status_not_initialized(self, mock_md_sync, client, temp_workspace):
        """Should return not initialized status when files don't exist."""
        from src.memory.md_sync import MarkdownSync
        
        mock_md_sync.return_value = MarkdownSync(temp_workspace)
        
        response = client.get("/api/v1/memory/identity/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["initialized"] is False
        assert data["has_spirit"] is False
        assert data["has_owner"] is False
    
    @patch("src.memory.md_sync.get_md_sync")
    def test_get_identity_status_initialized(self, mock_md_sync, client, temp_workspace):
        """Should return initialized status when files exist."""
        from src.memory.md_sync import MarkdownSync
        from src.memory.models import SpiritConfig, OwnerProfile
        
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig())
        sync.save_owner(OwnerProfile())
        mock_md_sync.return_value = sync
        
        response = client.get("/api/v1/memory/identity/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["initialized"] is True
    
    @patch("src.memory.md_sync.get_md_sync")
    def test_initialize_identity(self, mock_md_sync, client, temp_workspace):
        """Should create identity files."""
        from src.memory.md_sync import MarkdownSync
        
        sync = MarkdownSync(temp_workspace)
        mock_md_sync.return_value = sync
        
        response = client.post(
            "/api/v1/memory/identity/init",
            json={
                "owner_name": "测试用户",
                "owner_occupation": "开发者",
                "owner_interests": ["Python", "AI"],
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["owner"]["name"] == "测试用户"
    
    @patch("src.memory.md_sync.get_md_sync")
    def test_get_spirit_not_found(self, mock_md_sync, client, temp_workspace):
        """Should return 404 when SPIRIT.md doesn't exist."""
        from src.memory.md_sync import MarkdownSync
        
        mock_md_sync.return_value = MarkdownSync(temp_workspace)
        
        response = client.get("/api/v1/memory/identity/spirit")
        
        assert response.status_code == 404
    
    @patch("src.memory.md_sync.get_md_sync")
    def test_get_spirit_success(self, mock_md_sync, client, temp_workspace):
        """Should return spirit config."""
        from src.memory.md_sync import MarkdownSync
        from src.memory.models import SpiritConfig
        
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(
            role="助手",
            personality="友好",
            values=["诚实"],
            behavior_rules=["遵循指令"],
        ))
        mock_md_sync.return_value = sync
        
        response = client.get("/api/v1/memory/identity/spirit")
        
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "助手"
    
    @patch("src.memory.md_sync.get_md_sync")
    def test_update_spirit(self, mock_md_sync, client, temp_workspace):
        """Should update spirit config."""
        from src.memory.md_sync import MarkdownSync
        
        sync = MarkdownSync(temp_workspace)
        mock_md_sync.return_value = sync
        
        response = client.put(
            "/api/v1/memory/identity/spirit",
            json={
                "role": "新角色",
                "personality": "新性格",
                "values": ["新价值观"],
                "behavior_rules": ["新准则"],
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "新角色"
    
    @patch("src.memory.md_sync.get_md_sync")
    def test_get_owner_not_found(self, mock_md_sync, client, temp_workspace):
        """Should return 404 when OWNER.md doesn't exist."""
        from src.memory.md_sync import MarkdownSync
        
        mock_md_sync.return_value = MarkdownSync(temp_workspace)
        
        response = client.get("/api/v1/memory/identity/owner")
        
        assert response.status_code == 404
    
    @patch("src.memory.md_sync.get_md_sync")
    def test_get_owner_success(self, mock_md_sync, client, temp_workspace):
        """Should return owner profile."""
        from src.memory.md_sync import MarkdownSync
        from src.memory.models import OwnerProfile
        
        sync = MarkdownSync(temp_workspace)
        sync.save_owner(OwnerProfile(
            name="张三",
            age=30,
            occupation="工程师",
        ))
        mock_md_sync.return_value = sync
        
        response = client.get("/api/v1/memory/identity/owner")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "张三"
        assert data["age"] == 30
    
    @patch("src.memory.md_sync.get_md_sync")
    def test_update_owner(self, mock_md_sync, client, temp_workspace):
        """Should update owner profile."""
        from src.memory.md_sync import MarkdownSync
        
        sync = MarkdownSync(temp_workspace)
        mock_md_sync.return_value = sync
        
        response = client.put(
            "/api/v1/memory/identity/owner",
            json={
                "name": "李四",
                "age": 25,
                "occupation": "设计师",
                "interests": ["设计"],
                "goals": ["提升技能"],
                "preferences": {},
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "李四"
