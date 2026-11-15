"""remove unique redundante de mensagens

Revision ID: 1bc74598f301
Revises: c77398abee4a
Create Date: 2026-11-15 18:00:00.000000

A migration inicial criou em mensagens.id a chave primaria (mensagens_pkey) e
tambem uma constraint UNIQUE sobre a mesma coluna. A d109eb356688 renomeou essa
UNIQUE para pk_mensagens, mas ela nunca foi a chave primaria. A unicidade e a
deduplicacao (ON CONFLICT (id)) ja sao garantidas pela chave primaria real, e
app/db/models.py nao declara a UNIQUE. Esta migration remove a redundancia.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '1bc74598f301'
down_revision: Union[str, Sequence[str], None] = 'c77398abee4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove a UNIQUE redundante; a chave primaria mensagens_pkey continua valendo
    op.drop_constraint('pk_mensagens', 'mensagens', type_='unique')


def downgrade() -> None:
    # Recria a UNIQUE com o nome que a d109eb356688 deixou
    op.create_unique_constraint('pk_mensagens', 'mensagens', ['id'])
