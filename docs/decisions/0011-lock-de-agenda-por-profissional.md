```
Papel: registra o lock de transação da agenda de cada profissional, que serializa as gravações de agendamento e evita o deadlock na constraint de exclusão.
Entrada: docs/status.md
Relaciona-se com: 0004-conflito-de-horario.md, 0005-ordem-por-conversa.md, 0010-llmclient.md, ../arquitetura.md (seção 7), ../diagnosticos/2026-11-25-instabilidade-concorrencia.md, ../../app/agenda/agenda_propria.py, ../../app/agenda/servico.py, ../../tests/concurrency/test_servico_concorrencia.py, ../../tests/integration/test_agenda_propria.py, ../../tests/isolation/test_isolation_rls.py, ../../tests/integration/test_servico_agendamento.py
```

# 0011: Lock de agenda por profissional

## Contexto

O [ADR 0004](./0004-conflito-de-horario.md) garante o conflito de horário com uma constraint `EXCLUDE` em `agendamentos`. O lock da conversa ([ADR 0005](./0005-ordem-por-conversa.md)) não serializa contatos diferentes.

O [diagnóstico de 2026-11-25](../diagnosticos/2026-11-25-instabilidade-concorrencia.md) mostrou o que acontece quando 3 ou mais contatos pedem o mesmo horário ao mesmo tempo:

- Cada INSERT grava a linha e só depois procura conflitos. Duas gravações simultâneas esperam uma pela outra, e o Postgres aborta uma com `40P01` depois de `deadlock_timeout` (1 s).
- A nova tentativa do serviço forma outro ciclo. Depois de 3 tentativas, o `40P01` saía do serviço como `OperationalError` cru, contra o contrato do ADR 0004.
- No Windows com Docker Desktop, isso aconteceu em 3 de 10 execuções com processo novo.

## Alternativas consideradas

- **Espera com variação aleatória entre as tentativas, e mais tentativas.** Descartada como solução. Reduz a chance de o ciclo se repetir, mas continua dependendo de sorte.
- **Só traduzir o `40P01` esgotado para um erro de domínio.** Descartada como solução única. Esconde o erro cru, mas o paciente continua recebendo uma falha que não precisava existir. Fica como segunda barreira.
- **Lock na linha do profissional com `SELECT ... FOR UPDATE`.** Descartada. Faria o mesmo, mas a leitura da linha de `profissionais` passaria a disputar com qualquer outra escrita nela, e o lock precisaria de uma linha existente e visível pelo RLS.
- **Advisory lock de transação por tenant e profissional.** Escolhida. O ADR 0004 tinha descartado o advisory lock como barreira principal do conflito. Aqui ele não é a barreira: a constraint continua decidindo o que entra, e o lock só impede que as gravações se cruzem.

## Decisão

Toda gravação de agendamento pega, logo antes do INSERT, o lock de transação da agenda do profissional:

```sql
SELECT pg_advisory_xact_lock(hashtext(current_setting('app.tenant_id')::uuid::text), :profissional_id)
```

O lock fica em `AgendaPropria.criar` ([`agenda_propria.py`](../../app/agenda/agenda_propria.py)) e dura até o fim da transação.

### Chave do lock

