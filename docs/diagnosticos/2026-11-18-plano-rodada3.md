```
Papel: Plano de trabalho local derivado da inspeção de 2026-11-18. Não é versionado e não reflete o estado atual.
Entrada: docs/status.md
Relaciona-se com: ../status.md, ../etapas.md, ../arquitetura.md, ../decisions/0002-contas-de-banco.md, ../decisions/0004-conflito-de-horario.md, 2026-10-27-rodada2.md
```

# Plano de trabalho da rodada 3

Este plano organiza os achados da inspeção de 2026-11-18 na branch `wip/agendamentos`. Nenhum código foi alterado. Os testes não foram executados durante a inspeção.

Legenda de evidência:

- **Confirmado:** lido no código e coerente com o comportamento documentado do Postgres ou do SQLAlchemy.
- **Confirmado pelo desenvolvedor:** observado em execução real.
- **Suspeita:** depende de verificação no banco.

## 0. Correção do diagnóstico: PK de `mensagens`

A inspeção tratou a migration `7e9ab495716d` como inócua num banco novo. Isso estava errado. Num banco criado do zero, a tabela `mensagens` fica sem chave primária até essa migration rodar (confirmado pelo desenvolvedor).

Causa (confirmado):

1. [63eccb28bdf3](../../migrations/versions/63eccb28bdf3_initial_schema_with_tenants.py) declara na mesma tabela `PrimaryKeyConstraint('id')`, sem nome, e `UniqueConstraint('id', name='uq_mensagens_message_id')`.
2. Ao executar um `CREATE TABLE` com PK e UNIQUE sobre as mesmas colunas, o Postgres descarta o índice repetido e mantém só o da PK. Se a PK não tem nome e a UNIQUE tem, o nome da UNIQUE é passado para a PK. O resultado é uma única constraint, do tipo PRIMARY KEY, chamada `uq_mensagens_message_id`. Não existe `mensagens_pkey`.
3. [d109eb356688](../../migrations/versions/d109eb356688_renomeia_constraint_mensagens_para_pk_.py) renomeia essa constraint para `pk_mensagens`. O nome passa a ser correto, porque ela é a PK.
4. [1bc74598f301:7-11](../../migrations/versions/1bc74598f301_remove_unique_redundante_de_mensagens.py#L7-L11) parte de uma premissa falsa: diz que `mensagens_pkey` existe e que `pk_mensagens` é uma UNIQUE redundante. A linha 27 roda `op.drop_constraint('pk_mensagens', 'mensagens', type_='unique')`. No Postgres, o `type_` não muda o SQL gerado, que é só `ALTER TABLE mensagens DROP CONSTRAINT pk_mensagens`. Isso remove a única PK.
5. Sem índice único em `id`, o `ON CONFLICT (id)` de [queue.py](../../app/jobs/queue.py) falha com "there is no unique or exclusion constraint matching the ON CONFLICT specification".
6. [7e9ab495716d](../../migrations/versions/7e9ab495716d_garante_pk_em_mensagens_id.py) recria a PK como `mensagens_pkey`. Ela é necessária, não inócua.

Problemas que continuam:

- A docstring da `1bc74598f301` está errada e induz a erro.
- O downgrade da `7e9ab495716d` é `pass` e o da `1bc74598f301` cria uma UNIQUE chamada `pk_mensagens`. Descendo até antes da `1bc7`, o banco fica com a PK `mensagens_pkey` e mais uma UNIQUE `pk_mensagens`. Esse estado não é igual ao que existia antes do upgrade.
- Nenhum teste nem a CI detectou a perda da PK, porque a CI não compara o schema com os models nem faz o ciclo sobe, desce e sobe.

O tratamento está nos itens A6 e B1.

## Estado das etapas

- [status.md](../status.md) diz que a etapa ativa é a 4, parcial, e que a 5 não foi iniciada.
- Esta branch já tem a 5.5 e a 5.1. [etapas.md:154](../etapas.md#L154) prevê a 5.5 antes da 5.1, mas não prevê começar a 5 antes de concluir a 4.
- Esse desvio precisa de decisão do desenvolvedor: registrar como exceção ou pausar a etapa 5. Item B10.

## Grupo A: exige decisão de schema ou arquitetura e ADR

### A1. FKs compostas com `tenant_id`

- **Classificação:** Crítico. Confirmado pela leitura do código, sem execução.
- **O que muda:** as tabelas pai ganham UNIQUE `(tenant_id, id)`. As FKs filhas passam a referenciar `(tenant_id, id)`. Assim o banco impede que uma linha da clínica A aponte para um registro da clínica B. A verificação de integridade referencial do Postgres ignora o RLS, por isso a FK simples não protege.
- **FKs afetadas:**
  - `agendamentos.profissional_id` e `agendamentos.servico_id`
  - `horarios_trabalho.profissional_id`
  - `profissional_servicos.profissional_id` e `profissional_servicos.servico_id`
  - `handoffs.conversa_id`
- **Arquivos:** nova migration em `migrations/versions/`, [app/db/models.py](../../app/db/models.py), [tests/isolation/test_isolation_rls.py](../../tests/isolation/test_isolation_rls.py), novo ADR em `decisions/`.
- **Teste que prova o problema:** criar as clínicas A e B com `cnotini` e um profissional em B. Com `app_clinicas` e `app.tenant_id = A`, inserir um agendamento com o `profissional_id` de B. Hoje a inserção passa. Depois da mudança, deve falhar com violação de FK. Repetir para cada FK da lista.
- **Etapa:** 5, antes da 5.2 e da 5.3. Reforça o critério de isolamento de relacionamentos da regra 6 do CLAUDE.md.

### A2. Ordem de processamento e interação com `lock_timeout`

- **Classificação:** Importante. Confirmado pela leitura do código.
- **O que muda:** definir a garantia de ordem por conversa, que é a pendência da etapa 4. A mesma decisão resolve o problema do `lock_timeout` de 5 s com retry imediato. Hoje uma mensagem que espera mais de cerca de 15 s pelo lock da conversa gasta as 3 tentativas e vai para `dead`. Uma opção é o worker não capturar o job de uma conversa que já tem job em `processing`. Outra é reagendar com backoff sem gastar tentativa. A escolha cabe ao ADR.
- **Arquivos:** [app/jobs/worker.py](../../app/jobs/worker.py), [app/core/conversas.py](../../app/core/conversas.py), possivelmente uma migration de índice em `jobs`, [tests/concurrency/](../../tests/concurrency/), novo ADR.
- **Teste que prova o problema:**
  1. Enfileirar 2 jobs da mesma conversa.
  2. Rodar 2 workers com um `processamento` que dorme 20 s dentro de `conversa_travada`.
  3. Hoje o segundo job termina em `dead`. Depois da mudança, os dois devem terminar em `done`, na ordem de chegada.
  4. Um segundo teste deve verificar a ordem com 3 ou mais mensagens e 2 workers.
- **Etapa:** 4.

### A3. Idempotência entre o processamento e a finalização do job

- **Classificação:** Importante. Confirmado pela leitura do código. Inofensivo hoje, porque o processamento ainda não tem efeitos externos.
- **O que muda:** o commit da sessão `app_clinicas` e o `finalizar_job` são transações separadas ([worker.py:146-158](../../app/jobs/worker.py#L146-L158)). Se o worker morrer entre as duas, ou se o job passar de 300 s e for recapturado, o processamento se repete. É preciso decidir entre uma chave de idempotência por job, gravada junto com o efeito, e um limite de tempo de processamento menor que `LIMITE_LOCK_SEGUNDOS`.
- **Arquivos:** [app/jobs/worker.py](../../app/jobs/worker.py), [app/core/processamento.py](../../app/core/processamento.py), migration se for criada uma coluna ou tabela de idempotência, novo ADR.
- **Teste que prova o problema:** usar um `processamento` que grava uma linha e depois forçar uma exceção em `finalizar_job`. Na recaptura do job, a linha é gravada duas vezes. Depois da mudança, deve existir uma linha só.
- **Etapa:** 5.3, antes de criar agendamentos a partir do worker. Tem de estar resolvido antes da etapa 17, que envia mensagens.

### A4. Redução dos grants de `app_clinicas`

- **Classificação:** Importante. Confirmado pela leitura do código.
- **O que muda:** [21bc40ab245c:34-38](../../migrations/versions/21bc40ab245c_cria_role_app_clinicas_com_permissoes_.py#L34-L38) dá SELECT, INSERT, UPDATE e DELETE em todas as tabelas. Também configura o mesmo grant por padrão em toda tabela futura. A proposta:
  - `log_auditoria` e `consents` ficam só com SELECT e INSERT.
  - Revisar INSERT em `clinicas`.
  - Revisar UPDATE e DELETE em `jobs`.
  - Trocar o `ALTER DEFAULT PRIVILEGES` por grants explícitos em cada migration de tabela nova.
- **Restrição:** a regra 21 do CLAUDE.md exige pedido explícito e ADR. Este item só começa com essa autorização.
- **Arquivos:** nova migration, ADR novo ou revisão do [ADR 0002](../decisions/0002-contas-de-banco.md), testes novos de grants.
- **Teste que prova o problema:** como `app_clinicas`, com o tenant correto, rodar `DELETE FROM log_auditoria`. Hoje passa. Depois da mudança, deve falhar com `permission denied`.
- **Etapa:** 7, que introduz a auditoria. Pode ser antecipada se o desenvolvedor pedir.

### A5. NOT NULL, `server_default` e CHECK nas colunas de controle

- **Classificação:** Importante. Confirmado pela leitura do código.
- **O que muda:** mudança de schema sem ADR novo, mas com decisão sobre os valores válidos.
  - `jobs.status`, `run_at`, `attempts` e `max_attempts` passam a ser NOT NULL com `server_default`.
  - `conversas.estado_conversa` e `human_mode` passam a ser NOT NULL com `server_default`.
  - `jobs.status` ganha CHECK com os valores do worker.
  - `conversas.estado_conversa` ganha CHECK com os estados de [estados.py](../../app/core/estados.py).
  - `mensagens.direcao` ganha CHECK com `entrada` e `saida`. Os dados de teste que usam `'in'` precisam ser corrigidos.
- **Arquivos:** nova migration, [app/db/models.py](../../app/db/models.py), [tests/isolation/test_isolation_rls.py](../../tests/isolation/test_isolation_rls.py) (seed com `'in'` e com jobs sem `attempts`).
- **Teste que prova o problema:** inserir com `cnotini` um job sem `attempts` e sem `run_at` e rodar o worker. Hoje o job nunca é capturado e nunca vai para `dead`. Depois da mudança, a inserção usa os defaults e o job é processado. Também inserir `direcao = 'xyz'` e verificar que a inserção falha.
- **Etapa:** 4, porque afeta a fila e o estado da conversa.

### A6. Coerência das migrations de `mensagens`

- **Classificação:** Importante. Confirmado pela leitura do código e pelo desenvolvedor.
- **O que muda:** a cadeia `63ecc`, `d109`, `1bc7` e `7e9a` já foi aplicada e não deve ser reescrita sem decisão. Opções:
  - Manter a cadeia e só corrigir a docstring da `1bc74598f301` e os downgrades.
  - Reescrever a cadeia, o que só é aceitável se nenhum banco compartilhado já tiver aplicado essas migrations.
- **Decisão:** a escolha é do desenvolvedor. A regra de que as migrations aplicadas são imutáveis está no [ADR 0001](../decisions/0001-alembic.md), se ele tratar disso.
- **Arquivos:** [1bc74598f301](../../migrations/versions/1bc74598f301_remove_unique_redundante_de_mensagens.py), [7e9ab495716d](../../migrations/versions/7e9ab495716d_garante_pk_em_mensagens_id.py).
- **Teste que prova o problema:** o ciclo do item B1. Rodar `alembic upgrade head`, `alembic downgrade d109eb356688` e listar as constraints de `mensagens`. Hoje aparecem `mensagens_pkey` e `pk_mensagens`, quando deveria aparecer só a PK.
- **Etapa:** 2, já concluída. O item corrige um critério de pronto dela ("cada migration sobe, desce e sobe de novo sem erro").

### A7. Origem do `tenant_id` na entrada de mensagens

- **Classificação:** Importante como risco futuro. Confirmado pela leitura do código.
- **O que muda:** o CLI aceita o `tenant_id` de quem chama ([cli.py:52](../../app/channels/cli.py#L52)). Isso é aceitável no estudo. O webhook precisa derivar o tenant do número de destino e validá-lo antes de chamar `gravar_e_enfileirar`. Isso deve ser decidido em ADR antes de implementar o webhook.
- **Arquivos:** futuro `app/channels/whatsapp.py`, [app/jobs/queue.py](../../app/jobs/queue.py), ADR novo.
- **Teste que prova o problema:** na etapa 17, um webhook com um número de destino que não pertence a nenhuma clínica deve ser rejeitado sem gravar nada.
- **Etapa:** 17, junto com a Q-19.

## Grupo B: correções pequenas sem decisão

### B1. CI com ciclo de migrations e `alembic check`

- **Classificação:** Crítico para reprodutibilidade. Confirmado pela leitura do código.
- **O que muda:** em [ci.yml](../../.github/workflows/ci.yml), adicionar:
  - `alembic upgrade head`, `alembic downgrade base` e `alembic upgrade head` de novo.
  - `alembic check`, para comparar os models com o schema.
  - Uma consulta que falha se alguma tabela não tiver PK.
- **Arquivos:** [.github/workflows/ci.yml](../../.github/workflows/ci.yml).
- **Teste que prova o problema:** com a cadeia anterior à `7e9ab495716d`, o `alembic check` ou a consulta de PK falharia. É exatamente o erro da seção 0.
- **Etapa:** 2, critério de pronto ainda não verificado automaticamente.

### B2. README com o setup do zero

- **Classificação:** Crítico para reprodutibilidade. Confirmado pela leitura do código.
- **O que muda:** o [README.md](../../README.md) está vazio. Ele deve documentar:
  - a versão do Python,
  - a cópia do `.env.example`,
  - `docker compose up -d`,
  - `alembic upgrade head`,
  - o passo manual de `ALTER ROLE ... PASSWORD` para `app_clinicas` e `worker_jobs`,
  - o comando dos testes.
  
  Também deve dizer que `APP_DB_USER` e `WORKER_DB_USER` precisam ter exatamente os nomes das roles criadas nas migrations. O [.env.example](../../.env.example) ganha valores fictícios e comentários.
- **Arquivos:** [README.md](../../README.md), [.env.example](../../.env.example).
- **Teste que prova o problema:** clonar o repositório numa pasta nova e seguir só o README. Hoje não há instrução. Depois da mudança, `pytest` deve rodar até o fim.
- **Etapa:** 1. O README completo é critério da etapa 12, em [estudo.md, seção 9](../estudo.md#9-critério-de-pronto-e-readme).

### B3. `CREATE ROLE` com verificação de existência

- **Classificação:** Importante. Confirmado pela leitura do código.
- **O que muda:** a [c77398abee4a](../../migrations/versions/c77398abee4a_substitui_scheduler_service_por_worker_.py) e a [e4ffcb741dc3](../../migrations/versions/e4ffcb741dc3_cria_role_scheduler_service_com_.py) passam a criar a role só se ela não existir, com um bloco `DO`. Roles valem para o cluster inteiro.
- **Restrição:** isto não muda atributos, grants nem policies, só evita erro na criação. Mesmo assim mexe em migrations de roles, então precisa de confirmação explícita pela regra 21.
- **Arquivos:** as duas migrations citadas.
- **Teste que prova o problema:** criar um segundo banco no mesmo container e rodar `alembic upgrade head` nele. Hoje falha com "role already exists".
- **Etapa:** 2.

### B4. Tratamento de erros em `rodar()`

- **Classificação:** Importante. Confirmado pela leitura do código.
- **O que muda:** em [worker.py:193-197](../../app/jobs/worker.py#L193-L197), capturar `SQLAlchemyError` no laço, registrar o erro e esperar antes de tentar de novo, sem encerrar o processo.
- **Arquivos:** [app/jobs/worker.py](../../app/jobs/worker.py), [tests/concurrency/test_worker.py](../../tests/concurrency/test_worker.py).
- **Teste que prova o problema:** com um engine que falha na primeira chamada e funciona na segunda, `rodar(max_iteracoes=2)` hoje lança exceção. Depois da mudança, deve concluir e processar o job.
- **Etapa:** 4.

### B5. `cancelar` com filtro de status e de tenant

- **Classificação:** Importante. Confirmado pela leitura do código.
- **O que muda:** em [agenda_propria.py:74-81](../../app/agenda/agenda_propria.py#L74-L81), adicionar `AND status = 'agendado'` e `AND tenant_id = current_setting('app.tenant_id')::uuid`, como segunda barreira do [ADR 0002](../decisions/0002-contas-de-banco.md).
- **Arquivos:** [app/agenda/agenda_propria.py](../../app/agenda/agenda_propria.py), [tests/integration/test_agenda_propria.py](../../tests/integration/test_agenda_propria.py).
- **Testes que provam o problema:**
  - Cancelar duas vezes o mesmo agendamento. Hoje a segunda chamada indica sucesso.
  - Criar um agendamento real em B e tentar cancelá-lo como A. Deve indicar que não encontrou, e o registro de B deve continuar `agendado`.
- **Etapa:** 5.1.

### B6. Validação de fuso em `criar`

- **Classificação:** Importante. Confirmado pela leitura do código.
- **O que muda:** em [agenda_propria.py:43-68](../../app/agenda/agenda_propria.py#L43-L68), rejeitar `inicio` e `fim` sem `tzinfo` e rejeitar `fim <= inicio` antes de ir ao banco.
- **Arquivos:** [app/agenda/agenda_propria.py](../../app/agenda/agenda_propria.py), [tests/integration/test_agenda_propria.py](../../tests/integration/test_agenda_propria.py).
- **Teste que prova o problema:** chamar `criar` com `datetime(2026, 12, 1, 9, 0)` sem fuso. Hoje a gravação passa e o horário depende do `TimeZone` da sessão. Depois da mudança, deve lançar erro de validação.
- **Etapa:** 5.1.

### B7. Testes da constraint EXCLUDE

- **Classificação:** Crítico para a cobertura. Confirmado: nenhum teste exercita a constraint hoje.
- **O que muda:** só testes novos, sem alterar código.
  - Sobreposição rejeitada com `23P01`.
  - Horários adjacentes aceitos.
  - Agendamento cancelado não conflita.
  - Duas inserções concorrentes do mesmo horário, com só uma aceita.
  - Mesmo horário em clínicas diferentes, ambos aceitos.
- **Arquivos:** [tests/integration/test_agenda_propria.py](../../tests/integration/test_agenda_propria.py), `tests/concurrency/`.
- **Teste que prova o problema:** os próprios testes. Se a constraint for removida, eles devem falhar.
- **Etapa:** 5.5, cujo critério já prevê essa constraint.

### B8. Teste automático de cobertura do RLS

- **Classificação:** Importante. Confirmado pela leitura do código.
- **O que muda:** só um teste novo, sem alterar policies. Ele lista no catálogo do banco todas as tabelas com coluna `tenant_id` e falha se alguma não tiver RLS, FORCE e policy `isolamento_tenant`, ou se não estiver em `TABELAS_TENANT`.
- **Arquivos:** [tests/isolation/test_isolation_rls.py](../../tests/isolation/test_isolation_rls.py).
- **Teste que prova o problema:** criar localmente uma tabela com `tenant_id` sem policy. O teste deve falhar.
- **Etapa:** 2. Atende a regra 20 do CLAUDE.md.

### B9. Testes do worker independentes da fila global

- **Classificação:** Importante. Confirmado pela leitura do código.
- **O que muda:** os testes que chamam `reivindicar_job` e `processar_um` hoje pegam qualquer job pendente. Cada teste deve limpar a fila no início ou filtrar pelos jobs que criou. Os ids fixos (`msg-a`, `colisao-x`, `msg-dedupe-1`) passam a ter um sufixo aleatório.
- **Arquivos:** [tests/concurrency/test_worker.py](../../tests/concurrency/test_worker.py), [tests/concurrency/test_mensagens_seguidas.py](../../tests/concurrency/test_mensagens_seguidas.py), [tests/concurrency/test_dedupe_mensagens.py](../../tests/concurrency/test_dedupe_mensagens.py).
- **Teste que prova o problema:** enfileirar um job pelo CLI e rodar a suíte. Hoje os testes do worker podem processar o job errado e falhar.
- **Etapa:** 3.

### B10. Documentos que contradizem o código

- **Classificação:** Importante. Confirmado pela leitura.
- **O que muda:**
  - [status.md](../status.md): registrar a 5.5 e a 5.1 nesta branch, a decisão sobre o desvio de ordem das etapas 4 e 5, a contagem real de testes e a falha da PK de `mensagens` com a correção.
  - Q-20 em [arquitetura.md](../arquitetura.md): `agendamentos` já tem `contato_telefone`. Registrar como resolvida ou atualizar.
  - Q-23 em [arquitetura.md](../arquitetura.md): remover a afirmação de que o código isola a conversão de fuso num único ponto, ou criar esse ponto (B6).
  - [ADR 0004:38](../decisions/0004-conflito-de-horario.md#L38): marcar o SAVEPOINT e a tradução do `23P01` como planejados para a 5.3 (C2), não como implementados. Trocar o travessão do título, linha 7.
  - [base.py:3-5](../../app/agenda/base.py#L3-L5): corrigir a referência a uma "pendência da etapa 5" que não existe em [etapas.md](../etapas.md), ou criar a tarefa de disponibilidade lá.
  - [etapas.md](../etapas.md), etapa 5: `tests/unit/` e `app/handoff/` não existem. Manter só quando forem criados.
  - [decisions/README.md](../decisions/README.md): listar os ADRs.
  - Regra 18 do CLAUDE.md: esclarecer que o worker usa `worker_jobs` só para a fila, como no [ADR 0002](../decisions/0002-contas-de-banco.md).
- **Arquivos:** os citados.
- **Teste que prova o problema:** não se aplica. Revisão manual contra o código.
- **Etapa:** 4 e 5.

### B11. Limpeza de código morto e redundância

- **Classificação:** Melhoria. Confirmado pela leitura do código.
- **O que muda:**
  - Remover a fixture `client` de [conftest.py:6-8](../../tests/conftest.py#L6-L8).
  - Separar [requirements.txt](../../requirements.txt) entre produção e dev. Remover `psycopg[binary]` e os pacotes sem uso nesta fase.
  - Remover `pytest-timeout==2.4.0 ` com espaço sobrando, ou garantir que ele esteja nas dependências usadas pela CI.
  - Remover `import sqlalchemy as sa` sem uso nas migrations. Isso altera arquivos de migrations já aplicadas, mas sem efeito no schema.
  - Remover os índices redundantes `idx_clinicas_tenant_id`, `idx_conversas_tenant` e `idx_pacientes_contatos_tenant` numa migration nova. Os models também mudam.
  - Revisar no [.gitignore](../../.gitignore) as entradas `.dockerignore` e `docs/glossario.md`.
  - `docker-compose.yml`: publicar a porta só em `127.0.0.1`.
- **Arquivos:** os citados.
- **Teste que prova o problema:** a suíte completa deve continuar passando. O `alembic check` do B1 deve ficar limpo.
- **Etapa:** 1 e 2.

### B12. Melhorias pequenas de robustez

- **Classificação:** Melhoria. Confirmado pela leitura do código.
- **O que muda:**
  - [conversas.py:93-108](../../app/core/conversas.py#L93-L108): erro explícito quando a linha da conversa não for encontrada.
  - [cli.py:57-68](../../app/channels/cli.py#L57-L68): validar `--tenant` como UUID e tratar `ColisaoIdEntreTenants` sem encerrar.
  - [database.py](../../app/db/database.py): adicionar `connect_timeout`.
  - [worker.py:155](../../app/jobs/worker.py#L155): gravar em `last_error` só o tipo e uma mensagem curta, sem os parâmetros do SQL, para não gravar telefone e conteúdo.
- **Arquivos:** os citados, mais `tests/` para o CLI.
- **Testes que provam o problema:**
  - CLI com `--tenant abc`: hoje encerra com traceback.
  - Job que falha por erro de banco: hoje o `last_error` contém os parâmetros da query.
- **Etapa:** 3 e 4.

## Grupo C: adiar para a etapa correspondente

### C1. Índices de FK e índice parcial da fila

- **Classificação:** Melhoria. Confirmado pela leitura do código. Sem medição.
- **O que muda:**
  - Índices em `horarios_trabalho.profissional_id`, `profissional_servicos.servico_id`, `agendamentos.servico_id` e `agendamentos.profissional_id`.
  - Índice parcial `(run_at, id) WHERE status IN ('pending', 'processing')` em `jobs`.
  - Parte disso pode ser feita junto com o A1, porque as FKs compostas já criam índices `(tenant_id, id)` nas tabelas pai.
- **Arquivos:** nova migration, [app/db/models.py](../../app/db/models.py).
- **Teste que prova o problema:** `EXPLAIN` da query de captura com volume de dados fictício. Sem volume, não há ganho mensurável.
- **Etapa:** 12.

### C2. Tradução do `23P01` e SAVEPOINT

- **Classificação:** Importante. Confirmado: o [ADR 0004](../decisions/0004-conflito-de-horario.md) descreve, mas o código não tem.
- **O que muda:** em `criar` e na futura remarcação, envolver a inserção num SAVEPOINT, capturar `23P01` e lançar um erro de domínio de horário ocupado.
- **Arquivos:** [app/agenda/agenda_propria.py](../../app/agenda/agenda_propria.py), [app/agenda/base.py](../../app/agenda/base.py), testes de integração.
- **Teste que prova o problema:** criar dois agendamentos sobrepostos. Hoje sobe um `IntegrityError` cru e a transação inteira fica abortada. Depois da mudança, deve subir o erro de domínio e a transação deve continuar utilizável.
- **Etapa:** 5.2 e 5.3.

### C3. Disponibilidade no `AgendaProvider`

- **Classificação:** Melhoria. Confirmado pela leitura do código.
- **O que muda:** a [arquitetura](../arquitetura.md) define a interface com disponibilidade, criar e cancelar. Hoje só existem criar e cancelar.
- **Arquivos:** [app/agenda/base.py](../../app/agenda/base.py), [app/agenda/agenda_propria.py](../../app/agenda/agenda_propria.py).
- **Teste que prova o problema:** consultar a disponibilidade de um profissional com um horário ocupado. O horário não deve aparecer.
- **Etapa:** 5.2 ou 5.3, conforme o B10 decidir.

### C4. Uso de `validar_transicao` em produção

- **Classificação:** Melhoria. Confirmado: nenhum chamador fora dos testes.
- **O que muda:** toda escrita de `estado_conversa` deve passar por `validar_transicao`.
- **Arquivos:** [app/core/estados.py](../../app/core/estados.py), [app/core/processamento.py](../../app/core/processamento.py).
- **Teste que prova o problema:** o processamento tenta uma transição inválida, de `encerrada` para `aguardando_confirmacao`. Deve ser rejeitada e o estado não deve mudar.
- **Etapa:** 7, quando o processamento passa a mudar estados.

### C5. Retenção de jobs e varredura de órfãos

- **Classificação:** Melhoria. Confirmado pela leitura do código.
- **O que muda:**
  - Limpeza periódica de jobs `done` e `dead` antigos.
  - A varredura de órfãos deixa de rodar a cada iteração.
  - O worker passa a fechar a transação `worker_jobs` antes de processar, o que depende do A2.
- **Arquivos:** [app/jobs/worker.py](../../app/jobs/worker.py).
- **Teste que prova o problema:** contar as consultas de varredura em 100 iterações do worker. Medir o tempo de captura com muitos jobs `done`.
- **Etapa:** 12.

### C6. Coluna `conversas.historico` e parâmetros sem uso

- **Classificação:** Melhoria. Confirmado pela leitura do código.
- **O que muda:**
  - Decidir se `historico` será usada no contexto do LLM ou removida.
  - Remover o parâmetro `conexao` e a leitura não feita de `mensagem_id` em [processamento.py](../../app/core/processamento.py), ou passar a usá-los.
- **Arquivos:** [app/db/models.py](../../app/db/models.py), migration, [app/core/processamento.py](../../app/core/processamento.py).
- **Teste que prova o problema:** não se aplica. É limpeza.
- **Etapa:** 6.

## Ordem sugerida

1. B10, a decisão sobre o desvio das etapas 4 e 5 e o registro da falha da PK em `status.md`.
2. B1 e B2, a reprodutibilidade, para que tudo o que vier depois seja verificável.
3. A2, A5 e B4, para fechar a etapa 4.
4. A1, B5, B6, B7 e B8, o isolamento de relacionamentos e as garantias da 5.5 e da 5.1.
5. A3, C2 e C3, junto com a 5.2 e a 5.3.
6. A4, só com pedido explícito.

## O que continua sem validação

- Nenhum teste foi executado na inspeção. O banco não foi consultado.
- A afirmação de que a verificação de FK ignora o RLS vem da documentação do Postgres, sem teste prático.
- O comportamento do Postgres na seção 0 vem do código fonte e da documentação. Ele bate com a falha observada pelo desenvolvedor, mas o nome final da constraint não foi conferido no catálogo.
