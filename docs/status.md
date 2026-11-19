```
Papel: Índice de entrada único da documentação e registro do estado verificado mais recente.
Entrada: docs/status.md
Relaciona-se com: etapas.md, estudo.md, arquitetura.md, principios.md, decisions/README.md, diagnosticos/2026-10-13-rodada1.md, diagnosticos/2026-10-27-rodada2.md, diagnosticos/2026-11-18-plano-rodada3.md
```

# Status do projeto

Índice de entrada único da documentação. Último diagnóstico: 2026-11-18, em [`diagnosticos/2026-11-18-plano-rodada3.md`](./diagnosticos/2026-11-18-plano-rodada3.md). Este arquivo registra o estado verificado mais recente.

## Etapa ativa

**Etapa 4, concluída em 2026-11-18.** Reaberta em 2026-11-15 e fechada por decisão do desenvolvedor em 2026-11-18, depois da garantia de ordem. Tarefas 4.1 (máquina de estados e transições determinísticas), 4.2 (lock por conversa com `SELECT ... FOR UPDATE` e `lock_timeout`), 4.3 (teste de mensagens seguidas da mesma conversa) e 4.4 (escrita de clínica por sessão `app_clinicas` com RLS, ligada ao worker pelo ponto de injeção `processamento=`) implementadas em 2026-10-29, com testes passando. Evidência na seção "Evidências verificadas na etapa 4".

A etapa foi reaberta porque o critério de pronto em [`etapas.md`](./etapas.md) exige que mensagens seguidas não gerem processamento fora de ordem. O lock por conversa não garante a ordem de chegada entre workers. A decisão de 2026-11-15 foi manter o critério. A garantia de ordem é a tarefa em aberto.

A abordagem da garantia de ordem está no [ADR 0005](./decisions/0005-ordem-por-conversa.md), aceito em 2026-11-18. Ela foi implementada em 2026-11-18 com testes passando (seção "Verificado em 2026-11-18"). Para a conversa depois de uma mensagem morta, o desenvolvedor escolheu aceitar o risco até a etapa 9 (ver "Bloqueios e pendências").

**Etapa 5** (agendamento e handoff determinísticos), parada. As tarefas 5.5 (tabela `agendamentos`) e 5.1 (`AgendaProvider` e `AgendaPropria`) foram feitas na branch `wip/agendamentos` antes de a etapa 4 fechar, contra a regra de dependência de [`etapas.md`](./etapas.md). A evidência de testes dessas tarefas não está registrada aqui. Decisão de 2026-11-18: a etapa 5 fica parada até a etapa 4 cumprir o critério de pronto. A etapa 4 fechou em 2026-11-18. A retomada da etapa 5 aguarda decisão do desenvolvedor. Critérios de pronto em [`etapas.md`](./etapas.md).

## Estado das etapas (0 a 21)

Critérios de pronto de cada etapa ficam em [`etapas.md`](./etapas.md). Esta tabela registra só o que foi verificado.

| Etapa | Estado                                           | Evidência                                                                          |
| ----- | ------------------------------------------------ | ---------------------------------------------------------------------------------- |
| 0     | aberta, conteúdo pendente do Caio                | FAQ e base fictícia criados em [fake_clinic/](./fake_clinic/)                      |
| 1     | concluída                                        | Repositório, Docker Compose, `/health`, pytest e CI                                |
| 2     | concluída                                        | Schema multi-tenant, RLS, FORCE e policy de isolamento, testado com `app_clinicas` |
| 3     | concluída                                        | Canal CLI, fila de jobs e worker com `SKIP LOCKED`, exercitado ao vivo             |
| 4     | concluída                                        | Ver seção "Evidências verificadas na etapa 4"                                      |
| 5     | parada, 5.5 e 5.1 feitas antes da etapa 4 fechar | branch `wip/agendamentos`, sem evidência de testes registrada                      |
| 6     | não iniciada                                     | —                                                                                  |
| 7     | não iniciada                                     | —                                                                                  |
| 8     | não iniciada                                     | —                                                                                  |
| 9     | não iniciada                                     | —                                                                                  |
| 10    | não iniciada                                     | —                                                                                  |
| 11    | não iniciada                                     | —                                                                                  |
| 12    | não iniciada                                     | —                                                                                  |
| 13    | não iniciada                                     | —                                                                                  |
| 14    | não iniciada                                     | —                                                                                  |
| 15    | não iniciada                                     | —                                                                                  |
| 16    | não iniciada                                     | —                                                                                  |
| 17    | não iniciada                                     | —                                                                                  |
| 18    | não iniciada                                     | —                                                                                  |
| 19    | não iniciada                                     | —                                                                                  |
| 20    | não iniciada                                     | —                                                                                  |
| 21    | não iniciada                                     | —                                                                                  |

