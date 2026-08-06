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

# Find heads (revisions that no one points to)
pointed_to = set(revisions.values())
heads = [rev for rev in revisions.keys() if rev not in pointed_to]
print(f"Heads: {heads}")

