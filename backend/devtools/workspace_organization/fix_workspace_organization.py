#!/usr/bin/env python3
"""
Fix workspace organization and prevent pptxgenjs API errors.

Problems identified:
1. Workspace root is cluttered with mixed files (PPTX, JS scripts, etc.)
2. LLM uses wrong pptxgenjs API (pres.defineTheme() doesn't exist)
3. Dependencies are re-installed unnecessarily

Solutions:
1. Create organized subdirectory structure in workspace/
2. Add correct pptxgenjs API examples to skill documentation
3. Implement dependency state tracking
"""

import os
from pathlib import Path

workspace = Path('/Users/xuan.lx/Documents/x-agent/x-agent/workspace')

print("=" * 80)
print("Workspace Organization Fix")
print("=" * 80)

# Create organized directory structure
subdirs = {
    'presentations': 'Generated PPTX files',
    'scripts': 'Auto-generated JavaScript/Python scripts',
    'resources': 'Images, templates, and other resources',
    'temp': 'Temporary working files'
}

print("\n📁 Creating organized directory structure:")
for subdir, description in subdirs.items():
    dir_path = workspace / subdir
    if not dir_path.exists():
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Created: {subdir}/ - {description}")
    else:
        print(f"  ℹ️  Already exists: {subdir}/")

# List current files in root
print("\n📋 Current files in workspace root:")
root_files = [f for f in workspace.iterdir() if f.is_file()]
if root_files:
    for f in sorted(root_files):
        print(f"  - {f.name} ({f.stat().st_size} bytes)")
else:
    print("  (empty)")

# List subdirectories
print("\n📋 Existing subdirectories:")
root_dirs = [d for d in workspace.iterdir() if d.is_dir()]
if root_dirs:
    for d in sorted(root_dirs):
        print(f"  - {d.name}/")
else:
    print("  (none)")

print("\n" + "=" * 80)
print("Recommendations:")
print("=" * 80)
print("""
1. **Move existing generated files to appropriate subdirectories:**
   - *.pptx → presentations/
   - create_*.js, *_script.js → scripts/
   - *.html, *.json → resources/

2. **Update LLM instructions:**
   - Always save new files to appropriate subdirectories
   - Use relative paths from workspace root
   - Reference files using workspace/{subdir}/{filename}

3. **Example file organization:**
   workspace/
   ├── presentations/
   │   ├── steel_presentation.pptx
   │   └── product_intro.pptx
   ├── scripts/
   │   ├── create_steel_presentation.js
   │   └── html2pptx_converter.js
   ├── resources/
   │   ├── template.html
   │   └── data.json
   └── temp/
       └── (working files)

4. **Prevent API errors:**
   - Add correct pptxgenjs API examples to SKILL.md
   - Explicitly warn against defineTheme() (doesn't exist)
   - Provide working code snippets
""")

print("\n" + "=" * 80)
print("Next Steps:")
print("=" * 80)
print("1. Review and approve directory structure")
print("2. Move existing files to appropriate subdirectories")
print("3. Update skill documentation with correct API usage")
print("4. Test with new PPT generation request")