## Evidências verificadas na etapa 4

**Verificado em 2026-10-29.** `pytest tests/ -v`: `113 passed`. Arquivos da etapa (`test_estados.py`, `test_lock_conversa.py`, `test_mensagens_seguidas.py`): 42 testes passando.

- **4.1 máquina de estados.** `app/core/estados.py`, grafo em [`decisions/0003-grafo-de-transicoes.md`](./decisions/0003-grafo-de-transicoes.md). Transições inválidas rejeitadas, incluindo laço no mesmo estado e estado desconhecido (`test_estados.py`, 30 testes). A aresta `idle -> encerrada` está fora do grafo, coerente com o ADR 0003.
- **4.2 lock por conversa.** `app/core/conversas.py` (`conversa_travada`, `SELECT ... FOR UPDATE` que bloqueia, `lock_timeout` abaixo do limite de órfão do worker). Controles registrados: sem `FOR UPDATE`, sem `ON CONFLICT` e sem `lock_timeout` os testes correspondentes falham. Corrida de criação resulta em uma linha só.
- **4.3 mensagens seguidas.** `test_mensagens_seguidas_serializam_sem_duplicar`: vários jobs da mesma conversa, vários workers, processamentos sem sobreposição e cada job uma vez só. Estável em 20 de 20 execuções. Controle: sem o lock da conversa os processamentos se sobrepõem. A ordem de chegada entre workers não é garantida pelo lock.
- **4.4 escrita de clínica via `app_clinicas`.** `app/core/processamento.py` (`processar_mensagem`), por sessão `app_clinicas` com RLS e `app.tenant_id` do próprio job, ligada ao worker pelo ponto de injeção `processamento=`. Em 2026-10-29 isso foi feito sem alterar `app/jobs/worker.py`. Casos cobertos com controle: tenant vem da coluna do job (payload ignorado), reprocessamento do mesmo job não duplica a conversa, e o mesmo contato em duas clínicas gera duas conversas separadas.

**Verificado em 2026-11-18.** Garantia de ordem do [ADR 0005](./decisions/0005-ordem-por-conversa.md), restrições do schema e laço do worker resiliente. `pytest tests/ -v`: `144 passed` (eram 120 antes desta mudança).

- **Migration `5f2c8a1d9e47`.** Adiciona `jobs.contato_telefone`, o índice parcial da conversa, NOT NULL e `server_default` em `jobs` e `conversas`, e os CHECKs de status, estado, direção e conversa do job de mensagem. Verificações feitas:
  - O ciclo de sobe, desce e sobe passou, com o schema conferido no catálogo em cada ponto.
  - `alembic check` não detectou diferença entre os models e o schema.
  - Dados no formato antigo foram convertidos: `in` virou `entrada`, `out` virou `saida` e os nulos ganharam os defaults.
  - Um job de mensagem sem conversa fez a migration parar com erro, e o banco continuou na versão anterior.
