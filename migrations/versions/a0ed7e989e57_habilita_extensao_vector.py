"""habilita extensao vector

Revision ID: a0ed7e989e57
Revises: 63eccb28bdf3
Create Date: 2026-10-15 16:58:46.004331

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0ed7e989e57'
down_revision: Union[str, Sequence[str], None] = '63eccb28bdf3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Habilita a extensão de vetores, usada pelo RAG na etapa 8
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Remove a extensão; seguro enquanto nenhuma tabela usa o tipo vector
    op.execute("DROP EXTENSION IF EXISTS vector")
