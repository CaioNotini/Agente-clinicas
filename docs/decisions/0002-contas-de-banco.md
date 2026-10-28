```
Papel: registra a separação de contas de banco por papel (aplicação, migrations e worker).
Entrada: docs/status.md
Relaciona-se com: ../arquitetura.md (seção 5, quem usa qual credencial), ../estudo.md (etapa 2), ../../app/config.py, ../../tests/isolation/
```

# 0002 — Contas de banco

## Revisão

2026-10-28. A role de fundo `scheduler_service` foi substituída pela `worker_jobs`. Motivo da troca: o projeto passa a ter um único worker de jobs com conta de login própria, em vez de uma role `NOLOGIN` assumida por `SET ROLE`. A `worker_jobs` tem `LOGIN` e `BYPASSRLS`, recebe grants mínimos na migration `c77398abee4a` e tem a senha definida pelo CI a partir de secret. A decisão original e as alternativas descartadas continuam registradas abaixo, com a tabela de contas e as consequências já atualizadas para a nova role.

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
- A senha de `worker_jobs` é definida pelo CI a partir de secret, como a de `app_clinicas`, e nunca entra em migration.
- O worker usa `worker_jobs` somente para a fila (tabela `jobs`). Qualquer escrita específica de clínica passa por sessão `app_clinicas` com RLS, mantendo o filtro explícito de `tenant_id` como segunda barreira.
