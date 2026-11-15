```
Papel: Índice de entrada único da documentação e registro do estado verificado mais recente.
Entrada: docs/status.md
Relaciona-se com: etapas.md, estudo.md, arquitetura.md, principios.md, decisions/README.md, diagnosticos/2026-10-13-rodada1.md, diagnosticos/2026-10-27-rodada2.md
```

# Status do projeto

Índice de entrada único da documentação. Último diagnóstico: 2026-10-27, em [`diagnosticos/2026-10-27-rodada2.md`](./diagnosticos/2026-10-27-rodada2.md). Este arquivo registra o estado verificado mais recente.

## Etapa ativa

**Etapa 4, parcial. Reaberta em 2026-11-15.** Tarefas 4.1 (máquina de estados e transições determinísticas), 4.2 (lock por conversa com `SELECT ... FOR UPDATE` e `lock_timeout`), 4.3 (teste de mensagens seguidas da mesma conversa) e 4.4 (escrita de clínica por sessão `app_clinicas` com RLS, ligada ao worker pelo ponto de injeção `processamento=`) implementadas em 2026-10-29, com testes passando. Evidência na seção "Evidências verificadas na etapa 4".

A etapa foi reaberta porque o critério de pronto em [`etapas.md`](./etapas.md) exige que mensagens seguidas não gerem processamento fora de ordem. O lock por conversa não garante a ordem de chegada entre workers. A decisão de 2026-11-15 foi manter o critério. A garantia de ordem é a tarefa em aberto.

**Próxima etapa 5** (agendamento e handoff determinísticos), não iniciada. Depende da conclusão da etapa 4. Critérios de pronto em [`etapas.md`](./etapas.md).

## Estado das etapas (0 a 21)

Critérios de pronto de cada etapa ficam em [`etapas.md`](./etapas.md). Esta tabela registra só o que foi verificado.

| Etapa | Estado                            | Evidência                                                                 |
| ----- | --------------------------------- | ------------------------------------------------------------------------- |
| 0     | aberta, conteúdo pendente do Caio | FAQ e base fictícia criados em [fake_clinic/](./fake_clinic/)             |
| 1     | concluída                         | Repositório, Docker Compose, `/health`, pytest e CI                       |
| 2     | concluída                         | Schema multi-tenant, RLS, FORCE e policy de isolamento, testado com `app_clinicas` |
| 3     | concluída                         | Canal CLI, fila de jobs e worker com `SKIP LOCKED`, exercitado ao vivo    |
| 4     | parcial, falta a garantia de ordem | Ver seção "Evidências verificadas na etapa 4"                            |
| 5     | não iniciada                      | próxima etapa, depende da etapa 4                                         |
| 6     | não iniciada                      | —                                                                         |
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
- **4.4 escrita de clínica via `app_clinicas`.** `app/core/processamento.py` (`processar_mensagem`), por sessão `app_clinicas` com RLS e `app.tenant_id` do próprio job, ligada ao worker pelo ponto de injeção `processamento=`. Em 2026-10-29 isso foi feito sem alterar `app/jobs/worker.py`. Casos cobertos com controle: tenant vem da coluna do job (payload ignorado), reprocessamento do mesmo job não duplica a conversa, e o mesmo contato em duas clínicas gera duas conversas separadas.

## Bloqueios e pendências

- **Garantia de ordem na etapa 4.** O critério de mensagens seguidas em [`etapas.md`](./etapas.md) foi mantido em 2026-11-15. Falta implementar e testar que mensagens seguidas da mesma conversa são processadas na ordem de chegada. A abordagem não está definida.
- **Alterações de 2026-11-15 sem validação contra o banco.** Foram quatro alterações:
  - o laço `rodar()` de `app/jobs/worker.py` passou a usar `processar_mensagem` como processamento padrão.
  - a migration `1bc74598f301` remove a constraint UNIQUE redundante `pk_mensagens` de `mensagens`, e a chave primária real continua valendo.
  - a rota `/health` de `app/main.py` passou a consultar o banco, com 200 quando ele responde e 503 quando não responde. `tests/test_health.py` foi reescrito.
  - o passo de senha de `worker_jobs` em `.github/workflows/ci.yml` ganhou `ON_ERROR_STOP=1`.
