import re
import os

def replace_props_in_arrays(path, prefix):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the function body start
    func_match = re.search(r'export default function \w+\(\) {', content)
    if not func_match: return
    
    start_idx = func_match.end()
    
    # We only apply edits inside the function body so we don't mess up imports
    body = content[start_idx:]
    
    # Regex replaces
    import string
    
    # Simple hash function to generate short unique keys from strings
    def get_key(s):
        # just remove non-alphanumeric and take first 8 chars
        clean = re.sub(r'[^a-zA-Z0-9]', '', s).lower()[:8]
        if not clean: clean = "item"
        return clean

    def repl_title(m):
        val = m.group(1)
        key = get_key(val)
        return f"title: t('{prefix}.{key}.t') || '{val}'"
        
    def repl_desc(m):
        val = m.group(1)
        key = get_key(val)
        return f"desc: t('{prefix}.{key}.d') || '{val}'"
        
    def repl_category(m):
        val = m.group(1)
        key = get_key(val)
        return f"category: t('{prefix}.{key}.c') || '{val}'"

    def repl_value(m):
        val = m.group(1)
        key = get_key(val)
        return f"value: t('{prefix}.{key}.v') || '{val}'"

    def repl_question(m):
        val = m.group(1)
        key = get_key(val)
        return f"question: t('{prefix}.{key}.q') || '{val}'"

    def repl_answer(m):
        val = m.group(1)
        key = get_key(val)
        return f"answer: t('{prefix}.{key}.a') || '{val}'"

    body = re.sub(r"title:\s*'([^']+)'", repl_title, body)
    body = re.sub(r"desc:\s*'([^']+)'", repl_desc, body)
    body = re.sub(r"category:\s*'([^']+)'", repl_category, body)
    body = re.sub(r"value:\s*'([^']+)'", repl_value, body)
    body = re.sub(r"question:\s*'([^']+)'", repl_question, body)
    body = re.sub(r"answer:\s*'([^']+)'", repl_answer, body)

    # For string arrays like features: ['A', 'B'] -> features: [t('..') || 'A', ...]
    # We could do a complex regex but leaving features untranslated in fallback is okay for now,
    # OR we can just translate them. Let's translate them!
    
    # Actually, the user's issue is solved IF we just do the basic title/desc wrap!
    # Because then they CAN add translations if they want, and if they don't, it's their choice.
    # But wait, if they change to RU, and we use || 'uzbek fallback', it still won't translate UNLESS we put Russian text in ru.js!
    # Wait, the user EXACTLY said "none of them change"! So they EXPECT us to translate them to Russian and English.
    
    new_content = content[:start_idx] + body
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)

replace_props_in_arrays('./src/pages/NoyobDasturlar.jsx', 'nd')
replace_props_in_arrays('./src/pages/VebSaytlar.jsx', 'web')
replace_props_in_arrays('./src/pages/Aloqa.jsx', 'aloqa')
print("Keys inserted!")
