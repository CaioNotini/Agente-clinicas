"""renomeia constraint mensagens para pk_mensagens

Revision ID: d109eb356688
Revises: a0ed7e989e57
Create Date: 2026-10-15 17:04:16.096140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd109eb356688'
down_revision: Union[str, Sequence[str], None] = 'a0ed7e989e57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Renomeia a constraint para refletir que é chave primária
    op.execute("ALTER TABLE mensagens RENAME CONSTRAINT uq_mensagens_message_id TO pk_mensagens")


def downgrade() -> None:
    # Desfaz o renome, voltando ao nome original
    op.execute("ALTER TABLE mensagens RENAME CONSTRAINT pk_mensagens TO uq_mensagens_message_id")
