"""Helper utilities for PPTX skill execution.

Provides dependency checking, validation, and error handling utilities
to improve success rate of PPTX generation tasks.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple, Optional


def check_python_version(min_major: int = 3, min_minor: int = 8) -> bool:
    """Check if Python version meets minimum requirements.
    
    Args:
        min_major: Minimum major version (default: 3)
        min_minor: Minimum minor version (default: 8)
    
    Returns:
        True if version is sufficient, False otherwise
    """
    current = sys.version_info
    return (current.major > min_major or 
            (current.major == min_major and current.minor >= min_minor))


def ensure_dependencies(verbose: bool = True) -> Tuple[bool, str]:
    """Check and install python-pptx if needed.
    
    This is the PRIMARY function to call before creating presentations.
    
    Args:
        verbose: If True, print status messages
    
    Returns:
        Tuple of (success: bool, message: str)
    
    Example:
        ```python
        success, msg = ensure_dependencies()
        if not success:
            raise Exception(f"Dependency check failed: {msg}")
        ```
    """
    try:
        # Try to import
        from pptx import Presentation
        
        if verbose:
            print("✅ python-pptx is already installed")
        
        return True, "Already installed"
    
    except ImportError:
        if verbose:
            print("⚠️  python-pptx not found, installing...")
        
        try:
            # Install with --user flag for safety
            subprocess.check_call([
                sys.executable,
                "-m",
                "pip",
                "install",
                "--user",
                "python-pptx"
            ])
            
            # Verify installation succeeded
            from pptx import Presentation
            
            if verbose:
                print("✅ python-pptx installed successfully")
            
            return True, "Installed successfully"
        
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to install python-pptx: {e}"
            if verbose:
                print(f"❌ {error_msg}")
            return False, error_msg
        
        except ImportError:
            error_msg = "Installation succeeded but import still fails"
            if verbose:
                print(f"❌ {error_msg}")
            return False, error_msg


def create_directories(base_path: str, subdirs: list) -> dict:
    """Create necessary directories for file organization.
    
    Args:
        base_path: Base directory (usually workspace)
        subdirs: List of subdirectories to create (e.g., ['scripts', 'presentations'])
    
    Returns:
        Dict mapping subdir name to full path
    
    Example:
        ```python
        dirs = create_directories('/workspace', ['scripts', 'presentations'])
        script_dir = dirs['scripts']  # /workspace/scripts
        pptx_dir = dirs['presentations']  # /workspace/presentations
        ```
    """
    result = {}
    base = Path(base_path)
    
    for subdir in subdirs:
        full_path = base / subdir
        full_path.mkdir(parents=True, exist_ok=True)
        result[subdir] = str(full_path)
        
        print(f"✅ Directory ready: {full_path}")
    
    return result


def validate_presentation(
    filepath: str,
    expected_slides: Optional[int] = None,
    min_size_bytes: int = 1024
) -> Tuple[bool, str]:
    """Validate PPTX file integrity.
    
    Comprehensive validation that checks:
    1. File exists
    2. File size is reasonable
    3. File can be opened by python-pptx
    4. Slide count matches expectation (if provided)
    
    Args:
        filepath: Path to PPTX file
        expected_slides: Expected number of slides (optional)
        min_size_bytes: Minimum acceptable file size (default: 1KB)
    
    Returns:
        Tuple of (is_valid: bool, message: str)
    
    Example:
        ```python
        valid, msg = validate_presentation('output.pptx', expected_slides=10)
        if not valid:
            raise Exception(f"Validation failed: {msg}")
        print(f"✅ {msg}")
        ```
    """
    from pptx import Presentation
    
    # Check 1: File exists
    if not os.path.exists(filepath):
        return False, f"File does not exist: {filepath}"
    
    # Check 2: File size
    size = os.path.getsize(filepath)
    if size == 0:
        return False, "File is empty (0 bytes)"
    if size < min_size_bytes:
        return False, f"File suspiciously small: {size} bytes (min: {min_size_bytes})"
    
    # Check 3: Can open with python-pptx
    try:
        prs = Presentation(filepath)
    except Exception as e:
        return False, f"Cannot open file: {e}"
    
    # Check 4: Slide count
    actual_slides = len(prs.slides)
    if expected_slides is not None and actual_slides != expected_slides:
        return False, f"Expected {expected_slides} slides, got {actual_slides}"
    
    # All checks passed
    return True, f"Valid PPTX with {actual_slides} slides ({size:,} bytes)"


def quick_test() -> Tuple[bool, str]:
    """Create a minimal test PPTX to verify everything works.
    
    This creates a simple 1-slide presentation to /tmp/test.pptx
    to verify the entire pipeline works.
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        from pptx import Presentation
        
        # Create minimal presentation
        prs = Presentation()
        slide_layout = prs.slide_layouts[0]  # Title slide
        slide = prs.slides.add_slide(slide_layout)
        
        # Add title
        title = slide.shapes.title
        title.text = "Test Slide"
        
        # Save to temp location
        test_path = '/tmp/test_pptx_validation.pptx'
        prs.save(test_path)
        
        # Validate
        valid, msg = validate_presentation(test_path, expected_slides=1)
        
        if not valid:
            return False, f"Test validation failed: {msg}"
        
        # Clean up
        os.remove(test_path)
        
        return True, "Quick test passed - PPTX generation working"
    
    except Exception as e:
        return False, f"Quick test failed: {e}"