- A forma com dois inteiros (`int4`, `int4`) fica num espaço de chaves separado da forma com um `bigint`. Um advisory lock futuro de um inteiro não colide com este.
- **Tenant:** vem da sessão, nunca de um parâmetro (regra 5 do [CLAUDE.md](../../CLAUDE.md)). O `::uuid` faz a chamada falhar sem tenant na sessão. Isso cobre o setting ausente e também o setting vazio, que sobra numa conexão do pool depois de um `set_config` local de uma transação anterior. Sem tenant, não há lock nem gravação.
- **Por que o `::uuid`:** um `set_config('app.tenant_id', ..., true)` vale só até o fim da transação. Depois dela, na mesma conexão do pool, o setting continua existindo com o valor `''`, e não desaparece. Sem o `::uuid`, `hashtext('')` funcionaria, e a gravação pegaria um lock com uma chave vazia, comum a todas as sessões sem tenant. Com o `::uuid`, a chamada falha antes do lock. O INSERT falharia de qualquer forma, mas o lock já teria sido pego e seguraria as outras sessões sem tenant até o rollback.
- **Erro sem tenant na sessão,** conferido no banco local em 2026-11-25 com a conta `app_clinicas`:
  - Conexão que nunca definiu o setting: `42704` (`unrecognized configuration parameter "app.tenant_id"`), que chega como `ProgrammingError`.
  - Conexão em que o setting ficou `''`: `22P02` (`invalid input syntax for type uuid`), que chega como `DataError`.
  - Nos dois casos, nenhum lock é pego e nenhuma linha é gravada. O serviço não traduz esses códigos, porque gravar sem tenant é erro de programação e não concorrência. O erro sobe como veio, e o job segue o caminho normal de falha do worker.
  - A policy `isolamento_tenant` usa o mesmo cast (`tenant_id = current_setting('app.tenant_id')::uuid`), que nunca vira NULL nem casa com uma linha. O que ela garante é que essa conexão não recebe linha de nenhuma clínica. Nas medições de 2026-11-25, as leituras de `clinicas`, `agendamentos`, `profissionais` e `jobs` falharam com os mesmos códigos, inclusive com uma linha presente em `clinicas`. Esse erro depende do plano da consulta e não é garantido: um plano que não avalie a expressão pode terminar com zero linhas e sem erro. Nenhum código depende do erro para detectar a falta de tenant. Os testes de setting vazio em [`test_isolation_rls.py`](../../tests/isolation/test_isolation_rls.py) cobrem SELECT, INSERT, UPDATE e DELETE nas 15 tabelas.
- **Profissional:** `profissional_id` é `integer`, então entra direto no segundo inteiro, sem hash.
- **Colisão:** só o `hashtext` do tenant pode colidir, num espaço de 32 bits. Dois tenants com o mesmo hash e um profissional de mesmo id passariam a esperar um pelo outro. É aceitável porque só serializa a mais: a constraint e o RLS continuam decidindo o que entra e o que cada clínica vê. Como os ids de `profissionais` vêm de uma sequência única, dois tenants nem chegam a ter um profissional de mesmo id hoje.
- **`hashtext` é uma função interna do Postgres,** sem garantia de dar o mesmo resultado entre versões. É aceitável aqui porque a chave não é persistida nem comparada entre processos de versões diferentes. Ela só existe durante a transação, num único servidor. Uma troca de versão, como a migração para o Supabase (etapa 15), não deixa lock antigo para trás.

### Restrições

1. **Mais de um profissional numa operação.** Hoje toda gravação trava um profissional só, porque a remarcação mantém o mesmo profissional. Quem implementar uma operação que grave em mais de um profissional, como a remarcação com troca de profissional, trava todos na mesma transação em ordem crescente de `profissional_id`. Ordens diferentes entre duas transações criariam um deadlock novo.
2. **Nada lento entre o lock e o commit.** O lock é pego logo antes do INSERT e fica até o commit. Nenhuma chamada ao LLM pode acontecer depois do INSERT e antes do commit, porque a agenda do profissional ficaria parada durante a chamada (até 60 s, pelo [ADR 0010](./0010-llmclient.md)), e as outras gravações passariam do `lock_timeout` de 5 s. Na etapa 7, o texto de resposta é gerado antes da gravação ou depois do commit.
3. **Outros caminhos de gravação.** O lock fica no único INSERT em `agendamentos`, então todo caminho que grave pelo `AgendaProvider`, como o painel (etapa 14), passa por ele. Um `AgendaProvider` externo (D-17) precisa de uma serialização equivalente do seu lado, ou de pegar este mesmo lock antes de gravar. Uma remarcação futura que mova a linha com UPDATE de `inicio` e `fim`, em vez de cancelar e criar, também precisa pegar o lock antes do UPDATE, porque não passaria pelo INSERT.
4. **Segunda barreira.** Um `40P01` que sobrar depois das tentativas, ou um `55P03` porque a espera pelo lock passou do `lock_timeout`, vira `ConcorrenciaNaAgenda` ([`regras.py`](../../app/agenda/regras.py)). O erro é transitório, não herda de `ErroPermanente`, e o job tenta de novo com backoff. A mensagem não repete o texto do erro do banco. Nenhum erro cru do banco chega ao chamador, como pede o ADR 0004.

