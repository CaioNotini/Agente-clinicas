```
Papel: Índice de entrada único da documentação e registro do estado verificado mais recente.
Entrada: docs/status.md
Relaciona-se com: etapas.md, estudo.md, arquitetura.md, principios.md, decisions/README.md, diagnosticos/2026-11-18-plano-rodada3.md, diagnosticos/2026-11-24-rodada4.md, diagnosticos/2026-11-25-rodada5.md, diagnosticos/2026-11-25-instabilidade-concorrencia.md, guias_respostas/guia_respostas.md
```

# Status do projeto

Estado verificado em 2026-11-25. O histórico detalhado de cada mudança fica no git log e nos [ADRs](./decisions/README.md).

## Onde estamos

**Etapa 6 concluída. Próxima etapa ativa: 7, classificação, mensagens fixas e auditoria.** As etapas 0 a 6 estão concluídas.

Etapa 6 (concluída), resumo: chamada ao modelo por uma interface única. `LLMClient` e a implementação `AnthropicClient` sobre o SDK `anthropic==2.14.0` (versão `2026-10-21` da API), com o modelo em `LLM_MODEL` (`claude-haiku-5-5`), validado só na criação do cliente. Hierarquia de erros transitório e permanente, com o permanente herdando de `ErroPermanente`. Telemetria de cada chamada no log estruturado, nos eventos `llm_chamada` e `llm_chamada_falhou`, sem prompt, conteúdo nem telefone. Backoff exponencial com teto no retry de jobs, só no retry e nunca no `dead` (fórmula e valores no [ADR 0010](./decisions/0010-llmclient.md)). Teste real com o marcador `llm_real`, fora da CI. Decisões em [ADR 0010](./decisions/0010-llmclient.md) e [ADR 0005](./decisions/0005-ordem-por-conversa.md). O processamento ainda não chama o LLM. A ligação com o conteúdo da mensagem entra na etapa 7, com a classificação. Antes da 7.1, em 2026-11-25, a criação do SDK passou a ter um único ponto, [`app/llm/fabrica.py`](../app/llm/fabrica.py), que fixa `max_retries=0` e o timeout (A8 e B20 da [rodada 5](./diagnosticos/2026-11-25-rodada5.md)).

| Etapa  | Estado        |
| ------ | ------------- |
| 0 a 6  | concluídas    |
| 7 a 21 | não iniciadas |

## O que está verificado

Última verificação em 2026-11-25, no banco do Docker local:

