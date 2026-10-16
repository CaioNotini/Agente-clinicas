"""cria tabelas de agenda e contatos

Revision ID: 98141a9414dc
Revises: d109eb356688
Create Date: 2026-10-16 10:19:14.210982

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98141a9414dc'
down_revision: Union[str, Sequence[str], None] = 'd109eb356688'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Regras de agendamento de cada clínica: antecedência e janela de cancelamento
    op.create_table('regras_agendamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('antecedencia_minima_horas', sa.Integer(), nullable=True),
    sa.Column('antecedencia_maxima_dias', sa.Integer(), nullable=True),
    sa.Column('janela_cancelamento_horas', sa.Integer(), nullable=True),
    sa.Column('criada_em', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['tenant_id'], ['clinicas.tenant_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', name='uq_regras_tenant')
    )

    # Relação entre profissionais e os serviços que realizam
    op.create_table('profissional_servicos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('profissional_id', sa.Integer(), nullable=False),
    sa.Column('servico_id', sa.Integer(), nullable=False),
    sa.Column('criada_em', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['profissional_id'], ['profissionais.id'], ),
    sa.ForeignKeyConstraint(['servico_id'], ['servicos.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['clinicas.tenant_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('profissional_id', 'servico_id', name='uq_profissional_servico')
    )
    op.create_index('idx_profissional_servicos_tenant', 'profissional_servicos', ['tenant_id'], unique=False)

    # Contatos de pacientes: dado mínimo, sem prontuário
    op.create_table('pacientes_contatos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=True),
    sa.Column('contato_telefone', sa.String(length=20), nullable=False),
    sa.Column('criada_em', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['tenant_id'], ['clinicas.tenant_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'contato_telefone', name='uq_pacientes_tenant_contato')
    )
    op.create_index('idx_pacientes_contatos_tenant', 'pacientes_contatos', ['tenant_id'], unique=False)


def downgrade() -> None:
    # Remove na ordem inversa da criação, índices antes das tabelas
    op.drop_index('idx_pacientes_contatos_tenant', table_name='pacientes_contatos')
    op.drop_table('pacientes_contatos')
    op.drop_index('idx_profissional_servicos_tenant', table_name='profissional_servicos')
    op.drop_table('profissional_servicos')
    op.drop_table('regras_agendamento')
