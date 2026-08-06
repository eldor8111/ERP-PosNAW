import os
import re

versions_dir = r'D:\EcodeWeb\alembic\versions'
files = [f for f in os.listdir(versions_dir) if f.endswith('.py')]

revisions = {}
for f in files:
    with open(os.path.join(versions_dir, f), 'r', encoding='utf-8') as file:
        content = file.read()
        rev_match = re.search(r"revision.*?=\s*['\"]([^'\"]+)['\"]", content)
        down_match = re.search(r"down_revision.*?=\s*['\"]([^'\"]+)['\"]", content)
        
        rev = rev_match.group(1) if rev_match else None
        down = down_match.group(1) if down_match else None
        
        if rev:
            revisions[rev] = down

print(f"Total files: {len(files)}")
print(f"Missing down_revisions:")
for rev, down in revisions.items():
    if down and down not in revisions:
        print(f"{rev} points to missing {down}")
