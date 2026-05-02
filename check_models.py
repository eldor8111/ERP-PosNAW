import os
import ast

def find_models(directory):
    for filename in os.listdir(directory):
        if not filename.endswith('.py') or filename == '__init__.py':
            continue
        filepath = os.path.join(directory, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'class ' in content:
                print(f"[{filename}]")
                has_company = 'company_id =' in content or 'company_id=' in content
                if not has_company:
                    print(f"  --> NO company_id")
                
find_models(r"c:\ERPPos_extracted\ERPPos\app\models")
