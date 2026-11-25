```
Papel: registra como o worker garante que mensagens da mesma conversa são processadas na ordem de chegada.
Entrada: docs/status.md
Relaciona-se com: ../etapas.md (etapa 4), ../arquitetura.md (seção 8.1), 0002-contas-de-banco.md, 0003-grafo-de-transicoes.md, ../../app/jobs/worker.py, ../../app/jobs/queue.py, ../../app/core/conversas.py
```

# 0005: Ordem de processamento por conversa

## Contexto

O critério de pronto da etapa 4 em [`etapas.md`](../etapas.md) exige que mensagens seguidas da mesma conversa não sejam processadas fora de ordem nem em duplicidade. Em 2026-11-15 o critério foi mantido, e a garantia de ordem ficou como pendência em [`status.md`](../status.md).

Hoje o worker ([`worker.py`](../../app/jobs/worker.py)) captura qualquer job elegível da fila, por `run_at, id`, com `SKIP LOCKED`. Ele não olha para a conversa. A serialização vem só do lock por conversa ([`conversas.py`](../../app/core/conversas.py)), que impede duas mensagens da mesma conversa rodando ao mesmo tempo, mas não fixa a ordem. Casos confirmados pela leitura do código:

- **Falha da mensagem 1.** A mensagem 1 falha e volta para `pending`. Enquanto isso, outro worker já capturou a mensagem 2, que pega o lock e é processada antes da nova tentativa da 1.
- **Processamento lento.** Com dois workers, a mensagem 2 é capturada enquanto a 1 ainda processa e fica esperando o lock da conversa. Se a espera passa do `lock_timeout` de 5 s, a 2 falha, gasta uma tentativa e volta para a fila. Depois de 3 tentativas vai para `dead`. Uma mensagem 3 capturada nesse intervalo pode ser processada antes da 2.

A ordem importa para o motor de estados do [ADR 0003](./0003-grafo-de-transicoes.md). Um "sim" processado antes de "quero remarcar" leva a conversa a uma transição errada.

## Alternativas consideradas

- **Backoff sem gastar tentativa.** No erro de `lock_timeout`, o job volta para `pending` com `run_at` adiado e sem incrementar `attempts`. Descartada: evita que a mensagem 2 vá para `dead` por esperar o lock, mas não garante a ordem. Quando a mensagem 1 falha e volta para a fila, a 2 pode pegar o lock primeiro. A ordem continuaria dependendo de tempo.
- **Mudar o critério de pronto.** Aceitar só a serialização, sem garantia de ordem. Descartada: o critério foi mantido em 2026-11-15, e a ordem é necessária para o motor de estados.
- **Chave de ordem lida do payload.** Filtrar por `payload->>'contato_telefone'` sem coluna nova. Descartada: o payload é livre e do tipo `json`, a regra dependeria do formato de cada tipo de job, e o índice teria de ser sobre uma expressão.
- **Distribuir conversas entre workers fixos por hash.** Descartada: exige um número fixo de workers e redistribuição quando um deles cai, o que não cabe no estudo.

## Decisão

O worker só captura um job se não existir outro job da mesma conversa, com status `pending` ou `processing` e `id` menor. A conversa é identificada por `(tenant_id, contato_telefone)`, a mesma chave do lock por conversa. A ordem de chegada é a ordem do `id` do job.

## Justificativa

A regra fica no banco, dentro da mesma consulta de captura que já usa `SKIP LOCKED`. Não depende de tempo, de backoff nem de quantos workers estão no ar. Um job seguinte só fica elegível depois que o anterior termina em `done` ou `dead`, então não há como dois jobs da mesma conversa rodarem ao mesmo tempo nem fora de ordem. Os jobs bloqueados não são capturados, então não gastam tentativas nem esperam pelo lock.

**Segurança sob concorrência.** A verificação é um `NOT EXISTS` sobre `jobs`, na mesma consulta do `FOR UPDATE SKIP LOCKED`. O `FOR UPDATE` trava só as linhas da consulta principal. O `NOT EXISTS` só lê, sem travar nem pular nada.

- Se o worker A travou a mensagem 1 e ainda não fez o commit da captura, o worker B pula a 1 por causa do `SKIP LOCKED`. Mas o `NOT EXISTS` de B ainda enxerga a 1 como `pending`, que é a última versão confirmada. Então a 2 continua bloqueada.
- Depois do commit de A, B enxerga a 1 como `processing`, que também bloqueia.
- O status de um job só sai de `pending` ou `processing` para `done` ou `dead`, que são finais. Uma falha devolve o job para `pending`, que continua bloqueando. Um snapshot antigo pode mostrar a 1 como `pending` ou `processing` quando ela já terminou. Isso só atrasa a captura da 2 até a próxima volta do laço. Nunca mostra a 1 como terminada antes do tempo, então nunca antecipa a captura.

