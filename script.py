import re

file_path = r'D:\EcodeWeb\alembic\versions\92e3c075c1b5_create_user_wallets_table.py'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace upgrade and downgrade with pass
new_text = re.sub(r'def upgrade\(\) -> None:.*?def downgrade\(\) -> None:', 'def upgrade() -> None:\n    pass\n\ndef downgrade() -> None:', text, flags=re.DOTALL)
new_text = re.sub(r'def downgrade\(\) -> None:.*', 'def downgrade() -> None:\n    pass\n', new_text, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_text)

