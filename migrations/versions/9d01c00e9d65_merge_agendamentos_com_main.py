"""merge agendamentos com main

Revision ID: 9d01c00e9d65
Revises: 1bc74598f301, b131d6ee6471
Create Date: 2026-11-16 17:10:43.349214

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d01c00e9d65'
down_revision: Union[str, Sequence[str], None] = ('1bc74598f301', 'b131d6ee6471')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
