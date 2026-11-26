# Ponto único de configuração: carrega o .env e monta as duas URLs do banco
import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

from app.llm.base import ConfigLLM

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

# Configuração do cliente LLM (ADR 0010). Lida só quando o cliente é criado, não no
# import: a suíte do banco e a CI não precisam de LLM_MODEL nem ANTHROPIC_API_KEY, por
# isso estas variáveis ficam fora de variaveis_obrigatorias.
variaveis_llm = ["LLM_MODEL", "ANTHROPIC_API_KEY"]

# Padrões do modelo que não vêm do .env. max_tokens limita a resposta do modelo e
# inclui os tokens de raciocínio. ESFORCO_PADRAO = None não desliga o raciocínio: o
# modelo do estudo tem raciocínio adaptativo sempre ligado, com esforço padrão medium.
# None só diz que o cliente não envia effort; enviar ou remover o campo é da etapa 7.
# 4096 (tarefa 7.2): a resposta da classificação é um JSON curto, mas o raciocínio
# conta dentro do limite, e um corte vira saída inválida e cai na regra. O valor
# ainda limita o gasto de saída de cada chamada a 4096 tokens.
MAX_TOKENS_PADRAO = 4096
ESFORCO_PADRAO = None


def ler_config_llm():
    """Lê LLM_MODEL e ANTHROPIC_API_KEY e devolve (ConfigLLM, chave).

    Roda só quando o cliente LLM é criado, por isso a validação fica aqui e não no
    nível do módulo. Levanta RuntimeError listando as variáveis ausentes, no mesmo
    padrão de variaveis_obrigatorias. A chave não entra na ConfigLLM: vai direto ao
    SDK como api_key (ADR 0010).
    """
    faltando = [nome for nome in variaveis_llm if not os.getenv(nome)]
    if faltando:
        raise RuntimeError(f"Variáveis ausentes no .env: {', '.join(faltando)}")
    config = ConfigLLM(
        modelo=os.getenv("LLM_MODEL"),
        max_tokens=MAX_TOKENS_PADRAO,
        esforco=ESFORCO_PADRAO,
    )
    return config, os.getenv("ANTHROPIC_API_KEY")
