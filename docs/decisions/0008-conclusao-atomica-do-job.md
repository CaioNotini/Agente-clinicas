```
Papel: registra como o processamento de um job e a sua conclusão ficam atômicos, para um job não produzir efeito duas vezes.
Entrada: docs/status.md
Relaciona-se com: 0002-contas-de-banco.md, 0005-ordem-por-conversa.md, ../arquitetura.md (seção 8.1), ../etapas.md (etapas 5 e 17), ../../app/jobs/worker.py, ../../app/core/processamento.py
```

# 0008: Conclusão atômica do job com os efeitos do processamento

## Contexto

O item A3 do [plano de 2026-11-18](../diagnosticos/2026-11-18-plano-rodada3.md) aponta que o processamento de um job e a sua conclusão são transações separadas. Hoje, em [`worker.py`](../../app/jobs/worker.py), `processar_um` segue estes passos:

1. Captura o job e o marca `processing`, na transação 1, com `worker_jobs`.
2. Chama o processamento. [`processar_mensagem`](../../app/core/processamento.py) grava os efeitos de clínica numa sessão `app_clinicas` própria e faz o commit dela, na transação 2.
3. Marca o job `done` com `finalizar_job`, na transação 3, com `worker_jobs`.

Há três janelas em que o efeito se repete:

- **Queda entre os passos 2 e 3.** O efeito foi confirmado e o job ficou `processing`. Depois de `LIMITE_LOCK_SEGUNDOS` (300 s), o job é recapturado e processado de novo.
- **Erro em `finalizar_job`.** O laço sobrevive ao erro de banco (item B4), mas o job fica `processing` e é recapturado, com o mesmo resultado.
- **Processamento acima de 300 s.** Outro worker recaptura o job enquanto o primeiro ainda processa, e os dois confirmam efeitos. O filtro `locked_by` de `finalizar_job` só impede o primeiro de marcar `done`, não desfaz o que ele já gravou.

Hoje isso é inofensivo, porque o processamento só garante a conversa, com `ON CONFLICT DO NOTHING`. Na tarefa 5.3 o processamento passa a criar e cancelar agendamentos, e um efeito repetido vira um agendamento duplicado ou um cancelamento indevido. Por isso o item precisa estar resolvido antes da 5.3.

## Alternativas consideradas

- **Concluir o job na mesma transação dos efeitos.** O processamento grava os efeitos e marca o job `done` na mesma sessão `app_clinicas`, com a condição de que o job ainda pertença a este worker. Escolhida.
- **Tabela de execuções por job.** Uma tabela `(tenant_id, job_id)` recebe uma linha na mesma transação dos efeitos. Um reprocessamento encontra a linha e pula os efeitos. Descartada como mecanismo principal: resolve a repetição, mas exige tabela nova com RLS, policy e testes, e deixa o job em `processing` até a recaptura. Também não impede dois workers processando ao mesmo tempo depois de uma recaptura. Os dois passam pela verificação antes de qualquer um confirmar, e a disputa só se resolve pela chave única, com erro para um deles.
- **Limite de tempo de processamento abaixo de `LIMITE_LOCK_SEGUNDOS`.** Por exemplo, `statement_timeout` ou um prazo no worker. Descartada como solução: evita a recaptura de um job ainda vivo, mas não cobre a queda entre os passos 2 e 3 nem o erro em `finalizar_job`. Fica como complemento possível.
- **Renovar `locked_at` periodicamente (heartbeat).** Descartada pelo mesmo motivo do limite de tempo: reduz recapturas indevidas, mas não fecha a janela entre o efeito e a conclusão.
- **Tornar cada efeito idempotente por conta própria.** Por exemplo, uma chave única do job em `agendamentos`. Descartada como regra geral: depende de cada funcionalidade nova lembrar da sua chave. Pode existir como segunda barreira em efeitos específicos.

## Decisão

O processamento de um job conclui o job na mesma transação `app_clinicas` em que grava os efeitos de clínica. Dentro dessa transação, depois dos efeitos e antes do commit, roda:

```sql
UPDATE jobs SET status = 'done', last_error = NULL
WHERE id = :id AND locked_by = :worker AND status = 'processing'
```

Se nenhuma linha for atualizada, o job foi recapturado por outro worker. A transação inteira é desfeita, efeitos incluídos.

A transação de captura, na conta `worker_jobs`, é confirmada antes de o processamento começar. Enquanto ela estiver aberta, ela segura o `FOR UPDATE` na linha do job. O UPDATE da sessão `app_clinicas` esperaria por ela, e o worker travaria a si mesmo, porque a captura só seria confirmada depois do processamento. Por isso `reivindicar_job` confirma a própria transação antes de devolver o job, e nenhuma transação `worker_jobs` que fica aberta durante o processamento trava a linha do job.

## Justificativa

