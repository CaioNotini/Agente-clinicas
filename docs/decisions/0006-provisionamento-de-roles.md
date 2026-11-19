```
Papel: registra como as roles automatizadas são criadas pelas migrations e como recebem a senha.
Entrada: docs/status.md
Relaciona-se com: 0002-contas-de-banco.md, ../../scripts/definir_senhas.py, ../../.github/workflows/ci.yml, ../../tests/integration/test_senhas_roles.py
```

# 0006: Provisionamento das roles automatizadas

## Contexto

As migrations criam `app_clinicas` e `worker_jobs` sem senha, conforme o [ADR 0002](./0002-contas-de-banco.md). Até 2026-11-18 a senha era aplicada só pela CI, com dois passos `psql` em [`ci.yml`](../../.github/workflows/ci.yml). Num banco local novo era preciso rodar `ALTER ROLE ... PASSWORD` à mão, sem instrução no README. O item 1 do bloco 1 do [plano de 2026-11-18](../diagnosticos/2026-11-18-plano-rodada3.md) pede que um banco novo fique utilizável sem esse passo manual.

## Alternativas consideradas

- **Migration que lê a senha do ambiente.** Descartada por quatro motivos:
  - `alembic upgrade --sql` imprimiria a senha no SQL gerado.
  - A migration roda uma vez por banco, então trocar a senha exigiria uma migration nova.
  - O downgrade da `c77398abee4a` apaga e recria `worker_jobs`, e a senha se perderia no ciclo de sobe e desce.
  - Credencial é configuração do ambiente, não schema.
- **Manter os passos `psql` da CI e documentar o `ALTER ROLE` no README.** Descartada: a lógica ficaria duplicada entre a CI e o README, e o passo manual continuaria existindo.
- **Script único chamado pela CI e pelo README.** Escolhida.

## Decisão

As senhas de `app_clinicas` e `worker_jobs` são aplicadas por [`scripts/definir_senhas.py`](../../scripts/definir_senhas.py), executado com `python -m scripts.definir_senhas` depois de `alembic upgrade head`, tanto na CI quanto no setup local.

## Justificativa

O script lê as variáveis pelo mesmo `app/config.py` da aplicação, então a CI e o ambiente local usam o mesmo caminho. Ele pode rodar de novo a qualquer momento, inclusive depois de um downgrade. A senha nunca entra em migration nem em arquivo versionado.

## Consequências

- O script conecta com a conta de migrations e roda `ALTER ROLE` com o nome da role como identificador e a senha como literal escapado.
- Os nomes das roles são fixos. Se `APP_DB_USER` não for `app_clinicas` ou `WORKER_DB_USER` não for `worker_jobs`, o script para antes de conectar. Um `.env` errado não troca a senha de outra role, como a do superusuário.
- Se a role não existir, o script para e pede `alembic upgrade head`.
- Nenhuma senha é impressa. Erros de banco mostram só o tipo do erro.
- Os testes estão em [`test_senhas_roles.py`](../../tests/integration/test_senhas_roles.py). Eles cobrem uma role sem senha que volta a logar depois do script e um nome de role inesperado que é recusado sem alterar nada.
- Nenhum atributo, grant ou policy muda. Só a forma de aplicar a senha.

## Status

Aceita em 2026-11-18.
