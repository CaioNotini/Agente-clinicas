"""substitui scheduler_service por worker_jobs

Revision ID: c77398abee4a
Revises: 21bc40ab245c
Create Date: 2026-10-28 14:55:29.820585

Troca a role de fundo do projeto. Sai a scheduler_service (NOLOGIN, BYPASSRLS,
com SELECT/INSERT/UPDATE/DELETE em todas as tabelas) e entra a worker_jobs, a
conta de login do unico worker de jobs, com BYPASSRLS e grants minimos.
A senha de worker_jobs nao e definida aqui: fica a cargo do CI, a partir de
secret, no mesmo modelo de app_clinicas. Ver ADR 0002.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c77398abee4a'
down_revision: Union[str, Sequence[str], None] = '21bc40ab245c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1-2. Remove todos os privilegios de scheduler_service antes de apaga-la
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM scheduler_service")
    op.execute("REVOKE USAGE ON SCHEMA public FROM scheduler_service")

    # 3. Comprova que nao sobrou nenhum privilegio de tabela. Se sobrar, aborta a migration.
    op.execute(
        """
        DO $$
        DECLARE restantes int;
        BEGIN
            SELECT count(*) INTO restantes
            FROM information_schema.role_table_grants
            WHERE grantee = 'scheduler_service';
            IF restantes > 0 THEN
                RAISE EXCEPTION
                    'scheduler_service ainda tem % privilegio(s) de tabela apos o REVOKE; migration abortada',
                    restantes;
            END IF;
        END
        $$
        """
    )

    # 4. Agora sim, remove a role
    op.execute("DROP ROLE scheduler_service")

    # 5. Cria a conta de login do unico worker de jobs, com BYPASSRLS. Roles valem
    # para o cluster inteiro: so cria se outro banco ainda nao criou (ADR 0006)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'worker_jobs') THEN
                CREATE ROLE worker_jobs LOGIN BYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$
        """
    )

    # 6-10. Grants minimos para o worker: ler a fila, travar jobs, e gravar o que precisar
    op.execute("GRANT USAGE ON SCHEMA public TO worker_jobs")
    op.execute("GRANT SELECT, UPDATE ON jobs TO worker_jobs")
    op.execute("GRANT SELECT ON mensagens, conversas, clinicas TO worker_jobs")
    op.execute("GRANT INSERT ON mensagens, log_auditoria TO worker_jobs")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE log_auditoria_id_seq TO worker_jobs")


def downgrade() -> None:
    # Desfaz worker_jobs: remove os grants antes de apagar a role
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM worker_jobs")
    op.execute("REVOKE ALL ON SEQUENCE log_auditoria_id_seq FROM worker_jobs")
    op.execute("REVOKE USAGE ON SCHEMA public FROM worker_jobs")
    op.execute("DROP ROLE worker_jobs")

    # Recria scheduler_service exatamente como a migration 2.3 (e4ffcb741dc3) a deixou
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scheduler_service') THEN
                CREATE ROLE scheduler_service NOLOGIN BYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO scheduler_service"
    )
