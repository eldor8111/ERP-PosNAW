import os
import re

versions_dir = r'D:\EcodeWeb\alembic\versions'
files = [f for f in os.listdir(versions_dir) if f.endswith('.py')]

for f in files:
    with open(os.path.join(versions_dir, f), 'r', encoding='utf-8') as file:
        content = file.read()
        if 'd5f717cb38e5' in content:
            print(f"File {f} mentions d5f717cb38e5")