- `pytest tests/ -q` = `500 passed`, 4 deselected (`llm_real`), 1 warning conhecido (TestClient do Starlette), em 2026-11-25, no banco local no head `a5587f532a88`, com o código dos blocos 1 a 4 da [rodada 5](./diagnosticos/2026-11-25-rodada5.md). Rodado com `pytest-asyncio`, `pytest-mock`, `ruff` e `mypy` desinstalados do `.venv`, o que confirma que a suíte não depende deles (B22). Antes, em 2026-11-24, a suíte tinha `448 passed` num ambiente limpo instalado do zero pelo `requirements-dev.txt`. Esse ambiente limpo não foi repetido com o `requirements-dev.txt` atual.
- `pytest -m llm_real -v`, rodado pelo desenvolvedor em 2026-11-25 = `4 passed`, 490 deselected. Única execução paga, aprovada na implementação e no teste (regra 22). Não roda na CI.
- O banco local estava em `c3d8e5a1f297` e foi levado ao head `a5587f532a88` com `alembic upgrade head` em 2026-11-25. O `alembic check` passou ("No new upgrade operations detected.").
- CI mais recente verificada: run `45678396796`, commit `706dce9`, sucesso. Log lido: o ciclo de migrations (`upgrade head`, `downgrade base`, `upgrade head`) aplica a `a5587f532a88`, o `alembic check` não acusa diferença, [`scripts/verificar_pks.sql`](../scripts/verificar_pks.sql) confirma chave primária em todas as tabelas e o pytest dá `490 passed, 4 deselected`. Os commits dos blocos 1 a 4 da rodada 5 ainda não foram enviados ao GitHub e não têm CI.
- Lock da agenda por profissional ([ADR 0011](./decisions/0011-lock-de-agenda-por-profissional.md)), em 2026-11-25: 4 contatos criando no mesmo horário e 4 remarcando para o mesmo horário, 20 execuções seguidas de cada, com processo novo, todas com 1 aceito e 3 `HorarioIndisponivel`, sem `40P01`. Com a largada logo antes do INSERT, sem o lock a criação falhou em 15 de 20 (163 deadlocks no log) e a remarcação passou 20 de 20, sem nenhum deadlock e com 123 `23P01` limpos. Pela ausência de deadlock, só o teste de criação detecta a falta do lock. Pela presença do lock, criação e remarcação têm teste próprio, e sem o lock os dois falham. O mesmo vale para uma remarcação que mova a linha com UPDATE, sem passar por `AgendaPropria.criar`. A causa da diferença entre os dois caminhos está como pergunta em aberto no ADR.
- Isolamento com `app.tenant_id` vazio, em 2026-11-25: numa conexão `app_clinicas` em que o setting ficou `''` depois de uma transação, SELECT, INSERT, UPDATE e DELETE não devolvem, criam, alteram nem apagam linha em nenhuma das 15 tabelas, com as clínicas A e B semeadas. Nas 60 combinações a barreira foi a policy, com `22P02`. Nenhuma foi barrada por falta de grant. O teste só aceita como barreira o `22P02` ou o `42501` de RLS, e qualquer outro erro, como FK ou unicidade, o reprova. Prova por mutação, só no teste: com a conexão vendo a clínica B, 59 dos 60 casos falharam. O que passou foi o INSERT em `clinicas` com UUID novo, barrado pela própria policy (`42501`). Na versão anterior do teste, 7 INSERTs teriam passado disfarçados de erro de FK ou de unicidade. As linhas criadas pela mutação foram apagadas pela limpeza do teste, sem sobra no banco.
- Setup do zero só pelo [`README.md`](../README.md), num clone limpo, passou em 2026-11-20. A repetição fica com o desenvolvedor, na máquina local dele, e não é pendência do agente.
- pylint, black e isort passam e reprovam a CI quando falham.
- Prova por mutação da etapa 5, à mão e fora da suíte: sem RLS e sem o filtro explícito de tenant, os testes de isolamento do serviço e do handoff falham, o que confirma as duas barreiras. A segunda barreira da verificação de duplicata da fila tem teste próprio, `test_sem_rls_o_filtro_de_tenant_separa_colisao_de_duplicata` em [`test_dedupe_mensagens.py`](../tests/concurrency/test_dedupe_mensagens.py), que roda sem RLS pela conta de administração. Sem o tratamento de `ErroPermanente`, os testes do worker falham. Em 2026-11-25, sem `tenant_id = :t` na UPDATE de `finalizar_job`, só `test_finalizar_job_com_tenant_trocado_nao_altera_o_job` falha (B23), e o código foi restaurado.
- Critério de pronto da etapa 0 conferido em 2026-11-25, com o conteúdo de [`pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md) aprovado pelo desenvolvedor como a tarefa 0.3. Os três arquivos de [`fake_clinic/`](./fake_clinic/) têm o cabeçalho de relações. O [`FAQ.md`](./fake_clinic/FAQ.md) tem 15 perguntas, cada uma com categoria (14 `permitido` e 1 `sem_informacao`). A lista de bloqueadas tem 13 perguntas, 8 `clinico_bloqueado` e 5 `urgencia`, com formas indiretas nas perguntas 5 e 8. Os dados são fictícios (telefones `(00) 0000-000x`, CNPJ e CRM zerados, e-mails `.invalid`). Os únicos números reais são o 192 e o 188, de propósito.
- Critério de pronto da etapa 5 conferido: cada função de `app/agenda/regras.py` tem teste unitário com casos de borda, e o handoff gravado aparece no banco pela leitura da conta `app_clinicas`.

O que o código garante hoje, com a decisão de cada ponto:

- Isolamento entre clínicas por RLS, FORCE e policy `isolamento_tenant`, com cobertura conferida pelo catálogo ([ADR 0002](./decisions/0002-contas-de-banco.md)).
- FKs entre tabelas de clínica incluem `tenant_id` ([ADR 0007](./decisions/0007-fks-compostas-por-tenant.md)).
- Mensagens da mesma conversa processadas na ordem de chegada ([ADR 0005](./decisions/0005-ordem-por-conversa.md)) e sem processamento simultâneo (lock por conversa).
- Efeitos de um job confirmados uma vez só, junto com a conclusão do job ([ADR 0008](./decisions/0008-conclusao-atomica-do-job.md)).
- Transições de estado pelo grafo do [ADR 0003](./decisions/0003-grafo-de-transicoes.md).
- Erro permanente (`ConfiguracaoInvalida`, `MisturaDeTenants`) leva o job a `dead` na primeira falha, com log estruturado de erro. O texto de exceções não vai ao paciente (seções 7 e 8.1 da [arquitetura](./arquitetura.md)).
- O SDK da Anthropic só é criado em [`app/llm/fabrica.py`](../app/llm/fabrica.py), com `max_retries=0` e timeout de 60 s (5 s para a conexão), menor que o limite de órfão do job. Um teste confere os valores e varre `app/` atrás de outra criação do SDK ([ADR 0010](./decisions/0010-llmclient.md)).
- Gravações de agendamento do mesmo profissional em fila, pelo lock de transação da agenda, sem deadlock entre inserções concorrentes. `40P01` residual e `55P03` viram `ConcorrenciaNaAgenda`, sem erro cru do banco ([ADR 0011](./decisions/0011-lock-de-agenda-por-profissional.md)).
- Senhas das roles aplicadas por script, sem passo manual ([ADR 0006](./decisions/0006-provisionamento-de-roles.md)).

## Decisões recentes

- 2026-11-26: os documentos canônicos foram alinhados às 26 decisões aprovadas do [guia de respostas](./guias_respostas/guia_respostas.md), antes da 7.1. A decisão 23 foi refinada: com `urgencia` na lista de intenções, só a mensagem de urgência sai. A urgência é verificada antes do `human_mode`. Sem resposta ao lembrete, só o T-1 ganha um segundo envio, sem handoff. O destinatário do handoff passa a ser por profissional, com um destinatário padrão. Detalhes nas seções 8.1 a 8.4 e na Q-25 da [arquitetura](./arquitetura.md) (versão 2.2) e na revisão de 2026-11-26 do [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md). Nada disso está implementado ainda.

- 2026-11-25, etapa 0: existe uma única mensagem fixa de `urgencia`, que cobre todo risco imediato à vida, inclusive o pensamento de autolesão. Ela orienta o 192 ou o pronto-socorro de forma incondicional e cita o CVV (188), sem subcategoria de urgência. Perguntas administrativas nunca são `clinico_bloqueado`. Sem a informação na base, o agente oferece handoff ou seguir no automático. Regras na seção 8.3 da [arquitetura](./arquitetura.md#83-escopo-clínico).

- 2026-11-25, C6: a coluna `conversas.historico` foi removida (migration `a5587f532a88`, com downgrade que a recria). Ela nunca foi lida nem escrita. O contexto do LLM da etapa 7 virá das últimas mensagens do contato, direto de `mensagens` (`contato_telefone`, `conteudo`, `direcao`, `criada_em` por tenant). Manter `historico` duplicaria o dado, com risco de divergência e mais um ponto a apagar na exclusão do titular (LGPD). Um resumo de conversas longas, se preciso na etapa 7, será coluna nova com contrato e ADR.

## Pendências

**Previstas para etapas futuras**

- Antes da 7.2: ADR da saída da classificação. Define a lista de intenções com prioridade, como a saída separa as duas respostas de `clinico_bloqueado` e a verificação de urgência com `human_mode` ativo só pela regra da 7.1, sem LLM (seções 8.1 e 8.3 da [arquitetura](./arquitetura.md)).
- 7.3: três mensagens fixas em [`fixas.py`](../app/mensagens/fixas.py): urgência com o 192 ou o pronto-socorro e o CVV (188), clínico bloqueado e oferta de atendimento (seção 8.3 da [arquitetura](./arquitetura.md#83-escopo-clínico)). Hoje `MENSAGEM_URGENCIA` não cita o CVV e a oferta de atendimento não existe.
- Antes da 8: ADR de configuração e informações administrativas da clínica, com os itens da aba Configuração da clínica do [guia](./guias_respostas/guia_respostas.md), incluindo a regra de que dado com coluna própria não entra no RAG.
- Antes da 8: migration de `servicos.preco` de `Float` para `Numeric(10,2)`.
- Antes da 9: ADR da ação pendente da conversa, com a expiração de 15 minutos (decisão 11 do guia).
- Antes da 9: ADR do agrupamento de mensagens (decisões 10 e 14 do guia). Revê os ADRs [0005](./decisions/0005-ordem-por-conversa.md) e [0008](./decisions/0008-conclusao-atomica-do-job.md).
- Antes da 9: ADR do paciente separado do contato que escreve (terceiros, menores e privacidade).
- Antes da 9: destinatário do handoff por profissional e destinatário padrão em [`app/handoff/abertura.py`](../app/handoff/abertura.py) (revisão de 2026-11-26 do [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md)).
- Antes da 9: política para pedidos fora da antecedência (recusar, handoff ou agendar) em `regras_agendamento`.
- 17: ADR do provedor de transcrição de áudio (Whisper local no estudo, Amazon Transcribe no MVP).
- 7.2: implementar a saída estruturada no `AnthropicClient` e remover `EsquemaSaidaNaoSuportado`. Hoje `esquema_saida` preenchido levanta esse erro, que leva o job a `dead` ([ADR 0010](./decisions/0010-llmclient.md)).
- 7.2: nenhuma chamada ao LLM entre o INSERT de agendamento e o commit da transação. O lock da agenda do profissional fica até o commit, e a espera dos outros pacientes passaria do `lock_timeout` ([ADR 0011](./decisions/0011-lock-de-agenda-por-profissional.md)). O texto de resposta é gerado antes da gravação ou depois do commit.
- 7.2: chamar `criar_cliente_llm` no `main()` do worker e injetar o cliente no processamento ([ADR 0010](./decisions/0010-llmclient.md)). Hoje a função existe, mas nada a chama.
- 9: o timeout do LLM é por chamada. Um job com várias chamadas (classificação e function calling) pode somar mais que os 300 s do limite de órfão ([ADR 0010](./decisions/0010-llmclient.md)).
- 8: o [`FAQ.md`](./fake_clinic/FAQ.md) não tem mais entradas clínicas. O critério "trechos marcados como bloqueado nunca são retornados" vai precisar de um trecho clínico de teste criado na própria etapa 8.

- 13: não abrir handoff novo se já houver um aberto para a mesma conversa, motivo e agendamento. Na 5.4 cada pedido grava uma linha.
- 13: na remarcação fora da janela, o novo horário não é validado antes de abrir o handoff.
- 13: `handoffs` mistura `responder_ate` (timestamptz) com `criada_em`, `notificado_em`, `assumido_em` e `devolvido_em` (timestamp sem fuso). Resolver antes de comparar o prazo com esses instantes (C10 da rodada 4).
- 14: validar o nome do fuso ao gravar a configuração da clínica.
- 14: com entradas fora da fila, um `23P01` contra agendamento do próprio contato, sobreposto e com outro início, dá `HorarioIndisponivel` em vez de `AgendamentoDuplicado`, tanto na criação quanto na remarcação. Na remarcação o antigo continua ativo, porque o erro sobe pelo SAVEPOINT. Faz parte da ressalva sobre entradas fora da fila na seção 7 da [arquitetura](./arquitetura.md#7-modelo-de-dados).
- 7: o `mensagem_id` passado ao serviço deve vir do job. A FK garante a mesma clínica, mas não o mesmo contato.
- LGPD: a exclusão do titular que apague agendamentos precisa tratar antes os handoffs que apontam para eles (FK `NO ACTION`).
- Outros erros permanentes, como o payload sem `contato_telefone`, ainda consomem as 3 tentativas.
- `55P03` na gravação de agendamento, seja esperando o lock da agenda do profissional, seja na verificação da constraint, vira `ConcorrenciaNaAgenda` desde 2026-11-25 ([ADR 0011](./decisions/0011-lock-de-agenda-por-profissional.md)), e o job tenta de novo. O `55P03` do lock da conversa continua sem tratamento próprio.
- 7: reduzir os grants de `app_clinicas`, só com pedido explícito e ADR (item A4 do [plano](./diagnosticos/2026-11-18-plano-rodada3.md)). O UPDATE em `jobs` precisa continuar, pelo ADR 0008. Os grants de `worker_jobs` também são mais amplos que o uso, como registra o ADR 0002.
- 7: ao reduzir os grants (A4), o teste de FKs pelo catálogo passa a usar `pg_attribute` em vez de `information_schema.columns`, que só lista colunas com privilégio da role (B15 da [rodada 4](./diagnosticos/2026-11-24-rodada4.md)).
- 7: usar `validar_transicao` em toda escrita de estado (C4).
- 7: alinhar a descrição de `log_auditoria` na seção 7 da [arquitetura](./arquitetura.md) com as colunas `acao`, `descricao` e `dados` quando a auditoria for implementada. A ambiguidade continua listada abaixo até lá.
- 9: decidir a conduta para a conversa depois de uma mensagem morta. Risco aceito até lá ([ADR 0005](./decisions/0005-ordem-por-conversa.md)).
- 9: a disponibilidade oferece horários em que o próprio contato já tem consulta com outro profissional, e a criação os recusa depois com `AgendamentoDuplicado`. Decidir junto com a ferramenta `verificar_disponibilidade` (C8 da rodada 4).
- 7: enviar o esforço de raciocínio à API (por exemplo `low` na classificação) ou remover o campo `esforco` da `ConfigLLM`. Hoje o `AnthropicClient.completar` guarda o campo mas não o envia, e o `claude-haiku-5-5` usa o esforço padrão `medium`, com raciocínio adaptativo sempre ligado e tokens de raciocínio dentro de `max_tokens` ([ADR 0010](./decisions/0010-llmclient.md)).
- 10: persistir tokens, latência e modelo de cada chamada ao LLM numa tabela, com policy, `TABELAS_TENANT` e testes de isolamento. Na etapa 6 eles vão só ao log estruturado ([ADR 0010](./decisions/0010-llmclient.md)).
- 12: índices das colunas filhas das FKs, índice parcial da fila e retenção de jobs (C1 e C5).
- 12: teste de UPDATE que move uma linha própria para outra clínica (`SET tenant_id`), recusado pelo WITH CHECK da policy (C9 da rodada 4).
- 7: montar o contexto do LLM com as últimas N mensagens do contato, direto de `mensagens`, e avaliar o índice `(tenant_id, contato_telefone, criada_em)` em `mensagens` (substitui o C6, resolvido em 2026-11-25 com a remoção de `conversas.historico`).
- 17: derivar o `tenant_id` do número de destino no webhook (A7), e envio de WhatsApp como job novo, com idempotência no provedor (ADR 0008).
- 15: `ON DELETE SET NULL (mensagem_id)` exige Postgres 15 ou mais. Conferir a versão do Supabase na tarefa 15.2 (C11 da rodada 4).

- Antes da 7.1: instabilidade nos testes, diagnosticada em 2026-11-25 ([diagnóstico](./diagnosticos/2026-11-25-instabilidade-concorrencia.md)) e corrigida pela P2 e pela P1. O estouro de `test_servico_concorrencia.py` é um deadlock real entre 3 ou mais gravações no mesmo horário, e o `40P01` sai do serviço como erro cru depois das 3 tentativas. As 93 falhas da primeira execução foram de senha das roles divergente do ambiente. Em 2026-11-25 foi aplicada a P2: as esperas dos testes de concorrência seguem os prazos de [`prazos.py`](../tests/concurrency/prazos.py), e o teste do deadlock falha pela asserção, sem o pytest matar o processo. Em 2026-11-25 foi aplicada a P1: lock da agenda por profissional ([ADR 0011](./decisions/0011-lock-de-agenda-por-profissional.md)). Criação e remarcação concorrentes com 4 contatos passaram 20 de 20 vezes com processo novo, sem `40P01`. A instabilidade está resolvida.

**Ambiguidades de documentação**

- [`estudo.md`](./estudo.md), seção 4, cita um "endpoint de chat de teste" que nenhuma etapa prevê.
- A seção 7 da [arquitetura](./arquitetura.md) diz que `log_auditoria` guarda categoria e texto original, e a tabela tem `acao`, `descricao` e `dados`.

## Links

- [`etapas.md`](./etapas.md): plano de construção, etapas 0 a 21
- [`estudo.md`](./estudo.md): escopo, premissas e orçamento do estudo
- [`arquitetura.md`](./arquitetura.md): decisões técnicas, modelo de dados e questões em aberto
- [`principios.md`](./principios.md): princípios e como são verificados
- [`guias_respostas/guia_respostas.md`](./guias_respostas/guia_respostas.md): guia de respostas do agente, com as 26 decisões aprovadas e a planilha [`guia_respostas.xlsx`](./guias_respostas/guia_respostas.xlsx)
- [`decisions/README.md`](./decisions/README.md): ADRs 0001 a 0011
- [`fake_clinic/clinica.md`](./fake_clinic/clinica.md), [`fake_clinic/FAQ.md`](./fake_clinic/FAQ.md) e [`fake_clinic/pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md): base fictícia (clínica com equipe e recepção)
- [`fake_clinic/consultorio_solo.md`](./fake_clinic/consultorio_solo.md): segundo tenant fictício, consultório de um profissional só, sem recepção, para testar as regras da etapa 5 nos dois cenários
- [`diagnosticos/2026-11-25-rodada5.md`](./diagnosticos/2026-11-25-rodada5.md): diagnóstico da rodada 5, inspeção de 2026-11-25
- [`diagnosticos/2026-11-25-instabilidade-concorrencia.md`](./diagnosticos/2026-11-25-instabilidade-concorrencia.md): diagnóstico da instabilidade dos testes de concorrência, com a proposta de correção
- [`diagnosticos/2026-11-24-rodada4.md`](./diagnosticos/2026-11-24-rodada4.md): diagnóstico da rodada 4, inspeção de 2026-11-24
- [`diagnosticos/2026-11-18-plano-rodada3.md`](./diagnosticos/2026-11-18-plano-rodada3.md): plano de trabalho da rodada 3, com os itens ainda abertos
- [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md) e [`diagnosticos/2026-10-27-rodada2.md`](./diagnosticos/2026-10-27-rodada2.md): diagnósticos históricos
