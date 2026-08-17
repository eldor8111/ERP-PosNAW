import re

file_path = r'D:\EcodeWeb\alembic\versions\t5u6v7w8x9y0_add_bot_to_transfer.py'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

down_match = re.search(r"down_revision.*?=\s*['\"]([^'\"]+)['\"]", text)
print(down_match.group(1) if down_match else None)

