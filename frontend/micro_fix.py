import re

def process_file(path, comp_name, arrays):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Find component start
    match = re.search(f'export default function {comp_name}\\s*\\(\\)\\s*\\{{', content)
    if not match:
        print(f"Not found {comp_name}")
        return
    
    # 2. Extract arrays
    arrays_code = []
    for arr in arrays:
        # Match const arr = [ ... ] up to the first ] that is at indentation level 0 (but Javascript has them everywhere)
        # So instead we do a simpler match or just use regex matching blocks
        # using a simple approach: find "const arr = [\n" and match down to "\n]\n"
        arr_match = re.search(r'const ' + arr + r' = \[.*?^\]\n', content, re.MULTILINE | re.DOTALL)
        if arr_match:
            # remove from global scope
            content = content.replace(arr_match.group(0), '')
            code = arr_match.group(0)
            arrays_code.append(code)
            
    if not arrays_code:
        print(f"No arrays found for {comp_name}")
        return
    
    # 3. Add to inside component
    insert_point = r'const { t } = useLang\(\)\n'
    import_match = re.search(insert_point, content)
    if import_match:
        replacement = import_match.group(0) + '\n' + '\n'.join(arrays_code)
        content = content.replace(import_match.group(0), replacement)
        
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Processed {comp_name}")

process_file('./src/pages/NoyobDasturlar.jsx', 'NoyobDasturlar', ['solutionTypes', 'devProcess', 'techStack', 'projects'])
process_file('./src/pages/VebSaytlar.jsx', 'VebSaytlar', ['services', 'process', 'techStack'])
process_file('./src/pages/Aloqa.jsx', 'Aloqa', ['contacts', 'workingHours', 'faq'])
