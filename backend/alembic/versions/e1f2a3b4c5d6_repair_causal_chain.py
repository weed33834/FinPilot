"""repair_causal_chain

修复因果链条断裂：补 api_keys.scopes 列、加文档/报告溯源字段、
审计对象关联、AgentConfig 接入会话、Message LLM 元数据、
新建独立审批表与 text2sql 查询记录表。

Revision ID: e1f2a3b4c5d6
Revises: b07e3d4b37b4
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'b07e3d4b37b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 修复 api_keys.scopes 列（初始迁移遗漏，导致 alembic upgrade 时 scope 鉴权崩溃）
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scopes', sa.Text(), nullable=True, comment='逗号分隔的权限范围'))

    # 2. financial_reports 加 document_id + tenant_id（溯源到上传文档）
    with op.batch_alter_table('financial_reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('document_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('tenant_id', sa.String(length=100), nullable=True))
        batch_op.create_index('ix_financial_reports_document_id', ['document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_financial_reports_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_foreign_key('fk_financial_reports_document_id', 'documents', ['document_id'], ['id'], ondelete='SET NULL')

    # 3. reports 加溯源字段，template_id 从 String(64) 改为 Integer FK
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('document_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('data_connection_id', sa.Integer(), nullable=True))
        # template_id 类型变更：String(64) -> Integer（SQLite batch 重建表时直接指定新类型）
        batch_op.alter_column('template_id',
                              existing_type=sa.String(length=64),
                              type_=sa.Integer(),
                              existing_nullable=True,
                              postgresql_using='template_id::integer')
        batch_op.create_index('ix_reports_document_id', ['document_id'], unique=False)
        batch_op.create_index('ix_reports_data_connection_id', ['data_connection_id'], unique=False)
        batch_op.create_index('ix_reports_template_id', ['template_id'], unique=False)
        batch_op.create_foreign_key('fk_reports_document_id', 'documents', ['document_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_reports_data_connection_id', 'data_connections', ['data_connection_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_reports_template_id', 'report_templates', ['template_id'], ['id'], ondelete='SET NULL')

    # 4. report_subscriptions.last_report_id 从 String(64) 改为 Integer FK
    with op.batch_alter_table('report_subscriptions', schema=None) as batch_op:
        batch_op.alter_column('last_report_id',
                              existing_type=sa.String(length=64),
                              type_=sa.Integer(),
                              existing_nullable=True,
                              postgresql_using='last_report_id::integer')
        batch_op.create_foreign_key('fk_report_subscriptions_last_report_id', 'reports', ['last_report_id'], ['id'], ondelete='SET NULL')

    # 5. audit_logs 加业务对象关联字段
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target_object_type', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('target_object_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('resource', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('ip_address', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_audit_logs_target', ['target_object_type', 'target_object_id'], unique=False)

    # 6. conversations 加 agent_config_id
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('agent_config_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_conversations_agent_config_id', ['agent_config_id'], unique=False)
        batch_op.create_foreign_key('fk_conversations_agent_config_id', 'agent_configs', ['agent_config_id'], ['id'], ondelete='SET NULL')

    # 7. messages 加 LLM 运行时元数据
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('model_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('tokens_in', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('tokens_out', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('latency_ms', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('tool_calls', sa.Text(), nullable=True))

    # 8. 新建 approvals 表（独立审批历史）
    op.create_table('approvals',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('target_object_type', sa.String(length=32), nullable=False),
        sa.Column('target_object_id', sa.Integer(), nullable=False),
        sa.Column('report_id', sa.Integer(), nullable=True),
        sa.Column('reviewer_id', sa.Integer(), nullable=True),
        sa.Column('reviewer_name', sa.String(length=100), nullable=True),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('prev_status', sa.String(length=32), nullable=True),
        sa.Column('new_status', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('approvals', schema=None) as batch_op:
        batch_op.create_index('ix_approvals_tenant_target', ['tenant_id', 'target_object_type', 'target_object_id'], unique=False)
        batch_op.create_index('ix_approvals_tenant_action', ['tenant_id', 'action'], unique=False)
        batch_op.create_index('ix_approvals_report_id', ['report_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_approvals_tenant_id'), ['tenant_id'], unique=False)

    # 9. 新建 query_records 表（text2sql 查询持久化）
    op.create_table('query_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=True),
        sa.Column('user_id', sa.String(length=100), nullable=True),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('intent', sa.String(length=64), nullable=True),
        sa.Column('sql_text', sa.Text(), nullable=True),
        sa.Column('engine', sa.String(length=16), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('rows_json', sa.Text(), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('query_records', schema=None) as batch_op:
        batch_op.create_index('ix_query_records_tenant_created', ['tenant_id', 'created_at'], unique=False)
        batch_op.create_index('ix_query_records_tenant_conv', ['tenant_id', 'conversation_id'], unique=False)
        batch_op.create_index('ix_query_records_user_id', ['user_id'], unique=False)
        batch_op.create_index('ix_query_records_conversation_id', ['conversation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_query_records_tenant_id'), ['tenant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # query_records
    with op.batch_alter_table('query_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_query_records_tenant_id'))
        batch_op.drop_index('ix_query_records_conversation_id')
        batch_op.drop_index('ix_query_records_user_id')
        batch_op.drop_index('ix_query_records_tenant_conv')
        batch_op.drop_index('ix_query_records_tenant_created')
    op.drop_table('query_records')

    # approvals
    with op.batch_alter_table('approvals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_approvals_tenant_id'))
        batch_op.drop_index('ix_approvals_report_id')
        batch_op.drop_index('ix_approvals_tenant_action')
        batch_op.drop_index('ix_approvals_tenant_target')
    op.drop_table('approvals')

    # messages
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('tool_calls')
        batch_op.drop_column('latency_ms')
        batch_op.drop_column('tokens_out')
        batch_op.drop_column('tokens_in')
        batch_op.drop_column('model_name')

    # conversations
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_constraint('fk_conversations_agent_config_id', type_='foreignkey')
        batch_op.drop_index('ix_conversations_agent_config_id')
        batch_op.drop_column('agent_config_id')

    # audit_logs
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_logs_target')
        batch_op.drop_column('ip_address')
        batch_op.drop_column('resource')
        batch_op.drop_column('target_object_id')
        batch_op.drop_column('target_object_type')

    # report_subscriptions.last_report_id 回退为 String
    with op.batch_alter_table('report_subscriptions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_report_subscriptions_last_report_id', type_='foreignkey')
        batch_op.alter_column('last_report_id',
                              existing_type=sa.Integer(),
                              type_=sa.String(length=64),
                              existing_nullable=True)

    # reports
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.drop_constraint('fk_reports_template_id', type_='foreignkey')
        batch_op.drop_constraint('fk_reports_data_connection_id', type_='foreignkey')
        batch_op.drop_constraint('fk_reports_document_id', type_='foreignkey')
        batch_op.drop_index('ix_reports_template_id')
        batch_op.drop_index('ix_reports_data_connection_id')
        batch_op.drop_index('ix_reports_document_id')
        batch_op.alter_column('template_id',
                              existing_type=sa.Integer(),
                              type_=sa.String(length=64),
                              existing_nullable=True)
        batch_op.drop_column('data_connection_id')
        batch_op.drop_column('document_id')

    # financial_reports
    with op.batch_alter_table('financial_reports', schema=None) as batch_op:
        batch_op.drop_constraint('fk_financial_reports_document_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_financial_reports_tenant_id'))
        batch_op.drop_index('ix_financial_reports_document_id')
        batch_op.drop_column('tenant_id')
        batch_op.drop_column('document_id')

    # api_keys.scopes
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.drop_column('scopes')
