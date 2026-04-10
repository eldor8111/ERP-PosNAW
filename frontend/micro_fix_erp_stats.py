import re

path = r'c:\ERPPos_extracted\ERPPos\frontend\src\pages\ERPTizim.jsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

def get_key(s):
    clean = re.sub(r'[^a-zA-Z0-9]', '', s).lower()[:8]
    if not clean: clean = "item"
    return clean

def repl_wrap(match):
    prop = match.group(1)
    val = match.group(2)
    key = get_key(val)
    return f"{prop}: t('erp.stats.{key}.{prop}') || '{val}'"

# Find modules array
start_idx = content.find('const modules = [')
if start_idx != -1:
    end_idx = content.find(']', start_idx)  # Wait, ] might be just the first. Let's do a replace over the whole body
    body = content[start_idx:]
    body = re.sub(r"(val|label):\s*'([^']+)'", repl_wrap, body)
    content = content[:start_idx] + body

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("ERPTizim stats fixed!")
