#!/usr/bin/env python3
"""End-to-end test for PPTX skill improvements.

This test verifies:
1. Dependency checking works
2. Directory creation works
3. PPTX generation works
4. Validation works
5. Error handling works

Run this test to verify all improvements are working.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add helpers to path
sys.path.insert(0, str(Path(__file__).parent))

from helpers import (
    check_python_version,
    ensure_dependencies,
    create_directories,
    validate_presentation,
    quick_test,
    safe_create_presentation,
)


def test_basic_functionality():
    """Test 1: Basic functionality test."""
    print("\n" + "=" * 70)
    print("TEST 1: Basic Functionality")
    print("=" * 70)
    
    # Check Python version
    assert check_python_version(), "Python version check failed"
    print("✅ Python version OK")
    
    # Check dependencies
    success, msg = ensure_dependencies()
    assert success, f"Dependency check failed: {msg}"
    print(f"✅ Dependencies OK: {msg}")
    
    # Quick test
    success, msg = quick_test()
    assert success, f"Quick test failed: {msg}"
    print(f"✅ Quick test passed: {msg}")
    
    print("\n✅ TEST 1 PASSED: Basic functionality working\n")
    return True


def test_directory_organization():
    """Test 2: Directory organization test."""
    print("\n" + "=" * 70)
    print("TEST 2: Directory Organization")
    print("=" * 70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create directories
        dirs = create_directories(tmpdir, ['scripts', 'presentations'])
        
        # Verify directories exist
        assert 'scripts' in dirs, "scripts directory not created"
        assert 'presentations' in dirs, "presentations directory not created"
        
        # Verify paths are correct
        assert os.path.exists(dirs['scripts']), "scripts path doesn't exist"
        assert os.path.exists(dirs['presentations']), "presentations path doesn't exist"
        
        print(f"✅ Scripts directory: {dirs['scripts']}")
        print(f"✅ Presentations directory: {dirs['presentations']}")
        
        # Test nested structure
        nested_dirs = create_directories(
            dirs['presentations'],
            ['project-alpha', 'project-beta']
        )
        
        assert len(nested_dirs) == 2, "Nested directories not created correctly"
        print(f"✅ Nested directories created successfully")
    
    print("\n✅ TEST 2 PASSED: Directory organization working\n")
    return True


def test_presentation_creation():
    """Test 3: Full presentation creation test."""
    print("\n" + "=" * 70)
    print("TEST 3: Full Presentation Creation")
    print("=" * 70)
    
    from pptx import Presentation
    from pptx.util import Inches, Pt
    
    def create_sample_presentation():
        """Sample presentation creator function."""
        prs = Presentation()
        
        # Title slide
        slide_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(slide_layout)
        slide.shapes.title.text = "Test Presentation"
        subtitle = slide.placeholders[1]
        subtitle.text = "Automated Test"
        
        # Content slides
        for i in range(1, 6):
            slide_layout = prs.slide_layouts[1]
            slide = prs.slides.add_slide(slide_layout)
            slide.shapes.title.text = f"Slide {i}"
            
            tf = slide.shapes.placeholders[1].text_frame
            tf.text = f"This is bullet point 1 on slide {i}"
            
            p = tf.add_paragraph()
            p.text = f"This is bullet point 2 on slide {i}"
            p.level = 1
        
        # Save
        output_path = '/tmp/test_presentation.pptx'
        prs.save(output_path)
        print(f"   Saved to: {output_path}")
    
    try:
        # Use safe_create_presentation wrapper
        success, msg = safe_create_presentation(
            '/tmp/test_presentation.pptx',
            create_sample_presentation,
            expected_slides=6  # 1 title + 5 content
        )
        
        assert success, f"Safe creation failed: {msg}"
        print(f"✅ Presentation created and validated: {msg}")
        
        # Additional manual validation
        prs = Presentation('/tmp/test_presentation.pptx')
        assert len(prs.slides) == 6, f"Expected 6 slides, got {len(prs.slides)}"
        print(f"✅ Manual validation passed: {len(prs.slides)} slides")
        
        # Clean up
        os.remove('/tmp/test_presentation.pptx')
        print(f"✅ Cleanup completed")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise
    
    print("\n✅ TEST 3 PASSED: Full presentation creation working\n")
    return True


def test_error_handling():
    """Test 4: Error handling test."""
    print("\n" + "=" * 70)
    print("TEST 4: Error Handling")
    print("=" * 70)
    
    # Test 1: Validate non-existent file
    print("Testing validation of non-existent file...")
    valid, msg = validate_presentation('/nonexistent/path/file.pptx')
    assert not valid, "Should fail for non-existent file"
    assert "does not exist" in msg, f"Wrong error message: {msg}"
    print(f"✅ Correctly detected non-existent file: {msg}")
    
    # Test 2: Validate empty file
    print("Testing validation of empty file...")
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as f:
        empty_path = f.name
        pass  # Create empty file
    
    valid, msg = validate_presentation(empty_path)
    assert not valid, "Should fail for empty file"
    assert "empty" in msg.lower(), f"Wrong error message: {msg}"
    print(f"✅ Correctly detected empty file: {msg}")
    
    # Clean up
    os.remove(empty_path)
    
    # Test 3: Wrong slide count
    print("Testing slide count validation...")
    from pptx import Presentation
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[0])
    test_path = '/tmp/single_slide.pptx'
    prs.save(test_path)
    
    valid, msg = validate_presentation(test_path, expected_slides=5)
    assert not valid, "Should fail for wrong slide count"
    assert "Expected 5 slides, got 1" in msg, f"Wrong error message: {msg}"
    print(f"✅ Correctly detected slide count mismatch: {msg}")
    
    # Clean up
    os.remove(test_path)
    
    print("\n✅ TEST 4 PASSED: Error handling working\n")
    return True


def test_real_world_scenario():
    """Test 5: Real-world scenario test."""
    print("\n" + "=" * 70)
    print("TEST 5: Real-World Scenario")
    print("=" * 70)
    
    # Simulate real workspace structure
    with tempfile.TemporaryDirectory() as workspace:
        print(f"Using temporary workspace: {workspace}")
        
        # Step 1: Setup directory structure
        print("\nStep 1: Setting up directory structure...")
        dirs = create_directories(workspace, ['scripts', 'presentations'])
        
        # Step 2: Create a script
        print("\nStep 2: Creating Python script...")
        script_path = os.path.join(dirs['scripts'], 'create_presentation.py')
        
        script_content = '''#!/usr/bin/env python3
"""Generated presentation script."""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

def create_presentation():
    """Create a sample presentation."""
    prs = Presentation()
    
    # Title slide
    slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = "Real World Test"
    
    # Content slides
    for i in range(3):
        slide_layout = prs.slide_layouts[1]
        slide = prs.slides.add_slide(slide_layout)
        slide.shapes.title.text = f"Topic {i+1}"
        
        tf = slide.shapes.placeholders[1].text_frame
        tf.text = f"Key point 1 for topic {i+1}"
        
        p = tf.add_paragraph()
        p.text = f"Key point 2 for topic {i+1}"
    
    # Save to presentations directory
    output_path = '../presentations/real_world_test.pptx'
    prs.save(output_path)
    print(f"Saved to: {output_path}")
    return output_path

if __name__ == "__main__":
    create_presentation()
'''
        
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        print(f"✅ Script created: {script_path}")
        
        # Step 3: Execute the script
        print("\nStep 3: Executing script...")
        import subprocess
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            cwd=dirs['scripts']
        )
        
        if result.returncode != 0:
            print(f"❌ Script execution failed:")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            raise AssertionError("Script execution failed")
        
        print(f"✅ Script executed successfully")
        print(f"Output: {result.stdout.strip()}")
        
        # Step 4: Validate the output
        print("\nStep 4: Validating output...")
        output_path = os.path.join(dirs['presentations'], 'real_world_test.pptx')
        
        valid, msg = validate_presentation(output_path, expected_slides=4)
        assert valid, f"Validation failed: {msg}"
        print(f"✅ Output validated: {msg}")
        
        # Step 5: Verify file size
        size = os.path.getsize(output_path)
        print(f"✅ File size: {size:,} bytes")
        
        # Verify it's reasonable (> 1KB for 4 slides)
        assert size > 1024, f"File too small: {size} bytes"
    
    print("\n✅ TEST 5 PASSED: Real-world scenario working\n")
    return True


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 70)
    print("PPTX SKILL IMPROVEMENTS - COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    
    tests = [
        ("Basic Functionality", test_basic_functionality),
        ("Directory Organization", test_directory_organization),
        ("Presentation Creation", test_presentation_creation),
        ("Error Handling", test_error_handling),
        ("Real-World Scenario", test_real_world_scenario),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, True, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"\n❌ {test_name} FAILED: {e}\n")
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if error:
            print(f"       Error: {error}")
    
    print("\n" + "-" * 70)
    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print("=" * 70)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Improvements are working correctly.\n")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.\n")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
