"""Tests for Phase 2 argument passing feature."""

import pytest
from pathlib import Path
import sys

# Add backend src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from orchestrator.task_analyzer import TaskAnalyzer


class TestSkillArgumentParsing:
    """Test the parse_skill_command method."""
    
    def test_parse_with_arguments(self):
        """Test parsing command with arguments."""
        skill_name, args = TaskAnalyzer.parse_skill_command("/pptx create test.pptx")
        
        assert skill_name == "pptx"
        assert args == "create test.pptx"
    
    def test_parse_without_arguments(self):
        """Test parsing command without arguments."""
        skill_name, args = TaskAnalyzer.parse_skill_command("/pdf")
        
        assert skill_name == "pdf"
        assert args == ""
    
    def test_parse_non_command(self):
        """Test parsing non-command message."""
        skill_name, args = TaskAnalyzer.parse_skill_command("Hello, how are you?")
        
        assert skill_name == ""
        assert args == "Hello, how are you?"
    
    def test_parse_with_extra_spaces(self):
        """Test parsing command with extra spaces."""
        skill_name, args = TaskAnalyzer.parse_skill_command("/pptx   create   test.pptx  ")
        
        assert skill_name == "pptx"
        assert args == "create   test.pptx"
    
    def test_parse_empty_string(self):
        """Test parsing empty string."""
        skill_name, args = TaskAnalyzer.parse_skill_command("")
        
        assert skill_name == ""
        assert args == ""
    
    def test_parse_complex_arguments(self):
        """Test parsing complex arguments with special characters."""
        skill_name, args = TaskAnalyzer.parse_skill_command(
            "/skill create file.txt --option=value --flag"
        )
        
        assert skill_name == "skill"
        assert args == "create file.txt --option=value --flag"
    
    def test_parse_multiple_words_skill_name(self):
        """Test that skill name is only the first word after /."""
        skill_name, args = TaskAnalyzer.parse_skill_command("/skill-name arg1 arg2")
        
        assert skill_name == "skill-name"
        assert args == "arg1 arg2"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
