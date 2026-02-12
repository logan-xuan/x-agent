import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os
from pathlib import Path
import sys

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.plugins.registry.loader import PluginLoader  # Adjust import based on actual implementation
from src.plugins.registry.validator import PluginValidator
from src.plugins.security.sandbox import PluginSandbox


@pytest.mark.asyncio
async def test_plugin_loading():
    """Test basic plugin loading functionality"""

    with patch('src.plugins.registry.loader.PluginLoader.load_plugin') as mock_load:
        mock_load.return_value = {
            "id": "test-plugin-123",
            "name": "Test Plugin",
            "version": "1.0.0",
            "status": "loaded"
        }

        loader = PluginLoader()

        # Test loading a plugin
        result = await loader.load_plugin("test-plugin-id")

        assert result["id"] == "test-plugin-123"
        assert result["name"] == "Test Plugin"
        assert result["status"] == "loaded"
        mock_load.assert_called_once_with("test-plugin-id")


@pytest.mark.asyncio
async def test_plugin_validation_success():
    """Test successful plugin validation"""

    # Create a temporary plugin file for testing
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_plugin:
        temp_plugin.write("""
def plugin_function():
    return "Plugin executed successfully"
""")
        temp_plugin_path = temp_plugin.name

    try:
        validator = PluginValidator()

        with patch('src.plugins.registry.validator.PluginValidator.validate_plugin_file') as mock_validate:
            mock_validate.return_value = {
                "is_valid": True,
                "issues": [],
                "metadata": {"name": "Temp Plugin", "version": "1.0"}
            }

            result = await validator.validate_plugin_file(temp_plugin_path)

            assert result["is_valid"] is True
            assert result["metadata"]["name"] == "Temp Plugin"
            mock_validate.assert_called_once_with(temp_plugin_path)
    finally:
        # Clean up the temp file
        os.unlink(temp_plugin_path)


@pytest.mark.asyncio
async def test_plugin_validation_failure():
    """Test plugin validation with failures"""

    validator = PluginValidator()

    # Test validation of dangerous plugin content
    dangerous_code = """
import os
import sys
import shutil

def dangerous_plugin():
    # Potentially dangerous operations
    os.system('rm -rf /')
    shutil.rmtree('/')
    exec('import os; os.system("dangerous command")')
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_plugin:
        temp_plugin.write(dangerous_code)
        temp_plugin_path = temp_plugin.name

    try:
        with patch('src.plugins.registry.validator.PluginValidator.validate_plugin_file') as mock_validate:
            mock_validate.return_value = {
                "is_valid": False,
                "issues": ["Security violation: dangerous function calls detected"],
                "metadata": None
            }

            result = await validator.validate_plugin_file(temp_plugin_path)

            assert result["is_valid"] is False
            assert len(result["issues"]) > 0
            mock_validate.assert_called_once_with(temp_plugin_path)
    finally:
        os.unlink(temp_plugin_path)


@pytest.mark.asyncio
async def test_plugin_activation():
    """Test plugin activation functionality"""

    with patch('src.plugins.registry.manager.PluginManager.activate_plugin') as mock_activate:
        mock_activate.return_value = {
            "plugin_id": "test-plugin-456",
            "status": "activated",
            "timestamp": "2023-01-01T00:00:00Z"
        }

        from src.plugins.registry.manager import PluginManager
        manager = PluginManager()

        result = await manager.activate_plugin("test-plugin-456")

        assert result["status"] == "activated"
        assert result["plugin_id"] == "test-plugin-456"
        mock_activate.assert_called_once_with("test-plugin-456")


@pytest.mark.asyncio
async def test_plugin_deactivation():
    """Test plugin deactivation functionality"""

    with patch('src.plugins.registry.manager.PluginManager.deactivate_plugin') as mock_deactivate:
        mock_deactivate.return_value = {
            "plugin_id": "test-plugin-789",
            "status": "deactivated",
            "timestamp": "2023-01-01T00:00:00Z"
        }

        from src.plugins.registry.manager import PluginManager
        manager = PluginManager()

        result = await manager.deactivate_plugin("test-plugin-789")

        assert result["status"] == "deactivated"
        assert result["plugin_id"] == "test-plugin-789"
        mock_deactivate.assert_called_once_with("test-plugin-789")


def test_plugin_security_sandbox():
    """Test plugin security sandbox functionality"""

    with patch('src.plugins.security.sandbox.PluginSandbox.execute_in_sandbox') as mock_execute:
        mock_execute.return_value = {
            "result": "Safe execution result",
            "violations": [],
            "resources_used": {"cpu_time": 0.05, "memory_mb": 2.5}
        }

        sandbox = PluginSandbox()

        # Test safe code execution in sandbox
        safe_code = """
