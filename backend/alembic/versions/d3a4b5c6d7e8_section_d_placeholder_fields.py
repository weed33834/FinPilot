"""section_d_placeholder_fields

板块D：占位功能补全 + 字段错位修复。
- AgentConfig 补 agent_type / prompt_id / max_iterations / temperature 列
- LlmProvider 补 updated_at 列
- LlmModel 补 parameters 列
- SearchEngine 补 tenant_id / extra_params / priority 列，并继承 TenantMixin
- 新建 memories 表（长期记忆）
- 新建 system_settings 表（系统设置持久化）

说明：运行时由 finpilot/database/connection.py 的 _apply_schema_patches()
幂等补列，本迁移文件用于 alembic 历史记录与生产环境（PG/MySQL）升级。

Revision ID: d3a4b5c6d7e8
Revises: c2f3a4b5c6d7
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'c2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. AgentConfig 补列
    with op.batch_alter_table('agent_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('agent_type', sa.String(length=32), nullable=False, server_default='react'))
        batch_op.add_column(sa.Column('prompt_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('max_iterations', sa.Integer(), nullable=False, server_default='10'))
        batch_op.add_column(sa.Column('temperature', sa.Float(), nullable=False, server_default='0.7'))
        batch_op.create_foreign_key('fk_agent_configs_prompt_id', 'prompt_templates', ['prompt_id'], ['id'], ondelete='SET NULL')

    # 2. LlmProvider 补 updated_at
    with op.batch_alter_table('llm_providers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))

    # 3. LlmModel 补 parameters
    with op.batch_alter_table('llm_models', schema=None) as batch_op:
        batch_op.add_column(sa.Column('parameters', sa.JSON(), nullable=True))

    # 4. SearchEngine 补 tenant_id / extra_params / priority
    with op.batch_alter_table('search_engines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('extra_params', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('priority', sa.Integer(), nullable=False, server_default='0'))
        batch_op.create_index('ix_search_engines_tenant_active', ['tenant_id', 'is_active'], unique=False)

    # 5. memories 表（长期记忆）
    op.create_table(
        'memories',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('user_id', sa.String(length=100), nullable=True),
        sa.Column('category', sa.String(length=32), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('importance', sa.Integer(), nullable=True),
        sa.Column('source_conversation_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('memories', schema=None) as batch_op:
        batch_op.create_index('ix_memories_tenant_user', ['tenant_id', 'user_id'], unique=False)
        batch_op.create_index('ix_memories_tenant_category', ['tenant_id', 'category'], unique=False)
        batch_op.create_index('ix_memories_user_id', ['user_id'], unique=False)
        batch_op.create_index('ix_memories_source_conversation_id', ['source_conversation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_memories_tenant_id'), ['tenant_id'], unique=False)

    # 6. system_settings 表（系统设置持久化）
    op.create_table(
        'system_settings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'key', name='ix_system_settings_tenant_key'),
    )
    with op.batch_alter_table('system_settings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_system_settings_tenant_id'), ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('system_settings')

    with op.batch_alter_table('memories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_memories_tenant_id'))
        batch_op.drop_index('ix_memories_source_conversation_id')
        batch_op.drop_index('ix_memories_user_id')
        batch_op.drop_index('ix_memories_tenant_category')
        batch_op.drop_index('ix_memories_tenant_user')
    op.drop_table('memories')

    with op.batch_alter_table('search_engines', schema=None) as batch_op:
        batch_op.drop_index('ix_search_engines_tenant_active')
        batch_op.drop_column('priority')
        batch_op.drop_column('extra_params')
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('llm_models', schema=None) as batch_op:
        batch_op.drop_column('parameters')

    with op.batch_alter_table('llm_providers', schema=None) as batch_op:
        batch_op.drop_column('updated_at')

    with op.batch_alter_table('agent_configs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_agent_configs_prompt_id', type_='foreignkey')
        batch_op.drop_column('temperature')
        batch_op.drop_column('max_iterations')
        batch_op.drop_column('prompt_id')
        batch_op.drop_column('agent_type')
