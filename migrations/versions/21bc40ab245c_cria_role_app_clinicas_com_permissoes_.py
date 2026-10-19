"""cria role app_clinicas com permissoes da aplicacao

Revision ID: 21bc40ab245c
Revises: e69c546938b3
Create Date: 2026-10-19 16:00:18.196766

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21bc40ab245c'
down_revision: Union[str, Sequence[str], None] = 'e69c546938b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Cria a role da aplicação só se ela não existir (idempotente, para o ambiente local e o CI)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_clinicas') THEN
                CREATE ROLE app_clinicas LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$
    """)
    # Sem senha aqui: a senha é definida pelo CI a partir do secret
    op.execute("GRANT USAGE ON SCHEMA public TO app_clinicas")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_clinicas")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_clinicas")
    # Tabelas criadas em migrations futuras recebem as mesmas permissões automaticamente
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_clinicas")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_clinicas")
    # A aplicação não deve ler a tabela de controle do Alembic
    op.execute("REVOKE ALL ON alembic_version FROM app_clinicas")


def downgrade() -> None:
    # Remove só as permissões. A role não é apagada aqui, porque apagá-la invalidaria a senha do ambiente local
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM app_clinicas")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM app_clinicas")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_clinicas")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM app_clinicas")
    op.execute("REVOKE USAGE ON SCHEMA public FROM app_clinicas")
