# Status do projeto

Índice de entrada único da documentação. Último diagnóstico: 2026-10-13 — [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md).

## Etapa ativa

**Etapa 2 — parcial.** Falta, conforme D6:

- RLS (Row Level Security) ativo
- Role de worker com BYPASSRLS
- Tabelas `handoffs`, `consents`, `privacy_requests`
- pgvector no `docker-compose.yml`
- Teste de isolamento entre clínicas

Nada dessa lista foi implementado nesta rodada (rodada documental). A implementação é tarefa separada, com especificação e plano aprovados antes de qualquer alteração.

## Estado das etapas (0 a 21)

Critérios de pronto de cada etapa ficam em [`estudo.md`](./estudo.md#6-plano-de-construção-etapas-0-a-21) — esta tabela só registra o que foi verificado.

| Etapa | Estado | Evidência |
|---|---|---|
| 0 | aberta, conteúdo pendente do Caio | Sem FAQ nem base fictícia no repositório (conforme D5) |
| 1 | concluída | Repositório, Docker Compose, `/health`, pytest (3 testes passando), CI configurados |
| 2 | parcial | Migration inicial com 8 tabelas e `tenant_id`; falta a lista acima |
| 3 | não iniciada | `app/channels/` e `app/jobs/` vazios |
| 4 | não iniciada | `app/core/` vazio |
| 5 | não iniciada | — |
| 6 | não iniciada | `app/llm/` vazio |
| 7 | não iniciada | — |
| 8 | não iniciada | — |
| 9 | não iniciada | — |
| 10 | não iniciada | — |
| 11 | não iniciada | — |
| 12 | não iniciada | — |
| 13 | não iniciada | — |
| 14 | não iniciada | — |
| 15 | não iniciada | — |
| 16 | não iniciada | — |
| 17 | não iniciada | — |
| 18 | não iniciada | — |
| 19 | não iniciada | — |
| 20 | não iniciada | — |
| 21 | não iniciada | — |

## Bloqueios e pendências

- **D5** — conteúdo clínico da etapa 0 (FAQ, lista de perguntas proibidas): pendente, a cargo do Caio.
- **Q-17** — tecnologia e autenticação do painel: em aberto, necessária antes da etapa 13.
- **Q-18** — conversa no WhatsApp pessoal vs. painel: em aberto, necessária antes da etapa 13.

## Links

- [`estudo.md`](./estudo.md) — escopo e etapas 0 a 21
- [`arquitetura.md`](./arquitetura.md) — decisões técnicas, modelo de dados, questões em aberto
- [`principios.md`](./principios.md) — princípios e verificação
- [`decisions/README.md`](./decisions/README.md) — registros de decisão (ADRs)
- [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md) — diagnósticos históricos
