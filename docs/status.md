# Status do projeto

Índice de entrada único da documentação. Último diagnóstico: 2026-10-13, em [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md). Este arquivo registra o estado verificado mais recente.

## Etapa ativa

**Etapa 4, concluída em 2026-10-29.** Tarefas 4.1 (máquina de estados e transições determinísticas), 4.2 (lock por conversa com `SELECT ... FOR UPDATE` e `lock_timeout`), 4.3 (teste de mensagens seguidas da mesma conversa) e 4.4 (escrita de clínica por sessão `app_clinicas` com RLS, ligada ao worker pelo ponto de injeção `processamento=`) implementadas, com testes passando. Evidência na seção "Evidências verificadas na etapa 4".

**Próxima etapa 5** (agendamento e handoff determinísticos), não iniciada. Critérios de pronto em [`etapas.md`](./etapas.md).

## Estado das etapas (0 a 21)

Critérios de pronto de cada etapa ficam em [`etapas.md`](./etapas.md). Esta tabela registra só o que foi verificado.

| Etapa | Estado                            | Evidência                                                                 |
| ----- | --------------------------------- | ------------------------------------------------------------------------- |
| 0     | aberta, conteúdo pendente do Caio | FAQ e base fictícia criados em [fake_clinic/](./fake_clinic/)             |
| 1     | concluída                         | Repositório, Docker Compose, `/health`, pytest e CI                       |
| 2     | concluída                         | Schema multi-tenant, RLS, FORCE e policy de isolamento, testado com `app_clinicas` |
| 3     | concluída                         | Canal CLI, fila de jobs e worker com `SKIP LOCKED`, exercitado ao vivo    |
| 4     | concluída                         | Ver seção "Evidências verificadas na etapa 4"                             |
| 5     | não iniciada                      | próxima etapa                                                             |
| 6     | não iniciada                      | `app/llm/` vazio                                                          |
| 7     | não iniciada                      | —                                                                         |
| 8     | não iniciada                      | —                                                                         |
| 9     | não iniciada                      | —                                                                         |
| 10    | não iniciada                      | —                                                                         |
| 11    | não iniciada                      | —                                                                         |
| 12    | não iniciada                      | —                                                                         |
| 13    | não iniciada                      | —                                                                         |
| 14    | não iniciada                      | —                                                                         |
| 15    | não iniciada                      | —                                                                         |
| 16    | não iniciada                      | —                                                                         |
| 17    | não iniciada                      | —                                                                         |
| 18    | não iniciada                      | —                                                                         |
| 19    | não iniciada                      | —                                                                         |
| 20    | não iniciada                      | —                                                                         |
| 21    | não iniciada                      | —                                                                         |

## Evidências verificadas na etapa 4

**Verificado em 2026-10-29.** `pytest tests/ -v`: `113 passed`. Arquivos da etapa (`test_estados.py`, `test_lock_conversa.py`, `test_mensagens_seguidas.py`): 42 testes passando.

- **4.1 máquina de estados.** `app/core/estados.py`, grafo em [`decisions/0003-grafo-de-transicoes.md`](./decisions/0003-grafo-de-transicoes.md). Transições inválidas rejeitadas, incluindo laço no mesmo estado e estado desconhecido (`test_estados.py`, 30 testes). A aresta `idle -> encerrada` está fora do grafo, coerente com o ADR 0003.
- **4.2 lock por conversa.** `app/core/conversas.py` (`conversa_travada`, `SELECT ... FOR UPDATE` que bloqueia, `lock_timeout` abaixo do limite de órfão do worker). Controles registrados: sem `FOR UPDATE`, sem `ON CONFLICT` e sem `lock_timeout` os testes correspondentes falham. Corrida de criação resulta em uma linha só.
- **4.3 mensagens seguidas.** `test_mensagens_seguidas_serializam_sem_duplicar`: vários jobs da mesma conversa, vários workers, processamentos sem sobreposição e cada job uma vez só. Estável em 20 de 20 execuções. Controle: sem o lock da conversa os processamentos se sobrepõem. A ordem de chegada entre workers não é garantida pelo lock.
- **4.4 escrita de clínica via `app_clinicas`.** `app/core/processamento.py` (`processar_mensagem`), por sessão `app_clinicas` com RLS e `app.tenant_id` do próprio job, ligada ao worker pelo ponto de injeção `processamento=` sem alterar `app/jobs/worker.py`. Casos cobertos com controle: tenant vem da coluna do job (payload ignorado), reprocessamento do mesmo job não duplica a conversa, e o mesmo contato em duas clínicas gera duas conversas separadas.

## Bloqueios e pendências

- O default de produção do worker segue `processamento_vazio`. Ligar `processar_mensagem` como processamento padrão exige editar `app/jobs/worker.py`, fora do escopo das tarefas da etapa 4. A docstring de `app/jobs/worker.py` tem a nota "a lógica real entra a partir da etapa 4", que ficará desatualizada.
- Proposta de nova redação do critério de mensagens seguidas em [`etapas.md`](./etapas.md), sem processamento simultâneo nem duplicidade e com a ordem de chegada registrada como não garantida, pendente de aprovação antes de aplicar.

## Links

- [`etapas.md`](./etapas.md): plano de construção, etapas 0 a 21
- [`estudo.md`](./estudo.md): escopo, premissas e orçamento do estudo
- [`arquitetura.md`](./arquitetura.md): decisões técnicas, modelo de dados e questões em aberto
- [`principios.md`](./principios.md): princípios e como são verificados
- [`decisions/README.md`](./decisions/README.md): registros de decisão (ADRs)
- [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md): diagnósticos históricos
