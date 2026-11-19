"""remove indices redundantes de tenant_id

Revision ID: 4d7a9c2e1b56
Revises: 8b3e1f6a2c90
Create Date: 2026-11-18 21:00:00.000000

Item B11 do plano de 2026-11-18. Cada indice abaixo so cobre tenant_id, e outro
indice unico da mesma tabela ja comeca por tenant_id e atende as mesmas buscas:
- idx_clinicas_tenant_id: clinicas_tenant_id_key (UNIQUE tenant_id).
- idx_conversas_tenant: uq_conversas_tenant_contato (tenant_id, contato_telefone).
- idx_pacientes_contatos_tenant: uq_pacientes_tenant_contato (tenant_id, contato_telefone).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '4d7a9c2e1b56'
down_revision: Union[str, Sequence[str], None] = '8b3e1f6a2c90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (indice, tabela) removidos
INDICES = (
    ("idx_clinicas_tenant_id", "clinicas"),
    ("idx_conversas_tenant", "conversas"),
    ("idx_pacientes_contatos_tenant", "pacientes_contatos"),
)


def upgrade() -> None:
    for indice, tabela in INDICES:
        op.drop_index(indice, table_name=tabela)


def downgrade() -> None:
    for indice, tabela in reversed(INDICES):
        op.create_index(indice, tabela, ["tenant_id"], unique=False)
