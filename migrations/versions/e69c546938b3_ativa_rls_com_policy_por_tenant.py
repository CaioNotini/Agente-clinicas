"""ativa rls com policy por tenant

Revision ID: e69c546938b3
Revises: e4ffcb741dc3
Create Date: 2026-10-16 11:21:14.447320

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e69c546938b3'
down_revision: Union[str, Sequence[str], None] = 'e4ffcb741dc3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabelas com tenant_id, que recebem RLS e a policy de isolamento
TABELAS_TENANT = (
    "clinicas",
    "conversas",
    "jobs",
    "log_auditoria",
    "mensagens",
    "profissionais",
    "servicos",
    "horarios_trabalho",
    "profissional_servicos",
    "regras_agendamento",
    "pacientes_contatos",
    "handoffs",
    "consents",
    "privacy_requests",
)


def upgrade() -> None:
    for tabela in TABELAS_TENANT:
        # Liga o RLS e aplica também ao dono da tabela
        op.execute(f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabela} FORCE ROW LEVEL SECURITY")
        # Permite só linhas do tenant definido na transação, com erro se não houver tenant
        op.execute(
            f"CREATE POLICY isolamento_tenant ON {tabela} "
            "USING (tenant_id = current_setting('app.tenant_id')::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)"
        )


def downgrade() -> None:
    for tabela in TABELAS_TENANT:
        # Remove a policy antes de desligar o RLS
        op.execute(f"DROP POLICY IF EXISTS isolamento_tenant ON {tabela}")
        op.execute(f"ALTER TABLE {tabela} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabela} DISABLE ROW LEVEL SECURITY")

