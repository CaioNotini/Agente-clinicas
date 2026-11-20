"""etapa 5: fuso, duracao override, politica cancelamento, cancelado_fora_da_janela, handoff notificado

Colunas novas das decisoes da etapa 5 (ADR 0009):
- clinicas.fuso (IANA, default America/Sao_Paulo), handoff_prazo_resposta_minutos,
  handoff_texto_paciente.
- profissional_servicos.duracao_minutos: override opcional da duracao (Q-21).
- regras_agendamento.politica_cancelamento_fora_janela (Q-22), com CHECK.
- agendamentos.cancelado_fora_da_janela: marca de cancelamento tardio (Q-22).
- handoffs.notificado_para e notificado_canal (Q-24), com CHECK de canal.

Revision ID: 45ba5d9bc62d
Revises: b5e8d3f0a7c4
Create Date: 2026-11-20 20:48:39.323676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45ba5d9bc62d'
down_revision: Union[str, Sequence[str], None] = 'b5e8d3f0a7c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Colunas novas. Os NOT NULL tem server_default, entao as linhas existentes
    # recebem o valor padrao sem passo manual.
    op.add_column('agendamentos', sa.Column('cancelado_fora_da_janela', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('clinicas', sa.Column('fuso', sa.String(length=40), server_default=sa.text("'America/Sao_Paulo'"), nullable=False))
    op.add_column('clinicas', sa.Column('handoff_prazo_resposta_minutos', sa.Integer(), nullable=True))
    op.add_column('clinicas', sa.Column('handoff_texto_paciente', sa.String(length=500), nullable=True))
    op.add_column('handoffs', sa.Column('notificado_para', sa.String(length=100), nullable=True))
    op.add_column('handoffs', sa.Column('notificado_canal', sa.String(length=20), nullable=True))
    op.add_column('profissional_servicos', sa.Column('duracao_minutos', sa.Integer(), nullable=True))
    op.add_column('regras_agendamento', sa.Column('politica_cancelamento_fora_janela', sa.String(length=20), server_default=sa.text("'handoff'"), nullable=False))

    # CHECK dos dominios novos, no banco, para valerem em qualquer caminho de escrita.
    op.create_check_constraint(
        'ck_regras_politica_cancelamento',
        'regras_agendamento',
        "politica_cancelamento_fora_janela IN ('handoff', 'aceitar_e_marcar')",
    )
    op.create_check_constraint(
        'ck_handoffs_notificado_canal',
        'handoffs',
        "notificado_canal IN ('cli', 'whatsapp')",
    )


def downgrade() -> None:
    # Remove os CHECK antes das colunas que eles restringem.
    op.drop_constraint('ck_handoffs_notificado_canal', 'handoffs', type_='check')
    op.drop_constraint('ck_regras_politica_cancelamento', 'regras_agendamento', type_='check')

    op.drop_column('regras_agendamento', 'politica_cancelamento_fora_janela')
    op.drop_column('profissional_servicos', 'duracao_minutos')
    op.drop_column('handoffs', 'notificado_canal')
    op.drop_column('handoffs', 'notificado_para')
    op.drop_column('clinicas', 'handoff_texto_paciente')
    op.drop_column('clinicas', 'handoff_prazo_resposta_minutos')
    op.drop_column('clinicas', 'fuso')
    op.drop_column('agendamentos', 'cancelado_fora_da_janela')
