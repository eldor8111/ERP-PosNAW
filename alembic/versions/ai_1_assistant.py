"""E-code AI yordamchi (Claude): ai_conversations, ai_messages, ai_files jadvallari,
feature_packages ga AI cheklov ustunlari va nofaol "AI yordamchi" paketi.

Additiv: mavjud jadvallarga faqat nullable ustunlar qo'shiladi. Paket NOFAOL yaratiladi —
narx va limitlarni super admin kiritadi va faollashtiradi.

Revision ID: ai_1
Revises: d3_3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'ai_1'
down_revision: Union[str, Sequence[str], None] = 'd3_3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables():
    from alembic import context
    if context.is_offline_mode():   # --sql rejimi: bazaga ulanmasdan SQL chiqarish
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _tables()
    if 'ai_conversations' not in existing:
        op.create_table(
            'ai_conversations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('title', sa.String(200), nullable=True),
            sa.Column('model', sa.String(60), nullable=False),
            sa.Column('context', sa.JSON(), nullable=True),
            sa.Column('tools_hash', sa.String(64), nullable=True),
            sa.Column('turns', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('busy_until', sa.DateTime(), nullable=True),
            sa.Column('pending_note', sa.Text(), nullable=True),
            sa.Column('has_files', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_ai_conversations_id', 'ai_conversations', ['id'])
        op.create_index('ix_ai_conversations_company_id', 'ai_conversations', ['company_id'])
        op.create_index('ix_ai_conversations_user_id', 'ai_conversations', ['user_id'])

    if 'ai_messages' not in existing:
        op.create_table(
            'ai_messages',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('ai_conversations.id', ondelete='CASCADE'),
                      nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('role', sa.String(16), nullable=False),
            sa.Column('kind', sa.String(16), nullable=False),
            sa.Column('content', sa.JSON(), nullable=False),
            sa.Column('text', sa.Text(), nullable=True),
            sa.Column('actions', sa.JSON(), nullable=True),
            sa.Column('model', sa.String(60), nullable=True),
            sa.Column('stop_reason', sa.String(30), nullable=True),
            sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('cache_read_tokens', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('cache_write_tokens', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('cost_usd', sa.Numeric(12, 6), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_ai_messages_id', 'ai_messages', ['id'])
        op.create_index('ix_ai_messages_conversation_id', 'ai_messages', ['conversation_id'])
        op.create_index('ix_ai_messages_company_id', 'ai_messages', ['company_id'])
        op.create_index('ix_ai_messages_user_id', 'ai_messages', ['user_id'])
        op.create_index('ix_ai_messages_created_at', 'ai_messages', ['created_at'])

    if 'ai_files' not in existing:
        op.create_table(
            'ai_files',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('file_id', sa.String(100), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('conversation_id', sa.Integer(), nullable=True),
            sa.Column('filename', sa.String(200), nullable=True),
            sa.Column('media_type', sa.String(50), nullable=False),
            sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_ai_files_id', 'ai_files', ['id'])
        op.create_index('ix_ai_files_file_id', 'ai_files', ['file_id'], unique=True)
        op.create_index('ix_ai_files_company_id', 'ai_files', ['company_id'])
        op.create_index('ix_ai_files_user_id', 'ai_files', ['user_id'])
        op.create_index('ix_ai_files_conversation_id', 'ai_files', ['conversation_id'])

    op.execute("ALTER TABLE feature_packages ADD COLUMN IF NOT EXISTS ai_monthly_limit INTEGER")
    op.execute("ALTER TABLE feature_packages ADD COLUMN IF NOT EXISTS ai_daily_user_limit INTEGER")
    op.execute("ALTER TABLE feature_packages ADD COLUMN IF NOT EXISTS ai_allow_actions BOOLEAN")
    op.execute("ALTER TABLE feature_packages ADD COLUMN IF NOT EXISTS ai_allow_vision BOOLEAN")

    # Nofaol paket: narx va limitlarni super admin kiritib, faollashtiradi
    op.execute(
        "INSERT INTO feature_packages (code, name, description, price_per_month, is_active, sort_order, "
        "ai_monthly_limit, ai_daily_user_limit, ai_allow_actions, ai_allow_vision, created_at, updated_at) "
        "SELECT 'ai_assistant', 'AI yordamchi', "
        "'E-code AI: savdo, qoldiq, qarzlar bo''yicha savollarga javob, rasmdan kirim va tasdiqli amallar', "
        "0, false, 90, 0, 0, true, true, now(), now() "
        "WHERE NOT EXISTS (SELECT 1 FROM feature_packages WHERE code = 'ai_assistant')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_packages WHERE code LIKE 'ai_assistant%'")
    op.execute("ALTER TABLE feature_packages DROP COLUMN IF EXISTS ai_allow_vision")
    op.execute("ALTER TABLE feature_packages DROP COLUMN IF EXISTS ai_allow_actions")
    op.execute("ALTER TABLE feature_packages DROP COLUMN IF EXISTS ai_daily_user_limit")
    op.execute("ALTER TABLE feature_packages DROP COLUMN IF EXISTS ai_monthly_limit")
    op.drop_table('ai_files')
    op.drop_table('ai_messages')
    op.drop_table('ai_conversations')
