# Hook PreToolUse: bloqueia acesso direto ao arquivo .env (regra 17 do CLAUDE.md).
# Libera .env.example. Nao afeta pytest, alembic nem scripts.definir_senhas, que
# leem o .env pelo app/config.py em tempo de execucao e nao citam o arquivo na linha
# de comando. Entrada: JSON do Claude Code na stdin. Saida 2 bloqueia a ferramenta.
import json
import re
import sys

# Casa ".env" que nao seja ".env.example" e nao seja prefixo de outra palavra
# (".environment", ".env_local"). Assim ".env", "./.env" e "...\.env" bloqueiam,
# e ".env.example" passa.
PADRAO_ENV = re.compile(r"\.env(?!\.example)(?![\w.])")

# Ferramenta -> campo do tool_input onde um caminho ou comando pode citar o .env.
CAMPO_POR_FERRAMENTA = {
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
    "Bash": "command",
}


def main() -> int:
    try:
        dados = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Sem entrada valida nao ha o que bloquear.
        return 0

    ferramenta = dados.get("tool_name", "")
    campo = CAMPO_POR_FERRAMENTA.get(ferramenta)
    if campo is None:
        return 0

    alvo = dados.get("tool_input", {}).get(campo, "") or ""
    if PADRAO_ENV.search(alvo):
        print(
            "Bloqueado pelo hook block_env: acesso direto ao arquivo .env nao e "
            "permitido (regra 17 do CLAUDE.md). Use .env.example. A aplicacao le o "
            ".env pelo app/config.py em tempo de execucao.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
