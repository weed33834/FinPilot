"""section_c_frontend_routes

板块C：补齐前端 404 页面对应的后端数据模型.
- 扩展 api_keys 表（tenant_id/key_prefix/first_used_at/usage_count/expires_at/rotated_from/updated_at）
- 新建 access_policies / hitl_requests / eval_records / reflection_logs 四张表

Revision ID: c2f3a4b5c6d7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 扩展 api_keys 表（板块C：补齐前端 ApiKeysPage 期望的字段）
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('key_prefix', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('first_used_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('usage_count', sa.Integer(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('expires_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('rotated_from', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_api_keys_tenant_active', ['tenant_id', 'is_active'], unique=False)
        batch_op.create_index('ix_api_keys_rotated_from', ['rotated_from'], unique=False)

    # 2. access_policies 表（ABAC 访问策略）
    op.create_table(
        'access_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('resource_type', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('effect', sa.String(length=16), nullable=True, server_default='allow'),
        sa.Column('priority', sa.Integer(), nullable=True, server_default='100'),
        sa.Column('conditions', sa.JSON(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('1')),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_access_policies_tenant_id', 'access_policies', ['tenant_id'], unique=False)
    op.create_index('ix_access_policies_tenant_resource', 'access_policies', ['tenant_id', 'resource_type', 'action'], unique=False)

    # 3. hitl_requests 表（Human-in-the-loop 人工介入请求）
    op.create_table(
        'hitl_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('action_type', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('risk_level', sa.String(length=16), nullable=True, server_default='medium'),
        sa.Column('action_params', sa.JSON(), nullable=True),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=True, server_default='pending'),
        sa.Column('requested_by', sa.String(length=100), nullable=True),
        sa.Column('resolved_by', sa.String(length=100), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_hitl_tenant_id', 'hitl_requests', ['tenant_id'], unique=False)
    op.create_index('ix_hitl_tenant_status', 'hitl_requests', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_hitl_tenant_risk', 'hitl_requests', ['tenant_id', 'risk_level'], unique=False)

    # 4. eval_records 表（NL2SQL / RAG 评估记录）
    op.create_table(
        'eval_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('eval_type', sa.String(length=16), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('eval_method', sa.String(length=64), nullable=True),
        sa.Column('score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_eval_tenant_id', 'eval_records', ['tenant_id'], unique=False)
    op.create_index('ix_eval_tenant_type', 'eval_records', ['tenant_id', 'eval_type'], unique=False)
    op.create_index('ix_eval_tenant_created', 'eval_records', ['tenant_id', 'created_at'], unique=False)

    # 5. reflection_logs 表（错误自省日志）
    op.create_table(
        'reflection_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('task_name', sa.String(length=128), nullable=True),
        sa.Column('task_id', sa.String(length=128), nullable=True),
        sa.Column('resource_type', sa.String(length=64), nullable=True),
        sa.Column('resource_id', sa.String(length=64), nullable=True),
        sa.Column('exception_type', sa.String(length=255), nullable=False),
        sa.Column('exception_message', sa.Text(), nullable=False),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('error_category', sa.String(length=32), nullable=True, server_default='unknown'),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('suggested_fix', sa.Text(), nullable=True),
        sa.Column('retried', sa.Boolean(), nullable=True, server_default=sa.text('0')),
        sa.Column('resolved', sa.Boolean(), nullable=True, server_default=sa.text('0')),
        sa.Column('resolution', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reflection_tenant_id', 'reflection_logs', ['tenant_id'], unique=False)
    op.create_index('ix_reflection_task_id', 'reflection_logs', ['task_id'], unique=False)
    op.create_index('ix_reflection_tenant_category', 'reflection_logs', ['tenant_id', 'error_category'], unique=False)
    op.create_index('ix_reflection_tenant_resolved', 'reflection_logs', ['tenant_id', 'resolved'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_reflection_tenant_resolved', table_name='reflection_logs')
    op.drop_index('ix_reflection_tenant_category', table_name='reflection_logs')
    op.drop_index('ix_reflection_task_id', table_name='reflection_logs')
    op.drop_index('ix_reflection_tenant_id', table_name='reflection_logs')
    op.drop_table('reflection_logs')

    op.drop_index('ix_eval_tenant_created', table_name='eval_records')
    op.drop_index('ix_eval_tenant_type', table_name='eval_records')
    op.drop_index('ix_eval_tenant_id', table_name='eval_records')
    op.drop_table('eval_records')

    op.drop_index('ix_hitl_tenant_risk', table_name='hitl_requests')
    op.drop_index('ix_hitl_tenant_status', table_name='hitl_requests')
    op.drop_index('ix_hitl_tenant_id', table_name='hitl_requests')
    op.drop_table('hitl_requests')

    op.drop_index('ix_access_policies_tenant_resource', table_name='access_policies')
    op.drop_index('ix_access_policies_tenant_id', table_name='access_policies')
    op.drop_table('access_policies')

    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.drop_index('ix_api_keys_rotated_from')
        batch_op.drop_index('ix_api_keys_tenant_active')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('rotated_from')
        batch_op.drop_column('expires_at')
        batch_op.drop_column('usage_count')
        batch_op.drop_column('first_used_at')
        batch_op.drop_column('key_prefix')
        batch_op.drop_column('tenant_id')
