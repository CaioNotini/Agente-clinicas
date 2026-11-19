"""cria role scheduler_service com bypassrls

Revision ID: e4ffcb741dc3
Revises: 8fae39716955
Create Date: 2026-10-16 10:44:28.222387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4ffcb741dc3'
down_revision: Union[str, Sequence[str], None] = '8fae39716955'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Role do worker: ignora RLS para ler jobs e lembretes de todas as clínicas (D-05)
    # Roles valem para o cluster inteiro: so cria se outro banco ainda nao criou (ADR 0006)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scheduler_service') THEN
                CREATE ROLE scheduler_service NOLOGIN BYPASSRLS;
            END IF;
        END
        $$
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO scheduler_service")


def downgrade() -> None:
    # Remove os privilégios antes de apagar a role, senão o DROP falha
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM scheduler_service")
    op.execute("DROP ROLE IF EXISTS scheduler_service")
