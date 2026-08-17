import os
import ast

def find_missing_company_filters(directory):
    for filename in os.listdir(directory):
        if not filename.endswith('.py'):
            continue
        filepath = os.path.join(directory, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            print(f"Syntax error in {filename}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                body = ast.get_source_segment(content, node)
                if not body:
                    continue
                # Check if it's an endpoint (has @router. decorator)
                is_endpoint = any(
                    isinstance(dec, ast.Call) and 
                    isinstance(dec.func, ast.Attribute) and 
                    isinstance(dec.func.value, ast.Name) and 
                    dec.func.value.id == 'router'
                    for dec in node.decorator_list
                )
                if not is_endpoint:
                    continue
                
                # Check if it queries the db
                if 'db.query(' in body or 'db.execute(' in body:
                    # Look for company_id check
                    if 'company_id' not in body and 'current_user' in body:
                        print(f"[{filename}] {node.name} has queries but NO company_id filter!")

find_missing_company_filters(r"c:\ERPPos_extracted\ERPPos\app\routers")
