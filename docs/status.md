# Status do projeto

Índice de entrada único da documentação. Último diagnóstico: 2026-10-13, em [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md). Este arquivo registra o estado verificado mais recente.

## Etapa ativa

**Etapa 3, concluída em 2026-10-28.** Tarefas 3.1 (canal CLI), 3.2 (gravação em `mensagens` e criação de job com deduplicação) e 3.3 (worker com `SKIP LOCKED`, tentativas e `dead`) implementadas, com testes passando e com a cadeia do CLI ao worker exercitada ao vivo. Os critérios de pronto de [`etapas.md`](./etapas.md) para a etapa 3 não exigem CI no GitHub.

**Próxima etapa 4** (motor de estados e lock por conversa), não iniciada. Critérios de pronto em [`etapas.md`](./etapas.md).

## Estado das etapas (0 a 21)

Critérios de pronto de cada etapa ficam em [`etapas.md`](./etapas.md). Esta tabela registra só o que foi verificado.

| Etapa | Estado                            | Evidência                                                                            |
| ----- | --------------------------------- | ------------------------------------------------------------------------------------ |
| 0     | aberta, conteúdo pendente do Caio | FAQ e base fictícia criados em [fake_clinic/](./fake_clinic/)                        |
| 1     | concluída                         | Repositório, Docker Compose, `/health`, pytest (3 testes passando) e CI configurados |
| 2     | concluída                         | Ver seção "Evidências verificadas na etapa 2"                                        |
| 3     | concluída                         | Ver seção "Evidências verificadas na etapa 3"                                        |
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

## Evidências verificadas na etapa 3

**Verificado em 2026-10-28:**

- Cabeça do Alembic é `c77398abee4a`, a migration que substitui a role de fundo `scheduler_service` pela `worker_jobs` (login com BYPASSRLS).
- [`decisions/0002-contas-de-banco.md`](./decisions/0002-contas-de-banco.md) atualizado pela troca de `scheduler_service` para `worker_jobs`.
- `ColisaoIdEntreTenants` em `app/jobs/queue.py`: id de mensagem que já existe em outro tenant levanta erro explícito, em vez de virar duplicata silenciosa.
- Worker em `app/jobs/worker.py`, conectado como `worker_jobs` por `WORKER_DATABASE_URL`.

Os três testes exigidos pelos critérios de [`etapas.md`](./etapas.md) passam:

- dois workers disputando o mesmo job, só um processa: `tests/concurrency/test_worker.py::test_dois_workers_so_um_processa`.
- mensagem duplicada não gera segundo processamento: `tests/concurrency/test_dedupe_mensagens.py::test_mensagem_duplicada_nao_gera_segundo_job`.
- job que vai para `dead` após as tentativas: `tests/concurrency/test_worker.py::test_falha_volta_a_pending_e_depois_dead`.

Verificações finais da etapa 3, de 2026-10-28:

- **3.1 controle do critério de tenant.** Com a linha `set_config('app.tenant_id', ...)` comentada em `app/jobs/worker.py`, `pytest tests/concurrency/test_worker.py -k tenant` falhou nos dois testes (`test_define_tenant_antes_de_processar` e `test_sem_contexto_de_tenant_cruzado`, com `assert None == <uuid>`). Restaurada a linha, os dois passaram. `git diff app/jobs/worker.py` ficou vazio, sem alteração remanescente.
- **3.2 execução viva.** Clínica fictícia semeada com `cnotini` em um UUID gerado na execução. A mensagem enviada pelo CLI criou o job em `pending` com `attempts` 0 e `locked_by` nulo. O worker rodado como processo (`python -m app.jobs.worker`, laço `rodar()`) processou o job para `done`, `attempts` 1 e `locked_by` preenchido. Depois de processar, o worker ficou ocioso sem erro (stdout e stderr vazios) e encerrou ao ser parado, sem deixar job em `processing`. A limpeza com `cnotini` pelo UUID devolveu as contagens de `clinicas`, `mensagens` e `jobs` ao valor anterior.
- **3.3 suíte completa.** `pytest tests/ -v`, `71 passed`.

## Bloqueios e pendências

## Links

- [`etapas.md`](./etapas.md): plano de construção, etapas 0 a 21
- [`estudo.md`](./estudo.md): escopo, premissas e orçamento do estudo
- [`arquitetura.md`](./arquitetura.md): decisões técnicas, modelo de dados e questões em aberto
- [`principios.md`](./principios.md): princípios e como são verificados
- [`decisions/README.md`](./decisions/README.md): registros de decisão (ADRs)
- [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md): diagnósticos históricos