def safe_create_presentation(
    output_path: str,
    create_func,
    expected_slides: Optional[int] = None
) -> Tuple[bool, str]:
    """Safely create a presentation with full validation.
    
    This is the RECOMMENDED way to create presentations. It:
    1. Checks dependencies
    2. Creates necessary directories
    3. Calls your creation function
    4. Validates the output
    
    Args:
        output_path: Where to save the PPTX file
        create_func: Function that creates and saves the presentation
                    Should accept no arguments and return nothing
        expected_slides: Expected number of slides for validation
    
    Returns:
        Tuple of (success: bool, message: str)
    
    Example:
        ```python
        def my_presentation():
            prs = Presentation()
            # ... add slides ...
            prs.save('presentations/my.pptx')
        
        success, msg = safe_create_presentation(
            'presentations/my.pptx',
            my_presentation,
            expected_slides=10
        )
        
        if success:
            print(f"✅ {msg}")
        else:
            print(f"❌ {msg}")
        ```
    """
    try:
        # Step 1: Check dependencies
        print("Step 1/4: Checking dependencies...")
        deps_ok, deps_msg = ensure_dependencies(verbose=False)
        if not deps_ok:
            return False, f"Dependency check failed: {deps_msg}"
        
        # Step 2: Create directories
        print("Step 2/4: Creating directories...")
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # Step 3: Create presentation
        print("Step 3/4: Creating presentation...")
        create_func()
        
        # Step 4: Validate
        print("Step 4/4: Validating output...")
        valid, msg = validate_presentation(output_path, expected_slides)
        
        if not valid:
            return False, f"Validation failed: {msg}"
        
        return True, f"Success! {msg}"
    
    except Exception as e:
        return False, f"Creation failed: {e}"


# CLI interface for testing
if __name__ == "__main__":
    print("=" * 60)
    print("PPTX Helper Utilities - Test Suite")
    print("=" * 60)
    
    # Test 1: Python version
    print("\n[Test 1] Checking Python version...")
    if check_python_version():
        print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} OK")
    else:
        print(f"❌ Python {sys.version_info.major}.{sys.version_info.minor} too old (need 3.8+)")
    
    # Test 2: Dependencies
    print("\n[Test 2] Checking/installing dependencies...")
    success, msg = ensure_dependencies()
    print(f"Result: {msg}")
    
    # Test 3: Quick test
    print("\n[Test 3] Running quick test...")
    success, msg = quick_test()
    print(f"Result: {msg}")
    
    # Test 4: Directory creation
    print("\n[Test 4] Testing directory creation...")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        dirs = create_directories(tmpdir, ['scripts', 'presentations', 'test'])
        print(f"Created directories: {list(dirs.keys())}")
    
    print("\n" + "=" * 60)
    print("Test suite completed!")
    print("=" * 60)
