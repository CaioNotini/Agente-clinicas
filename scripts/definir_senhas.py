"""Define as senhas das roles automatizadas a partir das variaveis de ambiente.

Uso, na raiz do projeto, depois de `alembic upgrade head`:

    python -m scripts.definir_senhas

As migrations criam app_clinicas e worker_jobs sem senha, porque credencial nao
entra em migration (docs/decisions/0006-provisionamento-de-roles.md). Este
script aplica APP_DB_PASSWORD e WORKER_DB_PASSWORD com a conta de migrations.
Pode ser executado de novo a qualquer momento, por exemplo depois de um
downgrade que recria worker_jobs.

Os nomes das roles sao fixos. Se APP_DB_USER ou WORKER_DB_USER tiverem outro
valor, o script para antes de conectar: um .env errado nao pode trocar a senha
de outra role, como a do superusuario. Nenhuma senha e impressa.
"""
import os
import sys

import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine

from app.config import MIGRATION_DATABASE_URL

# Variavel com o usuario, variavel com a senha e nome da role criada nas migrations
ROLES = (
    ("APP_DB_USER", "APP_DB_PASSWORD", "app_clinicas"),
    ("WORKER_DB_USER", "WORKER_DB_PASSWORD", "worker_jobs"),
)


class ErroConfiguracao(Exception):
    """Configuracao que impede definir as senhas com seguranca."""


def validar_nomes() -> None:
    for var_usuario, _, role in ROLES:
        if os.getenv(var_usuario) != role:
            raise ErroConfiguracao(f"{var_usuario} deve ser {role}")


def definir_senhas(conexao) -> None:
    with conexao.cursor() as cursor:
        for _, var_senha, role in ROLES:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if cursor.fetchone() is None:
                raise ErroConfiguracao(
                    f"a role {role} nao existe: rode alembic upgrade head antes"
                )
            # ALTER ROLE nao aceita parametro: a senha entra como literal escapado
            cursor.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(os.environ[var_senha])
                )
            )


def main() -> int:
    try:
        validar_nomes()
        conexao = create_engine(MIGRATION_DATABASE_URL).raw_connection()
        try:
            definir_senhas(conexao)
            conexao.commit()
        finally:
            conexao.close()
    except ErroConfiguracao as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    except psycopg2.Error as erro:
        # So o tipo: a mensagem do driver pode repetir trechos do comando
        print(f"erro de banco: {type(erro).__name__}", file=sys.stderr)
        return 1
    print("senhas definidas: " + ", ".join(role for _, _, role in ROLES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
