```
Papel: Índice de entrada único da documentação e registro do estado verificado mais recente.
Entrada: docs/status.md
Relaciona-se com: etapas.md, estudo.md, arquitetura.md, principios.md, decisions/README.md, diagnosticos/2026-11-18-plano-rodada3.md, diagnosticos/2026-11-24-rodada4.md
```

# Status do projeto

Estado verificado em 2026-11-24. O histórico detalhado de cada mudança fica no git log e nos [ADRs](./decisions/README.md).

## Onde estamos

**Etapa ativa: 6, LLMClient com API direta.** A etapa 5 está concluída.

- Feitas: 5.5 (tabela `agendamentos`, conflito pelo [ADR 0004](./decisions/0004-conflito-de-horario.md)), 5.1 (`AgendaProvider` e `AgendaPropria`) 5.2 (regras de antecedência, expediente, conflito, duplicidade e janela de cancelamento em `app/agenda/regras.py`, descritas na seção 7 da [arquitetura](./arquitetura.md) e testadas nos dois cenários) 5.3 (serviço de agendamento em `app/agenda/servico.py`: criar, remarcar, cancelar e disponibilidade, com SAVEPOINT, `23P01` traduzido, nova tentativa no `40P01`, conclusão atômica do job e testes de isolamento da carga) e 5.4 (handoff gravado em `app/handoff/abertura.py`, sem mudar o estado da conversa, pela revisão do [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md)).
- As decisões do [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md) (Q-21 a Q-24) estão implementadas como blocos reutilizáveis: schema novo, conversão de fuso (`app/core/fuso.py`), regras puras de duração e cancelamento (`app/agenda/regras.py`) e mensagens fixas (`app/mensagens/fixas.py`).
- O serviço ainda não é chamado pelo processamento das mensagens. A ligação com o conteúdo da mensagem entra na etapa 7, com a classificação.
- A 5.5 e a 5.1 foram feitas antes de a etapa 4 fechar, contra a regra de dependência de [`etapas.md`](./etapas.md). O desvio foi aceito pelo desenvolvedor.

| Etapa  | Estado                                            |
| ------ | ------------------------------------------------- |
| 0      | aberta, falta o conteúdo de `pergs_bloqueadas.md` |
| 1 a 5  | concluídas                                        |
| 6      | ativa                                             |
| 7 a 21 | não iniciadas                                     |

## O que está verificado

Última verificação em 2026-11-24, no banco do Docker local:

- `pytest tests/ -q`: `448 passed`, no `.venv` e num ambiente limpo instalado do zero pelo `requirements-dev.txt`, depois da limpeza de dependências da rodada 4.
- O banco local estava em `45ba5d9bc62d` e foi levado ao head `c3d8e5a1f297` com `alembic upgrade head`. O `alembic check` passou.
- Ciclo de migrations (`upgrade head`, `downgrade base`, `upgrade head`) e [`scripts/verificar_pks.sql`](../scripts/verificar_pks.sql): última execução na CI do commit `99cc552`. Os commits da rodada 4 aguardam a CI.
- Setup do zero só pelo [`README.md`](../README.md), num clone limpo, passou em 2026-11-20. A repetição de 2026-11-24 parou no passo 4. O hook `block_env` barra a cópia do arquivo de exemplo, e em seguida o Docker Desktop parou de responder. Pendente.
- pylint, black e isort passam e reprovam a CI quando falham.
- Prova por mutação dos testes de isolamento do serviço (`tests/isolation/test_servico_isolamento.py`): rodando sem RLS e sem o filtro explícito de tenant, os 7 testes que provam isolamento falham. A mutação foi rodada à mão e não faz parte da suíte. A segunda barreira (filtro explícito) da verificação de duplicata da fila tem teste próprio, `test_sem_rls_o_filtro_de_tenant_separa_colisao_de_duplicata` em [`test_dedupe_mensagens.py`](../tests/concurrency/test_dedupe_mensagens.py), que roda sem RLS pela conta de administração. A do serviço e a de `concluir_job` continuam sem teste próprio, porque com o RLS ativo elas não mudam o resultado.
- Prova por mutação da 5.4, também à mão: sem RLS e sem o filtro da abertura, os 2 testes de isolamento do handoff falham. Sem o tratamento de `ErroPermanente`, os testes do worker falham. Com a FK de `mensagem_id` sem a lista de colunas no `SET NULL`, a exclusão da mensagem falha por NOT NULL em `tenant_id`.
- Critério de pronto da etapa 5: cada função de `app/agenda/regras.py` tem teste unitário com casos de borda (no limite, 1 segundo abaixo, coluna nula, adjacentes, último dia permitido), e `test_handoff_gravado_aparece_no_banco_com_destino_previsto` lê o handoff gravado pela conta `app_clinicas`.

