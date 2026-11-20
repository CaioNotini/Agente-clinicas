```
Papel: Índice de entrada único da documentação e registro do estado verificado mais recente.
Entrada: docs/status.md
Relaciona-se com: etapas.md, estudo.md, arquitetura.md, principios.md, decisions/README.md, diagnosticos/2026-11-18-plano-rodada3.md
```

# Status do projeto

Estado verificado em 2026-11-18. O histórico detalhado de cada mudança fica no git log e nos [ADRs](./decisions/README.md).

## Onde estamos

**Etapa ativa: 5, agendamento e handoff determinísticos.** Critérios de pronto em [`etapas.md`](./etapas.md).

- Feitas: 5.5 (tabela `agendamentos`, conflito pelo [ADR 0004](./decisions/0004-conflito-de-horario.md)) e 5.1 (`AgendaProvider` e `AgendaPropria`).
- Faltam: 5.2 (regras), 5.3 (criar, remarcar e cancelar) e 5.4 (handoff).
- O pré-requisito da 5.3, a conclusão atômica do job, está pronto ([ADR 0008](./decisions/0008-conclusao-atomica-do-job.md)).
- A 5.5 e a 5.1 foram feitas antes de a etapa 4 fechar, contra a regra de dependência de [`etapas.md`](./etapas.md). O desvio foi aceito pelo desenvolvedor.

| Etapa  | Estado                                            |
| ------ | ------------------------------------------------- |
| 0      | aberta, falta o conteúdo de `pergs_bloqueadas.md` |
| 1 a 4  | concluídas                                        |
| 5      | ativa                                             |
| 6 a 21 | não iniciadas                                     |

## O que está verificado

Última verificação em 2026-11-18, no banco do Docker local:

- `pytest tests/ -v`: `206 passed`.
- Ciclo de migrations (`upgrade head`, `downgrade base`, `upgrade head`), `alembic check` e [`scripts/verificar_pks.sql`](../scripts/verificar_pks.sql) passaram. Head: `b5e8d3f0a7c4`.
- Setup do zero só pelo [`README.md`](../README.md), num clone limpo, passou.
- pylint, black e isort passam e reprovam a CI quando falham.

O que o código garante hoje, com a decisão de cada ponto:

- Isolamento entre clínicas por RLS, FORCE e policy `isolamento_tenant`, com cobertura conferida pelo catálogo ([ADR 0002](./decisions/0002-contas-de-banco.md)).
- FKs entre tabelas de clínica incluem `tenant_id` ([ADR 0007](./decisions/0007-fks-compostas-por-tenant.md)).
- Mensagens da mesma conversa processadas na ordem de chegada ([ADR 0005](./decisions/0005-ordem-por-conversa.md)) e sem processamento simultâneo (lock por conversa).
- Efeitos de um job confirmados uma vez só, junto com a conclusão do job ([ADR 0008](./decisions/0008-conclusao-atomica-do-job.md)).
- Transições de estado pelo grafo do [ADR 0003](./decisions/0003-grafo-de-transicoes.md).
- Senhas das roles aplicadas por script, sem passo manual ([ADR 0006](./decisions/0006-provisionamento-de-roles.md)).

## Pendências

**Ação do desenvolvedor**

- Trocar a senha local de `worker_jobs` e rodar `python -m scripts.definir_senhas`. Ela apareceu na saída de um teste que falhou em 2026-11-18. O teste foi removido, e o `connect_timeout` do worker ficou sem teste automático.

**Decisões abertas**

- Disponibilidade no `AgendaProvider`: a [arquitetura](./arquitetura.md) prevê, e [`etapas.md`](./etapas.md) não tem tarefa. Entra na 5.2 ou na 5.3?

**Decisões recentes**

- Q-21 a Q-24 da seção 13 da [arquitetura](./arquitetura.md) resolvidas pelo [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md): duração por profissional, fuso por clínica, política de cancelamento fora da janela e registro de quem foi notificado no handoff. Consultórios de um profissional só passam a ser previstos, sem presumir recepção.

**Previstas para etapas futuras**

- 5.3: traduzir `23P01` e `40P01` em erro de domínio, com SAVEPOINT ([ADR 0004](./decisions/0004-conflito-de-horario.md)).
- 7: reduzir os grants de `app_clinicas`, só com pedido explícito e ADR (item A4 do [plano](./diagnosticos/2026-11-18-plano-rodada3.md)). O UPDATE em `jobs` precisa continuar, pelo ADR 0008. Os grants de `worker_jobs` também são mais amplos que o uso, como registra o ADR 0002.
- 7: usar `validar_transicao` em toda escrita de estado (C4).
- 9: decidir a conduta para a conversa depois de uma mensagem morta. Risco aceito até lá ([ADR 0005](./decisions/0005-ordem-por-conversa.md)).
- 12: índices das colunas filhas das FKs, índice parcial da fila e retenção de jobs (C1 e C5).
- 6: destino de `conversas.historico` (C6).
- 17: derivar o `tenant_id` do número de destino no webhook (A7), e envio de WhatsApp como job novo, com idempotência no provedor (ADR 0008).

**Ambiguidades de documentação**

- [`FAQ.md`](./fake_clinic/FAQ.md) cita [`pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md) como fonte de duas perguntas administrativas, e esse arquivo só tem perguntas clínicas e de urgência.
- [`principios.md`](./principios.md) cita "D10" no princípio 6, e não existe decisão com esse identificador.
- [`estudo.md`](./estudo.md), seção 4, cita um "endpoint de chat de teste" que nenhuma etapa prevê.
- A seção 7 da [arquitetura](./arquitetura.md) diz que `log_auditoria` guarda categoria e texto original, e a tabela tem `acao`, `descricao` e `dados`.

## Links

- [`etapas.md`](./etapas.md): plano de construção, etapas 0 a 21
- [`estudo.md`](./estudo.md): escopo, premissas e orçamento do estudo
- [`arquitetura.md`](./arquitetura.md): decisões técnicas, modelo de dados e questões em aberto
- [`principios.md`](./principios.md): princípios e como são verificados
- [`decisions/README.md`](./decisions/README.md): ADRs 0001 a 0008
- [`fake_clinic/clinica.md`](./fake_clinic/clinica.md), [`fake_clinic/FAQ.md`](./fake_clinic/FAQ.md) e [`fake_clinic/pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md): base fictícia (clínica com equipe e recepção)
- [`fake_clinic/consultorio_solo.md`](./fake_clinic/consultorio_solo.md): segundo tenant fictício, consultório de um profissional só, sem recepção, para testar as regras da etapa 5 nos dois cenários
- [`diagnosticos/2026-11-18-plano-rodada3.md`](./diagnosticos/2026-11-18-plano-rodada3.md): plano de trabalho da rodada 3, com os itens ainda abertos
- [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md) e [`diagnosticos/2026-10-27-rodada2.md`](./diagnosticos/2026-10-27-rodada2.md): diagnósticos históricos