- **Ordem por conversa.** `tests/concurrency/test_ordem_conversa.py`, 6 testes:
  - um job seguinte não é capturado enquanto o anterior processa,
  - dois workers com processamento lento seguem a ordem,
  - uma falha da mensagem 1 não deixa a 2 e a 3 passarem,
  - uma mensagem que esgota as tentativas vai para `dead` e libera as seguintes,
  - outras conversas e outras clínicas não são bloqueadas,
  - jobs sem conversa não bloqueiam nem são bloqueados.

  Antes da implementação, os 6 falhavam. Estáveis em 20 de 20 execuções. Controle: sem a cláusula `NOT EXISTS` da captura, com o schema novo, os 6 falham.

- **Restrições do schema.** `tests/integration/test_restricoes_schema.py`, 17 testes. Antes da implementação falhavam 15. Os 2 que passavam são os controles positivos de `entrada` e `saida`.
- **Laço do worker.** `test_rodar_sobrevive_a_erro_de_banco`: um erro de banco no laço não encerra o worker. Falhava antes da implementação.
- **Testes existentes ajustados ao schema novo, sem mudar asserções.** Os seeds de `test_worker.py` e `test_mensagens_seguidas.py` passam a gravar `contato_telefone` nos jobs de mensagem. O seed de `test_isolation_rls.py` usa `entrada` no lugar de `in`.

## Bloco 1 da rodada 3

Itens do [plano de 2026-11-18](./diagnosticos/2026-11-18-plano-rodada3.md), feitos na `main`, um commit por item.

- **Senhas das roles automatizadas, verificado em 2026-11-18.** [`scripts/definir_senhas.py`](../scripts/definir_senhas.py) aplica as senhas de `app_clinicas` e `worker_jobs`, chamado pela CI e pelo setup local. Decisão no [ADR 0006](./decisions/0006-provisionamento-de-roles.md). `tests/integration/test_senhas_roles.py`, 4 testes, falhavam antes do script. `pytest tests/ -v`: `148 passed`. A CI no GitHub ainda não rodou com o passo novo.
- **B3, `CREATE ROLE` idempotente, verificado em 2026-11-18.** As migrations `e4ffcb741dc3` e `c77398abee4a` só criam a role se ela não existir ([ADR 0006](./decisions/0006-provisionamento-de-roles.md)). `test_upgrade_head_num_segundo_banco_do_mesmo_cluster` falhava antes com `role "worker_jobs" already exists`. `pytest tests/ -v`: `149 passed`.
- **A6, downgrades de `mensagens`, verificado em 2026-11-18.** A cadeia foi mantida. A docstring da `1bc74598f301` foi corrigida. O downgrade dela recria a PK `pk_mensagens`, que era o estado original, e o da `7e9ab495716d` remove a `mensagens_pkey`. `test_downgrade_de_mensagens_volta_ao_estado_original` sobe até o head, desce até a `9d01c00e9d65` (sem PK), desce até a `c77398abee4a` (só `pk_mensagens`) e sobe de novo. Antes falhava, com a `mensagens_pkey` restando no primeiro downgrade. `pytest tests/ -v`: `150 passed`.
- **B1, CI com ciclo de migrations, verificado localmente em 2026-11-18.** O [`ci.yml`](../.github/workflows/ci.yml) roda `upgrade head`, `downgrade base`, `upgrade head`, `alembic check` e [`scripts/verificar_pks.sql`](../scripts/verificar_pks.sql), antes do script de senhas e do pytest. O pylint com `E` e `F` passa a reprovar a CI. Verificações feitas no banco local:
  - o ciclo passou e o `alembic check` não detectou diferença.
  - a consulta de PK passou no head e falhou em dois controles: uma tabela criada sem PK e o estado da `9d01c00e9d65`, sem PK em `mensagens`, que é o erro da seção 0 do plano.
  - o pylint passou e falhou num controle com variável indefinida. Os 18 `E1102` de `func.now()` são um falso positivo e foram desligados só em `app/db/models.py`.
  - depois do ciclo e do script de senhas, `pytest tests/ -v`: `150 passed`.
  
  A pipeline no GitHub ainda não rodou com essas mudanças.

