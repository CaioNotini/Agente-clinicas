```
Papel: Índice de entrada único da documentação e registro do estado verificado mais recente.
Entrada: docs/status.md
Relaciona-se com: etapas.md, estudo.md, arquitetura.md, principios.md, decisions/README.md, diagnosticos/2026-11-18-plano-rodada3.md, diagnosticos/2026-11-24-rodada4.md, diagnosticos/2026-11-25-rodada5.md
```

# Status do projeto

Estado verificado em 2026-11-25. O histórico detalhado de cada mudança fica no git log e nos [ADRs](./decisions/README.md).

## Onde estamos

**Etapa 6 concluída. Próxima etapa ativa: 7, classificação, mensagens fixas e auditoria.** As etapas 0 a 6 estão concluídas.

Etapa 6 (concluída), resumo: chamada ao modelo por uma interface única. `LLMClient` e a implementação `AnthropicClient` sobre o SDK `anthropic==2.14.0` (versão `2026-10-21` da API, `max_retries=0`), com o modelo em `LLM_MODEL` (`claude-haiku-5-5`), validado só na criação do cliente. Hierarquia de erros transitório e permanente, com o permanente herdando de `ErroPermanente`. Telemetria de cada chamada no log estruturado, nos eventos `llm_chamada` e `llm_chamada_falhou`, sem prompt, conteúdo nem telefone. Backoff no retry de jobs, `min(base * 2 ** (tentativas - 1), teto)` com `base` de 60 s e `teto` de 1800 s, só no retry e nunca no `dead`. Teste real com o marcador `llm_real`, fora da CI. Decisões em [ADR 0010](./decisions/0010-llmclient.md) e [ADR 0005](./decisions/0005-ordem-por-conversa.md). O processamento ainda não chama o LLM. A ligação com o conteúdo da mensagem entra na etapa 7, com a classificação.

| Etapa  | Estado        |
| ------ | ------------- |
| 0 a 6  | concluídas    |
| 7 a 21 | não iniciadas |

## O que está verificado

Última verificação em 2026-11-25, no banco do Docker local:

- `pytest tests/ -q` = `490 passed`, 1 warning conhecido (TestClient do Starlette), sem o marcador `llm_real`, em 2026-11-25, com o código das tarefas 6.1 a 6.4. Antes, em 2026-11-24, a suíte tinha `448 passed` num ambiente limpo instalado do zero pelo `requirements-dev.txt`, repetido com o SDK `anthropic` 2.14.0 e o FastAPI 0.108.0. As tarefas 6.1 a 6.4 somaram testes novos até os `490`.
- `pytest -m llm_real -v`, rodado pelo desenvolvedor em 2026-11-25 = `4 passed`, 490 deselected. Única execução paga, aprovada na implementação e no teste (regra 22). Não roda na CI.
- O banco local estava em `45ba5d9bc62d` e foi levado ao head `c3d8e5a1f297` com `alembic upgrade head`. O `alembic check` passou.
- Ciclo de migrations (`upgrade head`, `downgrade base`, `upgrade head`) e [`scripts/verificar_pks.sql`](../scripts/verificar_pks.sql): última execução na CI do commit `99cc552`. Os commits da rodada 4 aguardam a CI.
- Setup do zero só pelo [`README.md`](../README.md), num clone limpo, passou em 2026-11-20. A repetição fica com o desenvolvedor, na máquina local dele, e não é pendência do agente.
- pylint, black e isort passam e reprovam a CI quando falham.
- Prova por mutação da etapa 5, à mão e fora da suíte: sem RLS e sem o filtro explícito de tenant, os testes de isolamento do serviço e do handoff falham, o que confirma as duas barreiras. A segunda barreira da verificação de duplicata da fila tem teste próprio, `test_sem_rls_o_filtro_de_tenant_separa_colisao_de_duplicata` em [`test_dedupe_mensagens.py`](../tests/concurrency/test_dedupe_mensagens.py), que roda sem RLS pela conta de administração. Sem o tratamento de `ErroPermanente`, os testes do worker falham.
- Critério de pronto da etapa 0 conferido em 2026-11-25, com o conteúdo de [`pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md) aprovado pelo desenvolvedor como a tarefa 0.3. Os três arquivos de [`fake_clinic/`](./fake_clinic/) têm o cabeçalho de relações. O [`FAQ.md`](./fake_clinic/FAQ.md) tem 15 perguntas, cada uma com categoria (14 `permitido` e 1 `sem_informacao`). A lista de bloqueadas tem 13 perguntas, 8 `clinico_bloqueado` e 5 `urgencia`, com formas indiretas nas perguntas 5 e 8. Os dados são fictícios (telefones `(00) 0000-000x`, CNPJ e CRM zerados, e-mails `.invalid`). Os únicos números reais são o 192 e o 188, de propósito.
- Critério de pronto da etapa 5 conferido: cada função de `app/agenda/regras.py` tem teste unitário com casos de borda, e o handoff gravado aparece no banco pela leitura da conta `app_clinicas`.

O que o código garante hoje, com a decisão de cada ponto:

- Isolamento entre clínicas por RLS, FORCE e policy `isolamento_tenant`, com cobertura conferida pelo catálogo ([ADR 0002](./decisions/0002-contas-de-banco.md)).
- FKs entre tabelas de clínica incluem `tenant_id` ([ADR 0007](./decisions/0007-fks-compostas-por-tenant.md)).
- Mensagens da mesma conversa processadas na ordem de chegada ([ADR 0005](./decisions/0005-ordem-por-conversa.md)) e sem processamento simultâneo (lock por conversa).
- Efeitos de um job confirmados uma vez só, junto com a conclusão do job ([ADR 0008](./decisions/0008-conclusao-atomica-do-job.md)).
- Transições de estado pelo grafo do [ADR 0003](./decisions/0003-grafo-de-transicoes.md).
- Erro permanente (`ConfiguracaoInvalida`, `MisturaDeTenants`) leva o job a `dead` na primeira falha, com log estruturado de erro. O texto de exceções não vai ao paciente (seções 7 e 8.1 da [arquitetura](./arquitetura.md)).
- Senhas das roles aplicadas por script, sem passo manual ([ADR 0006](./decisions/0006-provisionamento-de-roles.md)).

## Decisões recentes

- 2026-11-25, etapa 0: existe uma única mensagem fixa de `urgencia`, que cobre todo risco imediato à vida, inclusive o pensamento de autolesão. Ela orienta o 192 ou o pronto-socorro de forma incondicional e cita o CVV (188), sem subcategoria de urgência. Perguntas administrativas nunca são `clinico_bloqueado`. Sem a informação na base, o agente oferece handoff ou seguir no automático. Regras na seção 8.3 da [arquitetura](./arquitetura.md#83-escopo-clínico).

- 2026-11-25, C6: a coluna `conversas.historico` foi removida (migration `a5587f532a88`, com downgrade que a recria). Ela nunca foi lida nem escrita. O contexto do LLM da etapa 7 virá das últimas mensagens do contato, direto de `mensagens` (`contato_telefone`, `conteudo`, `direcao`, `criada_em` por tenant). Manter `historico` duplicaria o dado, com risco de divergência e mais um ponto a apagar na exclusão do titular (LGPD). Um resumo de conversas longas, se preciso na etapa 7, será coluna nova com contrato e ADR.

## Pendências

**Previstas para etapas futuras**

- 7.3: `MENSAGEM_URGENCIA` em [`fixas.py`](../app/mensagens/fixas.py) ainda não cita o CVV (188), decidido na seção 8.3 da [arquitetura](./arquitetura.md#83-escopo-clínico).
- 8: o [`FAQ.md`](./fake_clinic/FAQ.md) não tem mais entradas clínicas. O critério "trechos marcados como bloqueado nunca são retornados" vai precisar de um trecho clínico de teste criado na própria etapa 8.

- 13: não abrir handoff novo se já houver um aberto para a mesma conversa, motivo e agendamento. Na 5.4 cada pedido grava uma linha.
- 13: na remarcação fora da janela, o novo horário não é validado antes de abrir o handoff.
- 13: `handoffs` mistura `responder_ate` (timestamptz) com `criada_em`, `notificado_em`, `assumido_em` e `devolvido_em` (timestamp sem fuso). Resolver antes de comparar o prazo com esses instantes (C10 da rodada 4).
- 14: validar o nome do fuso ao gravar a configuração da clínica.
- 14: com entradas fora da fila, um `23P01` contra agendamento do próprio contato, sobreposto e com outro início, dá `HorarioIndisponivel` em vez de `AgendamentoDuplicado`, tanto na criação quanto na remarcação. Na remarcação o antigo continua ativo, porque o erro sobe pelo SAVEPOINT. Faz parte da ressalva sobre entradas fora da fila na seção 7 da [arquitetura](./arquitetura.md#7-modelo-de-dados).
- 7: o `mensagem_id` passado ao serviço deve vir do job. A FK garante a mesma clínica, mas não o mesmo contato.
- LGPD: a exclusão do titular que apague agendamentos precisa tratar antes os handoffs que apontam para eles (FK `NO ACTION`).
- Outros erros permanentes, como o payload sem `contato_telefone`, ainda consomem as 3 tentativas.
- `55P03` (lock_timeout de 5 s esperando outra transação na verificação da constraint de conflito) sobe sem tratamento próprio, e o job tenta de novo.
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

**Ambiguidades de documentação**

- [`estudo.md`](./estudo.md), seção 4, cita um "endpoint de chat de teste" que nenhuma etapa prevê.
- A seção 7 da [arquitetura](./arquitetura.md) diz que `log_auditoria` guarda categoria e texto original, e a tabela tem `acao`, `descricao` e `dados`.

## Links

- [`etapas.md`](./etapas.md): plano de construção, etapas 0 a 21
- [`estudo.md`](./estudo.md): escopo, premissas e orçamento do estudo
- [`arquitetura.md`](./arquitetura.md): decisões técnicas, modelo de dados e questões em aberto
- [`principios.md`](./principios.md): princípios e como são verificados
- [`decisions/README.md`](./decisions/README.md): ADRs 0001 a 0010
- [`fake_clinic/clinica.md`](./fake_clinic/clinica.md), [`fake_clinic/FAQ.md`](./fake_clinic/FAQ.md) e [`fake_clinic/pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md): base fictícia (clínica com equipe e recepção)
- [`fake_clinic/consultorio_solo.md`](./fake_clinic/consultorio_solo.md): segundo tenant fictício, consultório de um profissional só, sem recepção, para testar as regras da etapa 5 nos dois cenários
- [`diagnosticos/2026-11-25-rodada5.md`](./diagnosticos/2026-11-25-rodada5.md): diagnóstico da rodada 5, inspeção de 2026-11-25
- [`diagnosticos/2026-11-24-rodada4.md`](./diagnosticos/2026-11-24-rodada4.md): diagnóstico da rodada 4, inspeção de 2026-11-24
- [`diagnosticos/2026-11-18-plano-rodada3.md`](./diagnosticos/2026-11-18-plano-rodada3.md): plano de trabalho da rodada 3, com os itens ainda abertos
- [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md) e [`diagnosticos/2026-10-27-rodada2.md`](./diagnosticos/2026-10-27-rodada2.md): diagnósticos históricos
