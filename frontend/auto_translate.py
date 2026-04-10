import os
import re
import string

def get_key(s):
    clean = re.sub(r'[^a-zA-Z0-9]', '', s).lower()[:15]
    if not clean: clean = "txt"
    return clean

# A set of words to completely ignore during translation
IGNORE_EXACT = {'+', '-', '/', '%', '&', '#', 'UZS', '$', '€', 'POS', 'CRM', 'API', 'PDF', 'Excel', 'ID', 'UUID', 'F-code', 'aHOST', 'ERP'}

def is_valid_text(text):
    text = text.strip()
    if not text: return False
    if text in IGNORE_EXACT: return False
    # If it's just numbers and symbols
    if not re.search(r'[a-zA-Zа-яА-ЯўЎқҚғҒҳҲ]', text):
        return False
    # If it looks like a variable name or condition like "val === 1"
    if '===' in text or '=>' in text or '&&' in text or '||' in text:
        return False
    return True

def auto_translate_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    filename = os.path.basename(filepath)
    comp_prefix = filename.split('.')[0].lower()[:5]
    
    # Check/add import
    if 'useLang' not in content:
        # Add import useLang
        import_stmt = "import { useLang } from '../../context/LangContext';\n"
        if 'import React' in content:
            content = content.replace('import React', import_stmt + 'import React', 1)
        else:
            content = import_stmt + content

    # Check/add instantiation
    if 'const { t } = useLang();' not in content:
        # insert after the main component declaration
        # e.g., export default function User() { 
        func_match = re.search(r'export default function [A-Z]\w*\([^)]*\) {\n', content)
        if func_match:
            content = content.replace(func_match.group(0), func_match.group(0) + "  const { t } = useLang();\n")
        else:
            # Maybe const Component = () => {
            arrow_match = re.search(r'const [A-Z]\w* = \([^)]*\) => {\n', content)
            if arrow_match:
                content = content.replace(arrow_match.group(0), arrow_match.group(0) + "  const { t } = useLang();\n")

    extracted_keys = {}
    
    # 1. Replace > Text <
    # We want to match > followed by text, and ends with <
    # But carefully avoiding JSX tags and expressions { ... }
    # A simple approach: regex >\s*([A-Za-zА-Яа-яЎўҚқҒғҲҳ' ]+?[A-Za-zА-Яа-яЎўҚқҒғҲҳ0-9' .!?,-:]*?)\s*<
    
    def repl_text_node(m):
        full = m.group(0)
        inner = m.group(1).strip()
        if not is_valid_text(inner): return full
        
        # Don't replace if it's already translated or has {}
        if '{' in inner or '}' in inner: return full
        
        # For simplicity, if it contains an apostrophe, escape it for the fallback
        fallback = inner.replace("'", "\\'")
        key = f"admin.{comp_prefix}.{get_key(inner)}"
        extracted_keys[key] = inner
        
        # Replace the inner text with {t('key') || 'inner'}
        # But preserve surrounding spaces
        left_space = m.group(0)[1:m.group(0).find(m.group(1))]
        right_space = m.group(0)[m.group(0).find(m.group(1))+len(m.group(1)):-1]
        
        return f">{left_space}{{t('{key}') || '{fallback}'}}{right_space}<"

    # Pattern for clean text nodes between > and <
    # It must not contain <, >, {, or }
    text_node_pattern = re.compile(r'>([^<>{}]*[a-zA-Zа-яА-ЯўЎқҚғҒҳҲ][^<>{}]*)<')
    content = text_node_pattern.sub(repl_text_node, content)

    # 2. Replace placeholder="Text"
    def repl_placeholder(m):
        full = m.group(0)
        attr = m.group(1) # placeholder or label or title
        quote = m.group(2)
        inner = m.group(3)
        if not is_valid_text(inner): return full
        if '{' in inner or '}' in inner: return full
        
        fallback = inner.replace("'", "\\'")
        key = f"admin.{comp_prefix}.{get_key(inner)}"
        extracted_keys[key] = inner
        
        return f"{attr}={{t('{key}') || '{fallback}'}}"

    attr_pattern = re.compile(r'\b(placeholder|label|title)=([\'"])([^>]+?)\2')
    content = attr_pattern.sub(repl_placeholder, content)

    # If changes made, write out
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filename} with {len(extracted_keys)} strings.")
        return extracted_keys
    return {}

def process_all():
    base_dir = r"c:\ERPPos_extracted\ERPPos\frontend\src\pages\admin"
    all_keys = {}
    for filename in os.listdir(base_dir):
        if filename.endswith(".jsx"):
            filepath = os.path.join(base_dir, filename)
            keys = auto_translate_file(filepath)
            all_keys.update(keys)

    # Print keys so we can copy them if needed or write to a dict file
    if all_keys:
        import json
        with open("extracted_keys.json", "w", encoding='utf-8') as f:
            json.dump(all_keys, f, ensure_ascii=False, indent=2)
        print(f"Total {len(all_keys)} keys extracted.")

process_all()