## Consequências

**Schema de `jobs`.**

- Nova coluna `contato_telefone`, `varchar(20)`, aceitando NULL. É preenchida por `gravar_e_enfileirar` em [`queue.py`](../../app/jobs/queue.py) para jobs `PROCESS_INBOUND_MESSAGE`. Jobs sem conversa, como os lembretes futuros, ficam com NULL e não entram na regra de ordem.
- CHECK `type <> 'PROCESS_INBOUND_MESSAGE' OR contato_telefone IS NOT NULL`. Um job de mensagem sem conversa escaparia da regra de ordem em silêncio.
- Novo índice parcial `(tenant_id, contato_telefone, id) WHERE status IN ('pending', 'processing')`, para a verificação do job anterior.
- A tabela continua coberta pela policy `isolamento_tenant` que já existe, sem mudança de policy, de grants nem de roles. Os grants atuais são por tabela e cobrem a coluna nova.
- Na mesma migration entram as restrições do item A5 do plano. Sem elas, um job anterior com `attempts` ou `run_at` nulo nunca seria capturado e bloquearia a conversa para sempre.
  - `jobs`: NOT NULL e `server_default` em `status` (`pending`), `run_at` (`now()`), `attempts` (0) e `max_attempts` (3). CHECK de `status` com `pending`, `processing`, `done` e `dead`.
  - `conversas`: NOT NULL e `server_default` em `estado_conversa` (`idle`) e `human_mode` (false). CHECK de `estado_conversa` com os cinco estados do [ADR 0003](./0003-grafo-de-transicoes.md).
  - `mensagens`: CHECK de `direcao` com `entrada` e `saida`. A coluna continua aceitando NULL.

**Migration.**

- Ordem do upgrade: primeiro a coluna nova, depois o preenchimento dos dados existentes, e só então os NOT NULL, os CHECKs e o índice.
- Preenchimento:
  - `jobs.contato_telefone` recebe `payload->>'contato_telefone'`.
  - `jobs.status` nulo vira `pending`, `run_at` nulo vira `criada_em` ou `now()`, `attempts` nulo vira 0 e `max_attempts` nulo vira 3.
  - `conversas.estado_conversa` nulo vira `idle` e `human_mode` nulo vira false.
  - `mensagens.direcao` com `in` vira `entrada` e com `out` vira `saida`. O valor `in` vinha dos seeds dos testes de isolamento, que passam a usar `entrada`.
- Dados que não têm conversão segura fazem a migration parar com erro explícito, sem apagar nada. São eles: um job `PROCESS_INBOUND_MESSAGE` sem `contato_telefone` no payload, e um status, estado ou direção fora dos valores conhecidos. A correção desses dados fica a cargo do desenvolvedor.
- O downgrade desfaz o schema por completo, na ordem inversa: índice, CHECKs, NOT NULL, `server_default` e a coluna. Ele não desfaz o preenchimento dos dados, porque não há como saber quais valores eram nulos ou `in` antes. Esses valores continuam válidos no schema antigo.

**Falha repetida de uma mensagem.**

- A mensagem que falha volta para `pending` e é tentada de novo até `max_attempts`, que hoje é 3. Enquanto isso, as mensagens seguintes da conversa esperam na fila.
- Ao chegar em `dead`, ela deixa de bloquear. As seguintes são processadas na ordem.
- O `dead` não bloqueia para sempre de propósito. Uma mensagem com defeito permanente pararia a conversa sem prazo.
- A mensagem morta fica registrada em `jobs`, com `status = 'dead'` e `last_error`. O aviso à recepção sobre mensagens mortas fica para o handoff da etapa 13.

**Conversa depois de uma mensagem morta.** Liberar as seguintes recria, de forma controlada, o problema do Contexto: a mensagem 2 é processada sem que a 1 tenha sido. Na etapa 4 o processamento só garante a conversa, então não há efeito visível. A partir da etapa 9, um "sim" pode levar a uma transição sem o "quero remarcar" que veio antes. Foram avaliadas duas opções. **Escolhida em 2026-11-18: opção 2.**

