```
Papel: registra a separação de contas de banco por papel (aplicação, migrations e worker).
Entrada: docs/status.md
Relaciona-se com: ../arquitetura.md (seção 5, quem usa qual credencial), ../estudo.md (etapa 2), ../../app/config.py, ../../tests/isolation/
```

# 0002 — Contas de banco

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

| Conta               | Papel                      | Superusuário | BYPASSRLS | Usada por                            |
| ------------------- | -------------------------- | ------------ | --------- | ------------------------------------ |
| `app_clinicas`      | aplicação (API e painel)   | não          | não       | `DATABASE_URL` em `app/config.py`    |
| `cnotini`           | migrations e administração | sim          | sim       | `MIGRATION_DATABASE_URL`, só Alembic |
| `scheduler_service` | worker de jobs e lembretes | não          | sim       | assumida com `SET ROLE` pelo worker  |

## Justificativa

Separar por papel mantém o RLS válido para a aplicação, e limita o acesso amplo ao worker e à administração. Se a credencial da aplicação vazar, ela não lê outras clínicas.

## Consequências

- A aplicação nunca pode usar `cnotini` nem `scheduler_service`. Isso precisa ser verificado em revisão de código.
- Testes de isolamento precisam usar `app_clinicas`. Usar `cnotini` dá resultado falso.
- Novas tabelas com `tenant_id` precisam entrar na lista `TABELAS_TENANT` dos testes e receber a policy.
- A role `scheduler_service` não deve ser assumida fora do worker.