O que o código garante hoje, com a decisão de cada ponto:

- Isolamento entre clínicas por RLS, FORCE e policy `isolamento_tenant`, com cobertura conferida pelo catálogo ([ADR 0002](./decisions/0002-contas-de-banco.md)).
- FKs entre tabelas de clínica incluem `tenant_id` ([ADR 0007](./decisions/0007-fks-compostas-por-tenant.md)).
- Mensagens da mesma conversa processadas na ordem de chegada ([ADR 0005](./decisions/0005-ordem-por-conversa.md)) e sem processamento simultâneo (lock por conversa).
- Efeitos de um job confirmados uma vez só, junto com a conclusão do job ([ADR 0008](./decisions/0008-conclusao-atomica-do-job.md)).
- Transições de estado pelo grafo do [ADR 0003](./decisions/0003-grafo-de-transicoes.md).
- Erro permanente (`ConfiguracaoInvalida`, `MisturaDeTenants`) leva o job a `dead` na primeira falha, com log estruturado de erro. O texto de exceções não vai ao paciente (seções 7 e 8.1 da [arquitetura](./arquitetura.md)).
- Senhas das roles aplicadas por script, sem passo manual ([ADR 0006](./decisions/0006-provisionamento-de-roles.md)).

## Pendências

**Decisões recentes**

- 2026-11-24, item C7 da [rodada 4](./diagnosticos/2026-11-24-rodada4.md): na remarcação, um novo início que coincide com outro agendamento ativo do mesmo contato levanta `AgendamentoDuplicado`, e o antigo continua ativo. A criação comum continua devolvendo o existente no pedido repetido. Registro na seção 7 da [arquitetura](./arquitetura.md).
- 2026-11-24, tarefa 5.4: `notificado_para` e `notificado_canal` gravam o destino previsto, e `notificado_em` confirma o envio. `handoffs` ganha `texto_paciente`, `responder_ate`, `agendamento_id` e `mensagem_id`, com FKs compostas e `ON DELETE SET NULL (mensagem_id)` para a exclusão do titular. `ConfiguracaoInvalida` vira handoff `configuracao_invalida`. Registro na revisão do [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md). A conduta depois de mensagem morta não se aplica à 5.4, porque ela não muda o estado da conversa, e o prazo continua na etapa 9.
- 2026-11-23, tarefa 5.3: a ordem das regras passa a ser antecedência, expediente, duplicidade e conflito. O contato que pede um horário sobreposto ao que ele já tem recebe `AgendamentoDuplicado`, mesmo com o mesmo profissional. Registro na seção 7 da [arquitetura](./arquitetura.md).
- 2026-11-23, tarefa 5.3: o pedido repetido (mesmo profissional e início) devolve o agendamento existente, na verificação prévia e no `23P01`. O provider responde a disponibilidade só por expediente e ocupação, e a antecedência é aplicada pelo serviço. O passo da disponibilidade é a duração a partir do início da faixa, sem horários quebrados. Remarcar fora da janela segue a regra de cancelamento do antigo. Registro na seção 7 da [arquitetura](./arquitetura.md) e no [ADR 0004](./decisions/0004-conflito-de-horario.md).
- 2026-11-23, tarefa 5.2: duplicidade é o mesmo contato com agendamento ativo sobreposto, com qualquer profissional, sem constraint, porque a ordem por conversa serializa os pedidos do mesmo contato (com a ressalva para entradas futuras fora da fila). Coluna nula em `regras_agendamento` desliga a regra, e cadastro ausente é `ConfiguracaoInvalida`, fora de `RegraViolada`. A disponibilidade (C3) entra na 5.3. Registro na seção 7 da [arquitetura](./arquitetura.md).
- Q-21 a Q-24 da seção 13 da [arquitetura](./arquitetura.md) resolvidas pelo [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md): duração por profissional, fuso por clínica, política de cancelamento fora da janela e registro de quem foi notificado no handoff. Consultórios de um profissional só passam a ser previstos, sem presumir recepção.