## Bloqueios e pendências

- **Pendência da etapa 9: conversa depois de uma mensagem morta.** Risco aceito em 2026-11-18 no [ADR 0005](./decisions/0005-ordem-por-conversa.md). Quando um job de mensagem vai para `dead`, as mensagens seguintes da conversa são processadas sem ela, e nada muda na conversa. A etapa 9 é a primeira em que o processamento altera o estado da conversa (tarefa 9.2). A conduta precisa estar decidida e implementada antes de a etapa 9 fechar.
- **Desvio na ordem das etapas 4 e 5.** As tarefas 5.5 e 5.1 foram feitas na branch `wip/agendamentos` com a etapa 4 ainda parcial. Decisão de 2026-11-18: a etapa 5 fica parada até a etapa 4 fechar. A etapa 4 fechou em 2026-11-18, e a retomada da etapa 5 aguarda decisão do desenvolvedor.
- **Alterações de 2026-11-15 sem validação contra o banco.** Foram quatro alterações:
  - o laço `rodar()` de `app/jobs/worker.py` passou a usar `processar_mensagem` como processamento padrão.
  - a migration `1bc74598f301` remove a constraint `pk_mensagens` de `mensagens`, tratando-a como UNIQUE redundante. Correção de 2026-11-18: `pk_mensagens` era a única chave primária, e a migration a remove. A chave volta com a `7e9ab495716d`. Causa na seção 0 de [`diagnosticos/2026-11-18-plano-rodada3.md`](./diagnosticos/2026-11-18-plano-rodada3.md).
  - a rota `/health` de `app/main.py` passou a consultar o banco, com 200 quando ele responde e 503 quando não responde. `tests/test_health.py` foi reescrito.
  - o passo de senha de `worker_jobs` em `.github/workflows/ci.yml` ganhou `ON_ERROR_STOP=1`. Em 2026-11-18 esse passo foi substituído pelo script do [ADR 0006](./decisions/0006-provisionamento-de-roles.md).
- **O que foi verificado em 2026-11-15, sem banco.** A máquina usada não tinha Docker nem banco no ar. Com variáveis fictícias: os módulos importam sem ciclo, o padrão de `rodar()` é `processar_mensagem`, `alembic heads` mostra `1bc74598f301` como head único, `test_estados.py` passa (30 testes) e o teste de `/health` com banco fora passa (503). Os dois testes de `/health` com banco no ar falharam por falta de banco, como esperado.
- **O que falta validar.** Em 2026-11-18, com o banco do Docker ligado, `alembic upgrade head` e `pytest tests/ -v` completo passaram (144 testes). O ciclo de sobe, desce e sobe da migration `1bc74598f301` foi verificado em 2026-11-18 (item A6 do bloco 1). Ainda falta a pipeline do CI no GitHub.
- Os grants de `worker_jobs` no banco são mais amplos que o uso feito pelo código. A decisão de 2026-11-15 foi documentar os grants reais no [ADR 0002](./decisions/0002-contas-de-banco.md), sem alterar o banco.
- Os testes de `tests/concurrency/test_estados.py` são unitários e não tocam no banco. Ficaram em `tests/concurrency/` porque a etapa 4 só lista esse diretório em [`etapas.md`](./etapas.md). A decisão de movê-los para `tests/unit/` está pendente.
- **Desvio conhecido na ordem das etapas.** As etapas 1 a 4 avançaram com a etapa 0 ainda aberta, contra a regra de dependência de [`etapas.md`](./etapas.md). A etapa 0 segue pendente do conteúdo de [`pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md).
- **Critérios de pronto aprovados.** Em 2026-11-15 foram aprovados os critérios de pronto de [`etapas.md`](./etapas.md) como estão, e o aviso de rascunho foi removido.
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
- [`diagnosticos/2026-11-18-plano-rodada3.md`](./diagnosticos/2026-11-18-plano-rodada3.md): plano de trabalho da rodada 3
