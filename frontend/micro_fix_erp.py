import re
import os

path = r'c:\ERPPos_extracted\ERPPos\frontend\src\pages\ERPTizim.jsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. find tariffs array
tariffs_match = re.search(r'const tariffs = \[\n.*?^\]\n', content, re.MULTILINE | re.DOTALL)
if tariffs_match:
    arr_code = tariffs_match.group(0)
    # remove from top level
    content = content.replace(arr_code, '')
    
    # insert inside the component
    func_start = re.search(r'export default function ERPTizim\(\) {\n(.*?const { t } = useLang\(\)\n)', content, re.MULTILINE | re.DOTALL)
    if func_start:
        rep = func_start.group(0) + '\n' + arr_code
        content = content.replace(func_start.group(0), rep)
        
        # Now wrap titles in tariffs
        def get_key(s):
            clean = re.sub(r'[^a-zA-Z0-9]', '', s).lower()[:8]
            if not clean: clean = "item"
            return clean
            
        def repl_wrap(match):
            prop = match.group(1)
            val = match.group(2)
            key = get_key(val)
            return f"{prop}: t('erp.tariffs.{key}.{prop}') || '{val}'"

        # Apply regex ONLY to the tariffs definition we just moved inside, actually applying globally is fine if we limit it to the body
        start_idx = content.find('export default function ERPTizim() {')
        head = content[:start_idx]
        body = content[start_idx:]
        
        # Only modify the tariffs array inside body
        tariffs_inside = re.search(r'const tariffs = \[\n.*?^\]\n', body, re.MULTILINE | re.DOTALL)
        if tariffs_inside:
            arr_str = tariffs_inside.group(0)
            arr_str = re.sub(r"(name|price|badge|desc|hint):\s*'([^']+)'", repl_wrap, arr_str)
            body = body.replace(tariffs_inside.group(0), arr_str)
            
        content = head + body

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("ERPTizim tariffs fixed!")
