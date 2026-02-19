#!/usr/bin/env python3
"""
Automatically organize workspace files into appropriate subdirectories.
"""

import shutil
from pathlib import Path

workspace = Path('/Users/xuan.lx/Documents/x-agent/x-agent/workspace')

print("=" * 80)
print("Auto-organizing Workspace Files")
print("=" * 80)

# Define file patterns and their target directories
patterns = {
    'presentations': ['*.pptx'],
    'scripts': ['create_*.js', 'create_*.py', '*_script.js', '*.py'],
    'resources': ['*.html', '*.json', '*.xml', '*.md'],
}

# Move files
moved_count = 0
for target_dir, extensions in patterns.items():
    target_path = workspace / target_dir
    
    for ext in extensions:
        # Skip if pattern contains wildcard in middle
        if '*' in ext:
            prefix = ext.split('*')[0]
            suffix = ext.split('*')[1] if '*' in ext else ''
            
            for f in workspace.iterdir():
                if f.is_file() and f.name.startswith(prefix) and f.name.endswith(suffix):
                    # Skip documentation files
                    if f.name in ['AGENTS.md', 'BOOTSTRAP.md', 'HEARTBEAT.md', 
                                  'IDENTITY.md', 'MEMORY.md', 'OWNER.md', 
                                  'SPIRIT.md', 'TOOLS.md']:
                        continue
                    
                    dest = target_path / f.name
                    if not dest.exists():
                        shutil.move(str(f), str(dest))
                        print(f"✅ Moved: {f.name} → {target_dir}/")
                        moved_count += 1
                    else:
                        print(f"⚠️  Skipped (exists): {f.name}")
        else:
            # Simple extension match
            for f in workspace.glob(f"*{ext}"):
                if f.is_file():
                    dest = target_path / f.name
                    if not dest.exists():
                        shutil.move(str(f), str(dest))
                        print(f"✅ Moved: {f.name} → {target_dir}/")
                        moved_count += 1
                    else:
                        print(f"⚠️  Skipped (exists): {f.name}")

print("\n" + "=" * 80)
print(f"Organization complete! Moved {moved_count} files.")
print("=" * 80)