**Previstas para etapas futuras**

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
- 12: índices das colunas filhas das FKs, índice parcial da fila e retenção de jobs (C1 e C5).
- 12: teste de UPDATE que move uma linha própria para outra clínica (`SET tenant_id`), recusado pelo WITH CHECK da policy (C9 da rodada 4).
- 6: destino de `conversas.historico` (C6).
- 17: derivar o `tenant_id` do número de destino no webhook (A7), e envio de WhatsApp como job novo, com idempotência no provedor (ADR 0008).
- 15: `ON DELETE SET NULL (mensagem_id)` exige Postgres 15 ou mais. Conferir a versão do Supabase na tarefa 15.2 (C11 da rodada 4).

**Ambiguidades de documentação**

- [`FAQ.md`](./fake_clinic/FAQ.md) cita [`pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md) como fonte de duas perguntas administrativas, e esse arquivo só tem perguntas clínicas e de urgência.
- [`estudo.md`](./estudo.md), seção 4, cita um "endpoint de chat de teste" que nenhuma etapa prevê.
- A seção 7 da [arquitetura](./arquitetura.md) diz que `log_auditoria` guarda categoria e texto original, e a tabela tem `acao`, `descricao` e `dados`.

## Links

- [`etapas.md`](./etapas.md): plano de construção, etapas 0 a 21
- [`estudo.md`](./estudo.md): escopo, premissas e orçamento do estudo
- [`arquitetura.md`](./arquitetura.md): decisões técnicas, modelo de dados e questões em aberto
- [`principios.md`](./principios.md): princípios e como são verificados
- [`decisions/README.md`](./decisions/README.md): ADRs 0001 a 0009
- [`fake_clinic/clinica.md`](./fake_clinic/clinica.md), [`fake_clinic/FAQ.md`](./fake_clinic/FAQ.md) e [`fake_clinic/pergs_bloqueadas.md`](./fake_clinic/pergs_bloqueadas.md): base fictícia (clínica com equipe e recepção)
- [`fake_clinic/consultorio_solo.md`](./fake_clinic/consultorio_solo.md): segundo tenant fictício, consultório de um profissional só, sem recepção, para testar as regras da etapa 5 nos dois cenários
- [`diagnosticos/2026-11-24-rodada4.md`](./diagnosticos/2026-11-24-rodada4.md): diagnóstico da rodada 4, inspeção de 2026-11-24
- [`diagnosticos/2026-11-18-plano-rodada3.md`](./diagnosticos/2026-11-18-plano-rodada3.md): plano de trabalho da rodada 3, com os itens ainda abertos
- [`diagnosticos/2026-10-13-rodada1.md`](./diagnosticos/2026-10-13-rodada1.md) e [`diagnosticos/2026-10-27-rodada2.md`](./diagnosticos/2026-10-27-rodada2.md): diagnósticos históricos