- **Opção 1, mínima: escalar a conversa. Não escolhida.** Quando um job `PROCESS_INBOUND_MESSAGE` vai para `dead`, o worker marca a conversa como `escalada` e `human_mode = true`, por uma sessão `app_clinicas` com RLS, como no [ADR 0002](./0002-contas-de-banco.md). As mensagens seguintes continuam sendo processadas, mas a conversa já está com a recepção. A partir da etapa 7 o agente não responde em `escalada`.
  - Custo: uma escrita de conversa no caminho de `dead`, mais um teste.
  - O [ADR 0003](./0003-grafo-de-transicoes.md) não permite `encerrada -> escalada` nem `escalada -> escalada`. Em `escalada` não há nada a fazer. Em `encerrada`, a escalada só é possível se o grafo ganhar essa aresta, o que exige revisar o ADR 0003. A alternativa é deixar a conversa encerrada como está.
  - Se a escrita da escalada falhar, o job continua `dead` e o erro fica em `last_error`.
- **Opção 2, escolhida: risco aceito até a etapa 9.** Nada muda na conversa. A mensagem morta fica só em `jobs`. O prazo é a primeira etapa em que o processamento passa a alterar o estado da conversa. Pela ordem de [`etapas.md`](../etapas.md), é a etapa 9, tarefa 9.2, que liga as ferramentas ao motor de estados. A etapa 7 só classifica e audita, a 5.4 grava o handoff sem mudar o estado, e a 13 vem depois da 9. A conduta precisa estar decidida e implementada antes de a etapa 9 fechar. O registro está em [`status.md`](../status.md).
- O tempo máximo de bloqueio é de `max_attempts` processamentos da mensagem que falha. Se o worker morrer durante o processamento, soma-se o limite de órfão `LIMITE_LOCK_SEGUNDOS`, de 300 s, até o job ser recapturado ou marcado `dead` pela varredura.
- Desde a tarefa 6.4 as novas tentativas têm backoff. Uma falha transitória adia o `run_at` do job (`atraso_backoff` em [`worker.py`](../../app/jobs/worker.py)), mas um `run_at` futuro do job anterior continua bloqueando os seguintes, porque a regra de ordem olha o status e não o `run_at`. A conversa inteira espera durante o backoff.

**Limites da garantia.**

- A ordem vale entre jobs já gravados. O `id` é gerado no INSERT, e duas transações de enfileiramento concorrentes podem gravar em ordem diferente da ordem dos ids. Nesse caso, o job de `id` menor gravado por último pode ser processado depois do maior. O CLI grava de forma sequencial, então isso não ocorre no estudo. O webhook da etapa 17 precisa revisitar este ponto, com o horário da mensagem enviado pela Meta.
- A recaptura de um job órfão depois de 300 s continua possível, como hoje. O processamento repetido por isso é o item A3 do plano, fora desta decisão.

**Lock por conversa.**

- O lock com `FOR UPDATE` continua, como segunda barreira contra escritas concorrentes na mesma conversa, por exemplo do painel futuro.
- Entre jobs `PROCESS_INBOUND_MESSAGE` da mesma conversa ele deixa de ser disputado, então o `lock_timeout` passa a atingir só escritores de fora da fila.

**Worker.**

- O laço `rodar()` passa a tratar erros de banco sem encerrar o processo, conforme o item B4 do plano. Sem isso, um worker que cai com um job em `processing` bloqueia a conversa até o limite de órfão.

**Testes que provam a garantia.**

- Dois workers, a mesma conversa e um processamento lento: a mensagem 2 não é capturada enquanto a 1 processa, e não gasta tentativas.
- Falha da mensagem 1 seguida das mensagens 2 e 3: a ordem de processamento registrada é 1, 1, 1 (até `dead`), 2, 3. Ou, se a 1 falhar só na primeira tentativa: 1, 1, 2, 3.
- Uma conversa bloqueada não bloqueia outra conversa, nem a mesma conversa de outra clínica.
- Jobs sem conversa (`contato_telefone` nulo) não bloqueiam jobs de conversa nem são bloqueados por eles.
- As restrições novas rejeitam um job de mensagem sem conversa, um status, estado ou direção inválidos, e aplicam os defaults quando a coluna é omitida.
- Controle: sem a cláusula de bloqueio na captura, os testes de ordem falham.

## Status

Aceita em 2026-11-18. Para a conversa depois de uma mensagem morta, a opção 2 foi escolhida em 2026-11-18, com prazo na etapa 9.