O efeito e a conclusão passam a ser confirmados juntos ou desfeitos juntos. Em cada janela do Contexto:

- **Queda antes do commit:** nada foi confirmado, e a recaptura reprocessa sem duplicar.
- **Queda depois do commit:** o job já está `done` e não é recapturado.
- **Recaptura de um job vivo:** só o worker que ainda é dono do job consegue confirmar. O outro desfaz os próprios efeitos.

A regra fica numa única função, usada por todo processamento, sem tabela nova.

## Consequências

**Contas e grants.**

- A sessão `app_clinicas` passa a atualizar a linha do próprio job. O grant de UPDATE em `jobs` já existe, e a policy `isolamento_tenant` restringe o UPDATE ao tenant do job, que é o `app.tenant_id` da sessão. Nenhum grant, role ou policy muda.
- O [ADR 0002](./0002-contas-de-banco.md) diz que o worker usa `worker_jobs` só para a fila e escreve dados de clínica por `app_clinicas`. Isso continua valendo. Muda que a conclusão bem-sucedida do job passa a ser feita pela sessão `app_clinicas`. O ADR 0002 ganha uma revisão citando este ADR.
- O item A4 do plano propõe revisar o UPDATE de `app_clinicas` em `jobs`. Com esta decisão, esse UPDATE precisa continuar, restrito à conclusão do próprio job.

**Código.**

- A captura, o caminho de falha (`pending` ou `dead`) e o tipo não suportado continuam com `worker_jobs`, como hoje.
- Depois do processamento, `processar_um` só marca `done` um job que ainda esteja em `processing` com este worker. Um processamento que concluiu o job na própria transação já o deixou `done`, então esse passo não altera nada. O passo continua existindo para processamentos sem efeito de clínica, como o vazio e os usados nos testes do worker. Todo processamento que grava efeito de clínica precisa concluir o job na própria transação.
- `finalizar_job` passa a exigir `status = 'processing'`, para nunca sobrescrever um job já concluído.
- A conclusão roda na sessão de `conversa_travada`, que já define `lock_timeout` de 5 s. Se a linha do job estiver travada por engano, o UPDATE falha com erro de lock em vez de esperar para sempre.
- Uma função única, por exemplo `concluir_job(session, job, worker_id)`, roda o UPDATE e levanta um erro próprio quando o job não pertence mais ao worker. `processar_mensagem` a chama dentro de `conversa_travada`, antes de sair do bloco.
- O erro de job perdido não deve virar falha do job. O dono atual é o outro worker, e o primeiro só desfaz a transação e segue.
- A assinatura `processamento(conexao, job)` precisa receber o `worker_id`, ou o `JobCapturado` passa a carregá-lo.

**Limites.**

- Vale para efeitos gravados no banco. Um efeito externo, como o envio de WhatsApp da etapa 17, não entra numa transação do Postgres. Ele deve sair do processamento como um job novo, gravado na mesma transação (padrão outbox), e o envio desse job precisa de idempotência própria no provedor. Isso fica para a etapa 17.
- A recaptura de um job vivo continua possível depois de 300 s. Ela passa a desperdiçar trabalho, mas não duplica efeito. O limite de tempo ou o heartbeat podem entrar depois, se a medição mostrar recapturas.
- O lock da conversa serializa os dois processamentos da mesma conversa. O segundo espera o primeiro confirmar ou desfazer, e então encontra o job já `done` ou com outro dono.

**Testes que provam o problema e a correção.** O efeito de teste é uma linha em `log_auditoria`, gravada por `app_clinicas`.

- Queda simulada entre o efeito e a conclusão: forçar erro na conclusão pelo `worker_jobs` e recapturar com limite de 0 s. Hoje o efeito aparece duas vezes. Depois, uma vez.
- Dois workers com processamento mais lento que o limite de recaptura: hoje os dois efeitos são confirmados. Depois, um só, e o job termina `done`.
- O worker que perdeu o job desfaz os efeitos e não marca `done`.
- Controles: o caminho feliz conclui o job com um efeito, e uma falha de processamento continua levando o job a `pending` e depois a `dead`, sem efeito confirmado.
- Captura confirmada: durante o processamento, outra conexão consegue `SELECT ... FOR UPDATE NOWAIT` na linha do job e a vê em `processing`. Se a captura continuasse aberta, esse teste falharia com `55P03`.
- Controle do travamento: com uma transação `worker_jobs` aberta segurando o `FOR UPDATE` da linha do job, a conclusão pela sessão `app_clinicas` falha por `lock_timeout`. É o travamento que o worker sofreria se a captura não fosse confirmada antes.
- O teste de ordem por conversa do [ADR 0005](./0005-ordem-por-conversa.md) continua passando.

## Status

Aceita em 2026-11-18, com o ajuste da captura confirmada antes do processamento.
