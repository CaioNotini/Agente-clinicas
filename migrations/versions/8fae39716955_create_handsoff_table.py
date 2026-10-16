"""create handsoff table

Revision ID: 8fae39716955
Revises: 98141a9414dc
Create Date: 2026-10-16 10:36:57.719797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8fae39716955'
down_revision: Union[str, Sequence[str], None] = '98141a9414dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Número de plantão da recepção, usado para avisar sobre handoffs (D-29)
    op.add_column('clinicas', sa.Column('telefone_plantao', sa.String(length=20), nullable=True))

    # Registro de cada handoff: quem foi avisado, quem assumiu e quando voltou ao bot
    op.create_table('handoffs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('conversa_id', sa.Integer(), nullable=False),
    sa.Column('motivo', sa.String(length=50), nullable=False),
    sa.Column('notificado_em', sa.DateTime(), nullable=True),
    sa.Column('assumido_por', sa.String(length=100), nullable=True),
    sa.Column('assumido_em', sa.DateTime(), nullable=True),
    sa.Column('devolvido_em', sa.DateTime(), nullable=True),
    sa.Column('criada_em', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['tenant_id'], ['clinicas.tenant_id'], ),
    sa.ForeignKeyConstraint(['conversa_id'], ['conversas.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_handoffs_tenant', 'handoffs', ['tenant_id'], unique=False)
    op.create_index('idx_handoffs_conversa', 'handoffs', ['conversa_id'], unique=False)

    # Histórico de consentimentos: uma linha por aceite, sem sobrescrever o anterior
    op.create_table('consents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('contato_telefone', sa.String(length=20), nullable=False),
    sa.Column('tipo', sa.String(length=50), nullable=False),
    sa.Column('versao_texto', sa.String(length=20), nullable=False),
    sa.Column('canal', sa.String(length=30), nullable=True),
    sa.Column('concedido_em', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['tenant_id'], ['clinicas.tenant_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_consents_tenant_contato', 'consents', ['tenant_id', 'contato_telefone'], unique=False)

    # Pedidos de privacidade do titular (acesso, correção, exclusão, portabilidade)
    op.create_table('privacy_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('contato_telefone', sa.String(length=20), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('criada_em', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('concluida_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['tenant_id'], ['clinicas.tenant_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_privacy_requests_tenant', 'privacy_requests', ['tenant_id'], unique=False)


def downgrade() -> None:
    # Remove na ordem inversa: índices, tabelas e depois a coluna
    op.drop_index('idx_privacy_requests_tenant', table_name='privacy_requests')
    op.drop_table('privacy_requests')
    op.drop_index('idx_consents_tenant_contato', table_name='consents')
    op.drop_table('consents')
    op.drop_index('idx_handoffs_conversa', table_name='handoffs')
    op.drop_index('idx_handoffs_tenant', table_name='handoffs')
    op.drop_table('handoffs')
    op.drop_column('clinicas', 'telefone_plantao')