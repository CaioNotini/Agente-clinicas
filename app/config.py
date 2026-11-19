# Ponto único de configuração: carrega o .env e monta as duas URLs do banco
import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

raiz_projeto = Path(__file__).resolve().parent.parent
load_dotenv(raiz_projeto / ".env")

variaveis_obrigatorias = [
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "APP_DB_USER",
    "APP_DB_PASSWORD",
    "WORKER_DB_USER",
    "WORKER_DB_PASSWORD",
]
faltando = [nome for nome in variaveis_obrigatorias if not os.getenv(nome)]
if faltando:
    raise RuntimeError(f"Variáveis ausentes no .env: {', '.join(faltando)}")

_servidor_e_banco = (
    f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)


def _monta_url(usuario: str, senha: str) -> str:
    # quote com safe="" codifica todo caractere especial, inclusive o espaco como %20.
    # quote_plus trocava o espaco por +, que o SQLAlchemy nao desfaz na leitura.
    return f"postgresql://{usuario}:{quote(senha, safe='')}@{_servidor_e_banco}"


# Conta da aplicação: sem superusuário, sujeita ao RLS
DATABASE_URL = _monta_url(os.getenv("APP_DB_USER"), os.getenv("APP_DB_PASSWORD"))

# Conta de migrations: dona das tabelas, usada só pelo Alembic
MIGRATION_DATABASE_URL = _monta_url(os.getenv("DB_USER"), os.getenv("DB_PASSWORD"))

# Conta do worker de jobs: leitura da fila de todas as clínicas (BYPASSRLS)
WORKER_DATABASE_URL = _monta_url(
    os.getenv("WORKER_DB_USER"), os.getenv("WORKER_DB_PASSWORD")
)