- **O que foi verificado em 2026-11-15, sem banco.** A máquina usada não tinha Docker nem banco no ar. Com variáveis fictícias: os módulos importam sem ciclo, o padrão de `rodar()` é `processar_mensagem`, `alembic heads` mostra `1bc74598f301` como head único, `test_estados.py` passa (30 testes) e o teste de `/health` com banco fora passa (503). Os dois testes de `/health` com banco no ar falharam por falta de banco, como esperado.
- **O que falta validar.** Com o banco do Docker ligado: `alembic upgrade head`, o ciclo de sobe, desce e sobe da migration `1bc74598f301`, e `pytest tests/ -v` completo, com 113 testes esperados. A alteração do CI só é validada quando a pipeline rodar no GitHub.
- Os grants de `worker_jobs` no banco são mais amplos que o uso feito pelo código. A decisão de 2026-11-15 foi documentar os grants reais no [ADR 0002](./decisions/0002-contas-de-banco.md), sem alterar o banco.
- Os testes de `tests/concurrency/test_estados.py` são unitários e não tocam no banco. Ficaram em `tests/concurrency/` porque a etapa 4 só lista esse diretório em [`etapas.md`](./etapas.md). A decisão de movê-los para `tests/unit/` está pendente.
- **Desvio conhecido na ordem das etapas.** As etapas 1 a 4 avançaram com a etapa 0 ainda aberta, contra a regra de dependência de [`etapas.md`](./etapas.md). A etapa 0 segue pendente do conteúdo de [`pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md), a cargo do Caio.
- **Critérios de pronto aprovados.** Em 2026-11-15 o Caio aprovou os critérios de pronto de [`etapas.md`](./etapas.md) como estão, e o aviso de rascunho foi removido.
- **Questões que bloqueiam a especificação da etapa 5.** Q-20 a Q-24, na seção 13 de [`arquitetura.md`](./arquitetura.md).
- **Ambiguidades de documentação ainda sem decisão.**
  - Q-03 pede resposta na etapa 4 e na etapa 15, mas o ambiente local não tem pooler, então a parte da etapa 4 não tem como ser respondida.
  - [`FAQ.md`](./fake_clinic/FAQ.md) cita [`pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md) como fonte de duas perguntas administrativas marcadas como bloqueado, e esse arquivo só tem perguntas clínicas e de urgência.
  - [`principios.md`](./principios.md) cita "D10" na verificação do princípio 6, e não existe decisão com esse identificador ligada ao tema.
  - [`estudo.md`](./estudo.md), seção 4, cita um "endpoint de chat de teste" que nenhuma etapa de [`etapas.md`](./etapas.md) prevê.
  - A seção 7 de [`arquitetura.md`](./arquitetura.md) diz que `log_auditoria` guarda categoria e texto original, e a tabela tem as colunas `acao`, `descricao` e `dados`.

## Links

- [`etapas.md`](./etapas.md): plano de construção, etapas 0 a 21
- [`estudo.md`](./estudo.md): escopo, premissas e orçamento do estudo
- [`arquitetura.md`](./arquitetura.md): decisões técnicas, modelo de dados e questões em aberto
- [`principios.md`](./principios.md): princípios e como são verificados
- [`decisions/README.md`](./decisions/README.md): registros de decisão (ADRs)
- [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md): diagnóstico histórico da rodada 1
- [`diagnosticos/2026-10-27-rodada2.md`](./diagnosticos/2026-10-27-rodada2.md): diagnóstico histórico da rodada 2