### Lock e SAVEPOINT

A inserção roda num SAVEPOINT (ADR 0004). Conferido no banco local em 2026-11-25:

- `ROLLBACK TO SAVEPOINT` solta o lock pego dentro dele. Só acontece no `23P01` ou no `40P01`, quando a linha também foi desfeita, então não há o que proteger.
- `RELEASE SAVEPOINT` passa o lock para a transação externa, que o mantém até o commit.

## Justificativa

O lock troca um comportamento que dependia de sorte por um determinístico: as gravações do mesmo profissional entram em fila, e a perdedora recebe o `23P01` da constraint, que vira `HorarioIndisponivel`. O custo é uma espera curta entre pacientes do mesmo profissional, enquanto a transação vencedora não fizer nada lento depois do INSERT. Profissionais diferentes não esperam um pelo outro.

## Consequências

- Gravações concorrentes no mesmo profissional deixaram de produzir deadlock. Validação em 2026-11-25, com processo novo a cada execução: 4 contatos criando no mesmo horário, 20 de 20 sem `40P01`, com exatamente 1 aceito e 3 `HorarioIndisponivel`. O mesmo para 4 contatos remarcando para o mesmo horário, 20 de 20, com as 3 consultas antigas dos perdedores ainda agendadas.
- Os testes de criação e de remarcação concorrentes soltam as 4 threads juntas logo antes do lock e do INSERT, por um `AgendaProvider` de teste injetado pelo parâmetro `agenda`. Uma largada no início da operação deixava as threads chegarem espalhadas ao INSERT.
- A falta do lock é detectada pela presença dele, na criação e na remarcação. Os testes `test_criar_segura_o_lock_da_agenda_ate_o_commit` ([`test_agenda_propria.py`](../../tests/integration/test_agenda_propria.py)) e `test_remarcar_pega_o_lock_da_agenda_ate_o_commit` ([`test_servico_agendamento.py`](../../tests/integration/test_servico_agendamento.py)) conferem, de outra conexão, que o lock da agenda do profissional está concedido antes do commit, com o tenant na chave, e some depois dele. Prova por mutação em 2026-11-25: sem o lock em `AgendaPropria.criar`, os dois falham. Uma remarcação que mova a linha antiga com UPDATE, sem passar por `AgendaPropria.criar`, também derruba o teste da remarcação.
- Prova por mutação pela ausência de deadlock, sem o lock, 20 execuções de cada com processo novo, em 2026-11-25:
  - **Criação:** falhou em 15 de 20, com 163 deadlocks no log do Postgres. A falha chegou como `ConcorrenciaNaAgenda`, e não como erro cru.
  - **Remarcação:** passou 20 de 20, sem nenhum deadlock no log e com 123 conflitos `23P01` limpos. Por isso, na remarcação, só o teste de presença detecta a falta do lock. Ver a pergunta em aberto abaixo.
- O pior caso de uma gravação nos testes passa a incluir a espera pelo lock ([`prazos.py`](../../tests/concurrency/prazos.py)).
- `test_conflito_agendamento.py` passou a aceitar só o `23P01` como rejeição.
- A restrição 2 vale para a tarefa 7.2 e está registrada no [`status.md`](../status.md).

## Pergunta em aberto

Por que a remarcação concorrente não sofre deadlock sem o lock? Com as 4 threads soltas juntas logo antes do INSERT, a disputa aconteceu (123 conflitos `23P01` no log), mas nenhum deadlock, enquanto a criação no mesmo cenário teve 163. A diferença visível é que a remarcação faz o INSERT num SAVEPOINT dentro de outro, depois do UPDATE que cancela a consulta antiga. Essa hipótese não foi testada. O resultado é empírico e não é garantia, e a remarcação continua sob o lock. Não há tarefa aberta para investigar.

## Status

Aceita
