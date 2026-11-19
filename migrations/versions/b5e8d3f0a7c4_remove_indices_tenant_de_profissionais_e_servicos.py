"""remove indices de tenant_id de profissionais e servicos

Revision ID: b5e8d3f0a7c4
Revises: 4d7a9c2e1b56
Create Date: 2026-11-18 22:00:00.000000

Desde a 8b3e1f6a2c90 (ADR 0007), profissionais e servicos tem UNIQUE
(tenant_id, id), que comeca por tenant_id e atende as mesmas buscas destes
indices. Decisao do desenvolvedor de 2026-11-18.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b5e8d3f0a7c4'
down_revision: Union[str, Sequence[str], None] = '4d7a9c2e1b56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (indice, tabela) removidos
INDICES = (
    ("idx_profissionais_tenant", "profissionais"),
    ("idx_servicos_tenant", "servicos"),
)


def upgrade() -> None:
    for indice, tabela in INDICES:
        op.drop_index(indice, table_name=tabela)


def downgrade() -> None:
    for indice, tabela in reversed(INDICES):
        op.create_index(indice, tabela, ["tenant_id"], unique=False)
