"""garante pk em mensagens.id

Revision ID: 7e9ab495716d
Revises: 9d01c00e9d65
Create Date: 2026-11-16 17:12:32.956497

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e9ab495716d'
down_revision: Union[str, Sequence[str], None] = '9d01c00e9d65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'mensagens'::regclass AND contype = 'p'
            ) THEN
                ALTER TABLE mensagens ADD CONSTRAINT mensagens_pkey PRIMARY KEY (id);
            END IF;
        END $$;
    """)



def downgrade() -> None:
    """Downgrade schema."""
    pass