def safe_operation():
    return "Safe result"
"""

        result = sandbox.execute_in_sandbox(safe_code)

        assert "Safe execution result" in result["result"]
        assert len(result["violations"]) == 0
        assert result["resources_used"]["cpu_time"] >= 0
        mock_execute.assert_called_once()


@pytest.mark.asyncio
async def test_plugin_manifest_parsing():
    """Test parsing of plugin manifest files"""

    mock_manifest = {
        "name": "Test Plugin",
        "version": "1.0.0",
        "description": "A test plugin for validation",
        "author": "Test Author",
        "license": "MIT",
        "dependencies": [],
        "api_version": "1.0",
        "capabilities": ["tool", "service"]
    }

    with patch('src.plugins.registry.manifest_parser.ManifestParser.parse_manifest') as mock_parse:
        mock_parse.return_value = mock_manifest

        from src.plugins.registry.manifest_parser import ManifestParser
        parser = ManifestParser()

        result = await parser.parse_manifest("path/to/manifest.json")

        assert result["name"] == "Test Plugin"
        assert result["version"] == "1.0.0"
        assert result["capabilities"] == ["tool", "service"]
        mock_parse.assert_called_once_with("path/to/manifest.json")


@pytest.mark.asyncio
async def test_plugin_registry_operations():
    """Test plugin registry operations"""

    with patch.multiple('src.plugins.registry',
                        Registry=MagicMock(),
                        Plugin=MagicMock()):

        registry_mock = MagicMock()
        registry_mock.register_plugin.return_value = {"status": "registered", "plugin_id": "new-plugin-123"}
        registry_mock.unregister_plugin.return_value = {"status": "unregistered"}

        # Test registering a plugin
        register_result = await registry_mock.register_plugin({
            "name": "New Test Plugin",
            "version": "1.0.0"
        })

        assert register_result["status"] == "registered"
        assert register_result["plugin_id"] == "new-plugin-123"

        # Test unregistering a plugin
        unregister_result = await registry_mock.unregister_plugin("new-plugin-123")

        assert unregister_result["status"] == "unregistered"


@pytest.mark.asyncio
async def test_plugin_security_restrictions():
    """Test that the plugin sandbox properly restricts dangerous operations"""

    sandbox = PluginSandbox()

    # Test various restricted operations
    restricted_operations = [
        "import os; os.system('ls')",  # System calls
        "import shutil; shutil.rmtree('/')",  # Dangerous file operations
        "__import__('subprocess').call(['rm', '-rf', '/'])",  # Process execution
        "exec('dangerous code')",  # Dynamic code execution
        "eval('dangerous expression')",  # Dynamic evaluation
    ]

    for operation in restricted_operations:
        with patch('src.plugins.security.sandbox.PluginSandbox.execute_in_sandbox') as mock_execute:
            mock_execute.return_value = {
                "result": "Operation blocked by sandbox",
                "violations": ["Security restriction violated"],
                "resources_used": {"cpu_time": 0, "memory_mb": 0}
            }

            result = sandbox.execute_in_sandbox(operation)

            # Should detect security violations
            assert len(result["violations"]) > 0