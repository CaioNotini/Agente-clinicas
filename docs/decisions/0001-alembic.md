```
Papel: Decisão sobre o local do Alembic (migrations) no repositório.
Entrada: docs/status.md
Relaciona-se com: ../estudo.md, ../arquitetura.md, README.md
```

# 0001: Alembic permanece na raiz do repositório

## Contexto
[`arquitetura.md`, seção 6](../arquitetura.md#6-estrutura-do-código) e [`estudo.md`, seção 4](../estudo.md#4-stack-e-arquitetura) descreviam `db/` (dentro de `app/`) como o lugar de "modelos e migrations (Alembic)". Na implementação real, o Alembic usa a convenção padrão da própria ferramenta: `migrations/` e `alembic.ini` na raiz do repositório, fora de `app/`. `app/db/` contém só os modelos SQLAlchemy (`base.py`, `database.py`, `models.py`).

## Alternativas consideradas
- Mover `migrations/` e `alembic.ini` para dentro de `app/db/`, para bater com o texto dos documentos. Descartada: moveria um Alembic já configurado (caminhos relativos em `alembic.ini` e `migrations/env.py`) sem necessidade funcional, só para igualar a documentação ao código.

## Decisão
O Alembic (`migrations/`, `alembic.ini`) permanece na raiz do repositório. Os documentos canônicos foram corrigidos para refletir isso. Nenhum arquivo de código foi movido.

## Justificativa
É a convenção padrão do Alembic, reduz fricção para quem já conhece a ferramenta, e mover uma configuração funcional é uma mudança de infraestrutura sem ganho real. A documentação devia descrever o código, não o contrário.

## Consequências
`app/db/` continua descrito como "modelos" apenas. Qualquer nova menção à estrutura do repositório nos documentos canônicos deve manter essa distinção (modelos em `app/db/`, migrations na raiz).

## Status
Aceita
