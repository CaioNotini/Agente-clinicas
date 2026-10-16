# Status do projeto

Índice de entrada único da documentação. Último diagnóstico: 2026-10-13, em [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md). Este arquivo registra o estado verificado mais recente.

## Etapa ativa

**Etapa 2, parcial.** Subtarefas, conforme a especificação em [`estudo.md`](./estudo.md#6-plano-de-construção-etapas-0-a-21):

- 2.1 Extensão pgvector: concluída (migration `a0ed7e989e57`). Imagem `pgvector/pgvector:pg15`, extensão `vector` habilitada e testada com upgrade e downgrade.
- 2.2 Tabelas faltantes: concluída, em duas migrations. Migration A `98141a9414dc` (`profissional_servicos`, `regras_agendamento`, `pacientes_contatos`) e migration B `8fae39716955` (`handoffs`, `consents`, `privacy_requests`, coluna `clinicas.telefone_plantao`). Ambas testadas com upgrade, downgrade e upgrade.
- 2.3 Role `scheduler_service` com BYPASSRLS: concluida.
- 2.4 RLS nas tabelas com `tenant_id`: concluída (migration `e69c546938b3`). RLS e FORCE ativos nas 14 tabelas, policy `isolamento_tenant`. Aplicação conecta com `app_clinicas`, sem superusuário. Leitura verificada: sem tenant a consulta falha, com tenant A só a clínica A aparece. Escrita, atualização e exclusão cruzadas ficam para a 2.5.
- 2.5 Teste de isolamento entre clínicas: pendente.

Cada subtarefa é implementada separadamente, com especificação e plano aprovados antes de qualquer alteração.

## Estado das etapas (0 a 21)

Critérios de pronto de cada etapa ficam em [`estudo.md`](./estudo.md#6-plano-de-construção-etapas-0-a-21). Esta tabela registra só o que foi verificado.

| Etapa | Estado                            | Evidência                                                                            |
| ----- | --------------------------------- | ------------------------------------------------------------------------------------ |
| 0     | aberta, conteúdo pendente do Caio | Sem FAQ nem base fictícia no repositório (conforme D5)                               |
| 1     | concluída                         | Repositório, Docker Compose, `/health`, pytest (3 testes passando) e CI configurados |
| 2     | parcial                           | Ver seção "Evidências verificadas na etapa 2"                                        |
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

- **Conexão:** `select 1` retorna `1` com a URL montada a partir do `.env`.
- **Migrations:** `alembic current` e `alembic heads` mostram a revisão de partida da 2.2, `a0ed7e989e57 (head)`, após a 2.1.
- **Migration inicial:** `63eccb28bdf3`, aplicada e intacta.
- **Migration de extensão (2.1):** `a0ed7e989e57`, com `CREATE EXTENSION IF NOT EXISTS vector` no upgrade e `DROP EXTENSION IF EXISTS vector` no downgrade. Testada com upgrade, downgrade e upgrade. O downgrade só é seguro enquanto nenhuma tabela usar o tipo `vector`.
- **Renome da constraint de `mensagens` (migration `d109eb356688`):** `uq_mensagens_message_id` renomeada para `pk_mensagens`, para refletir que é chave primária. Testada com upgrade, downgrade e upgrade.
- **Imagem do banco:** `pgvector/pgvector:pg15`, em execução. O volume `postgres_data` é o mesmo de antes.
- **Tabelas existentes:** `clinicas`, `conversas`, `jobs`, `log_auditoria`, `mensagens`, `profissionais`, `servicos`, `horarios_trabalho`, `profissional_servicos`, `regras_agendamento`, `pacientes_contatos`, `handoffs`, `consents`, `privacy_requests`, além de `alembic_version`. A coluna `clinicas.telefone_plantao` também existe.
- **Identificador de mensagem:** a coluna real é `mensagens.id`, chave primária, com o identificador da Meta. A arquitetura ainda cita `message_id`.

## Bloqueios e pendências

- **Q-17:** tecnologia e autenticação do painel. Em aberto, necessária antes da etapa 13.
- **Q-18:** conversa no WhatsApp pessoal versus painel. Em aberto, necessária antes da etapa 13.
- **Centralização da configuração:** criar `app/config.py` para eliminar a montagem duplicada da URL em `env.py` e `database.py`.

## Links

- [`estudo.md`](./estudo.md): escopo e etapas 0 a 21
- [`arquitetura.md`](./arquitetura.md): decisões técnicas, modelo de dados e questões em aberto
- [`principios.md`](./principios.md): princípios e como são verificados
- [`decisions/README.md`](./decisions/README.md): registros de decisão (ADRs)
- [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md): diagnósticos históricos
