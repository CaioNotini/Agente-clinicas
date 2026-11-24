"""handoff: texto ao paciente, prazo e referencias ao agendamento e a mensagem

Tarefa 5.4, revisao do ADR 0009 de 2026-11-24:
- handoffs.texto_paciente: copia do texto que o bot informou ao paciente na abertura.
  Nunca o conteudo da mensagem do paciente.
- handoffs.responder_ate (timestamptz): instante limite, calculado na abertura a
  partir do prazo da clinica. Nulo quando a clinica nao informa prazo.
- handoffs.agendamento_id: FK composta para agendamentos (ADR 0007), NO ACTION.
- handoffs.mensagem_id: so a referencia da mensagem de origem. FK composta para
  mensagens com ON DELETE SET NULL (mensagem_id): o pedido de exclusao do titular
  (LGPD) apaga a mensagem e o handoff fica, sem a referencia. A lista de colunas do
  SET NULL (Postgres 15) zera so mensagem_id. Sem ela, o SET NULL zeraria tambem
  tenant_id, que e NOT NULL.
- UNIQUE (tenant_id, id) em agendamentos e mensagens, alvo das FKs compostas.

As colunas novas sao nullable, entao as linhas existentes nao precisam de
preenchimento. Nenhuma policy, role ou grant muda: handoffs ja tem a policy
isolamento_tenant e esta em TABELAS_TENANT.

Revision ID: c3d8e5a1f297
Revises: 45ba5d9bc62d
Create Date: 2026-11-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3d8e5a1f297'
down_revision: Union[str, Sequence[str], None] = '45ba5d9bc62d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('handoffs', sa.Column('texto_paciente', sa.String(length=600), nullable=True))
    op.add_column(
        'handoffs',
        sa.Column('responder_ate', postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column('handoffs', sa.Column('agendamento_id', sa.Integer(), nullable=True))
    op.add_column('handoffs', sa.Column('mensagem_id', sa.String(length=100), nullable=True))

    # Alvo das FKs compostas. O id ja e PK, a UNIQUE existe so para a FK (ADR 0007).
    op.create_unique_constraint('uq_agendamentos_tenant_id_id', 'agendamentos', ['tenant_id', 'id'])
    op.create_unique_constraint('uq_mensagens_tenant_id_id', 'mensagens', ['tenant_id', 'id'])

    op.create_foreign_key(
        'fk_handoffs_agendamento_id_tenant',
        'handoffs',
        'agendamentos',
        ['tenant_id', 'agendamento_id'],
        ['tenant_id', 'id'],
    )
    # SQL direto: o SQLAlchemy nao aceita a lista de colunas no ON DELETE SET NULL
    op.execute(
        "ALTER TABLE handoffs ADD CONSTRAINT fk_handoffs_mensagem_id_tenant "
        "FOREIGN KEY (tenant_id, mensagem_id) REFERENCES mensagens (tenant_id, id) "
        "ON DELETE SET NULL (mensagem_id)"
    )


def downgrade() -> None:
    op.drop_constraint('fk_handoffs_mensagem_id_tenant', 'handoffs', type_='foreignkey')
    op.drop_constraint('fk_handoffs_agendamento_id_tenant', 'handoffs', type_='foreignkey')
    op.drop_constraint('uq_mensagens_tenant_id_id', 'mensagens', type_='unique')
    op.drop_constraint('uq_agendamentos_tenant_id_id', 'agendamentos', type_='unique')
    op.drop_column('handoffs', 'mensagem_id')
    op.drop_column('handoffs', 'agendamento_id')
    op.drop_column('handoffs', 'responder_ate')
    op.drop_column('handoffs', 'texto_paciente')
