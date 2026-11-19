```
Papel: registra a separação de contas de banco por papel (aplicação, migrations e worker).
Entrada: docs/status.md
Relaciona-se com: ../arquitetura.md (seção 5, quem usa qual credencial), ../etapas.md (etapa 2), ../../app/config.py, ../../tests/isolation/
```

# 0002: Contas de banco

## Revisão

2026-10-28. A role de fundo `scheduler_service` foi substituída pela `worker_jobs`. Motivo da troca: o projeto passa a ter um único worker de jobs com conta de login própria, em vez de uma role `NOLOGIN` assumida por `SET ROLE`. A `worker_jobs` tem `LOGIN` e `BYPASSRLS`, recebe os grants da migration `c77398abee4a` e tem a senha definida pelo CI a partir de secret. A decisão original e as alternativas descartadas continuam registradas abaixo, com a tabela de contas e as consequências já atualizadas para a nova role.

2026-11-15. As consequências passam a listar os grants reais de `worker_jobs`, que são mais amplos que o uso feito pelo código. Nenhum grant foi alterado no banco.

2026-11-18. As senhas de `app_clinicas` e `worker_jobs` passam a ser aplicadas por um script único, chamado pela CI e pelo setup local, conforme o [ADR 0006](./0006-provisionamento-de-roles.md).

2026-11-18. A conclusão bem-sucedida de um job passa a ser feita pela sessão `app_clinicas` do processamento, na mesma transação dos efeitos, conforme o [ADR 0008](./0008-conclusao-atomica-do-job.md). A captura e o caminho de falha continuam com `worker_jobs`.

## Status

Aceita.

## Contexto

O RLS isola as clínicas, mas não vale para superusuário nem para role com BYPASSRLS. A conta de migrations (`cnotini`) é superusuário. Se a aplicação usasse essa conta, o isolamento não existiria. O worker precisa ler todas as clínicas, por isso tem BYPASSRLS.

## Alternativas consideradas

- **Uma conta única para tudo.** Descartada: superusuário ignora o RLS, então a aplicação ficaria sem isolamento.
- **Role por clínica.** Descartada: não escala, e contraria a decisão D-03 de banco único com `tenant_id`.
- **Três contas com papéis distintos.** Escolhida.

## Decisão

Três contas, cada uma com um papel:

| Conta          | Papel                      | Login | Superusuário | BYPASSRLS | Usada por                               |
| -------------- | -------------------------- | ----- | ------------ | --------- | --------------------------------------- |
| `app_clinicas` | aplicação (API e painel)   | sim   | não          | não       | `DATABASE_URL` em `app/config.py`       |
| `cnotini`      | migrations e administração | sim   | sim          | sim       | `MIGRATION_DATABASE_URL`, só Alembic    |
| `worker_jobs`  | worker de jobs             | sim   | não          | sim       | conexão própria do único worker de jobs |

## Justificativa

Separar por papel mantém o RLS válido para a aplicação, e limita o acesso amplo ao worker e à administração. Se a credencial da aplicação vazar, ela não lê outras clínicas.

## Consequências

- A aplicação nunca pode usar `cnotini` nem `worker_jobs`. Isso precisa ser verificado em revisão de código.
- Testes de isolamento precisam usar `app_clinicas`. Usar `cnotini` dá resultado falso.
- Novas tabelas com `tenant_id` precisam entrar na lista `TABELAS_TENANT` dos testes e receber a policy.
- A role `worker_jobs` é usada só pelo processo do worker de jobs. A aplicação que atende requisições nunca se conecta com ela.
- A senha de `worker_jobs`, como a de `app_clinicas`, nunca entra em migration. Ela é aplicada pelo script do [ADR 0006](./0006-provisionamento-de-roles.md), com o valor do secret na CI e do `.env` no ambiente local.
- O código do worker usa `worker_jobs` somente para a fila (tabela `jobs`). Qualquer escrita específica de clínica passa por sessão `app_clinicas` com RLS, mantendo o filtro explícito de `tenant_id` como segunda barreira.
- Os grants de `worker_jobs` no banco são mais amplos que esse uso. A migration `c77398abee4a` concede `SELECT` e `UPDATE` em `jobs`, `SELECT` em `mensagens`, `conversas` e `clinicas`, `INSERT` em `mensagens` e `log_auditoria`, e `USAGE` e `SELECT` na sequência `log_auditoria_id_seq`. Hoje o código só usa os grants de `jobs`. Os demais existem no banco e não são usados.
