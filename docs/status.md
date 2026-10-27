# Status do projeto

Índice de entrada único da documentação. Último diagnóstico: 2026-10-13, em [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md). Este arquivo registra o estado verificado mais recente.

## Etapa ativa

**Etapa 2, concluída.** Critério de pronto de [`etapas.md`](./etapas.md) comprovado nesta verificação: schema multi-tenant, RLS ativo, role de worker, tabelas `handoffs`, `log_auditoria`, `consents` e `privacy_requests` (vazias) e teste de isolamento.

**Próxima etapa: 3**, não iniciada. Depende da etapa 2, concluída. Entrega prevista: canal CLI, fila de jobs, worker.

## Estado das etapas (0 a 21)

Critérios de pronto de cada etapa ficam em [`etapas.md`](./etapas.md). Esta tabela registra só o que foi verificado.

| Etapa | Estado                            | Evidência                                                                            |
| ----- | --------------------------------- | ------------------------------------------------------------------------------------ |
| 0     | aberta, conteúdo pendente do Caio | Sem FAQ nem base fictícia no repositório (conforme D5)                               |
| 1     | concluída                         | Repositório, Docker Compose, `/health`, pytest (3 testes passando) e CI configurados |
| 2     | concluída                         | Ver seção "Evidências verificadas na etapa 2"                                        |
| 3     | não iniciada                      | `app/channels/` e `app/jobs/` vazios                                                 |
| 4     | não iniciada                      | `app/core/` vazio                                                                    |
| 5     | não iniciada                      | —                                                                                    |
| 6     | não iniciada                      | `app/llm/` vazio                                                                     |
| 7     | não iniciada                      | —                                                                                    |
| 8     | não iniciada                      | —                                                                                    |
| 9     | não iniciada                      | —                                                                                    |
| 10    | não iniciada                      | —                                                                                    |
| 11    | não iniciada                      | —                                                                                    |
| 12    | não iniciada                      | —                                                                                    |
| 13    | não iniciada                      | —                                                                                    |
| 14    | não iniciada                      | —                                                                                    |
| 15    | não iniciada                      | —                                                                                    |
| 16    | não iniciada                      | —                                                                                    |
| 17    | não iniciada                      | —                                                                                    |
| 18    | não iniciada                      | —                                                                                    |
| 19    | não iniciada                      | —                                                                                    |
| 20    | não iniciada                      | —                                                                                    |
| 21    | não iniciada                      | —                                                                                    |

## Evidências verificadas na etapa 2

- **Revalidação em 2026-10-22 (somente leitura):** `alembic heads` e `alembic current` mostram cabeça única `21bc40ab245c`, sem migrations pendentes. Roles confirmadas com os mesmos atributos do ADR 0002. RLS e FORCE RLS ativos (`true`/`true`) nas 14 tabelas de `TABELAS_TENANT`, todas com a policy `isolamento_tenant` (`cmd = ALL`, mesma condição em `USING` e `WITH CHECK`), e nenhuma tabela com `tenant_id` ficou sem essa policy. `consents` e `privacy_requests` com 0 linhas. `pytest tests/isolation -v`, com `engine_app` em todas as asserções, `56 passed`. Nenhum arquivo de código, teste, migration, configuração, role ou policy foi alterado nesta verificação.

## Bloqueios e pendências

- **Q-17:** tecnologia e autenticação do painel. Em aberto, necessária antes da etapa 13.
- **Q-18:** conversa no WhatsApp pessoal versus painel. Em aberto, necessária antes da etapa 13.

## Links

- [`etapas.md`](./etapas.md): plano de construção, etapas 0 a 21
- [`estudo.md`](./estudo.md): escopo, premissas e orçamento do estudo
- [`arquitetura.md`](./arquitetura.md): decisões técnicas, modelo de dados e questões em aberto
- [`principios.md`](./principios.md): princípios e como são verificados
- [`decisions/README.md`](./decisions/README.md): registros de decisão (ADRs)
- [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md): diagnósticos históricos
