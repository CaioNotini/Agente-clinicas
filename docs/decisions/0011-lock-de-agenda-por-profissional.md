```
Papel: registra o lock de transação da agenda de cada profissional, que serializa as gravações de agendamento e evita o deadlock na constraint de exclusão.
Entrada: docs/status.md
Relaciona-se com: 0004-conflito-de-horario.md, 0005-ordem-por-conversa.md, 0010-llmclient.md, ../arquitetura.md (seção 7), ../diagnosticos/2026-11-25-instabilidade-concorrencia.md, ../../app/agenda/agenda_propria.py, ../../app/agenda/servico.py, ../../tests/concurrency/test_servico_concorrencia.py, ../../tests/integration/test_agenda_propria.py
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
- **Profissional:** `profissional_id` é `integer`, então entra direto no segundo inteiro, sem hash.
- **Colisão:** só o `hashtext` do tenant pode colidir, num espaço de 32 bits. Dois tenants com o mesmo hash e um profissional de mesmo id passariam a esperar um pelo outro. É aceitável porque só serializa a mais: a constraint e o RLS continuam decidindo o que entra e o que cada clínica vê. Como os ids de `profissionais` vêm de uma sequência única, dois tenants nem chegam a ter um profissional de mesmo id hoje.
- **`hashtext` é uma função interna do Postgres,** sem garantia de dar o mesmo resultado entre versões. É aceitável aqui porque a chave não é persistida nem comparada entre processos de versões diferentes. Ela só existe durante a transação, num único servidor. Uma troca de versão, como a migração para o Supabase (etapa 15), não deixa lock antigo para trás.

### Restrições

1. **Mais de um profissional numa operação.** Hoje toda gravação trava um profissional só, porque a remarcação mantém o mesmo profissional. Quem implementar uma operação que grave em mais de um profissional, como a remarcação com troca de profissional, trava todos na mesma transação em ordem crescente de `profissional_id`. Ordens diferentes entre duas transações criariam um deadlock novo.
2. **Nada lento entre o lock e o commit.** O lock é pego logo antes do INSERT e fica até o commit. Nenhuma chamada ao LLM pode acontecer depois do INSERT e antes do commit, porque a agenda do profissional ficaria parada durante a chamada (até 60 s, pelo [ADR 0010](./0010-llmclient.md)), e as outras gravações passariam do `lock_timeout` de 5 s. Na etapa 7, o texto de resposta é gerado antes da gravação ou depois do commit.
3. **Outros caminhos de gravação.** O lock fica no único INSERT em `agendamentos`, então todo caminho que grave pelo `AgendaProvider`, como o painel (etapa 14), passa por ele. Um `AgendaProvider` externo (D-17) precisa de uma serialização equivalente do seu lado, ou de pegar este mesmo lock antes de gravar.
4. **Segunda barreira.** Um `40P01` que sobrar depois das tentativas, ou um `55P03` porque a espera pelo lock passou do `lock_timeout`, vira `ConcorrenciaNaAgenda` ([`regras.py`](../../app/agenda/regras.py)). O erro é transitório, não herda de `ErroPermanente`, e o job tenta de novo com backoff. A mensagem não repete o texto do erro do banco. Nenhum erro cru do banco chega ao chamador, como pede o ADR 0004.

### Lock e SAVEPOINT

A inserção roda num SAVEPOINT (ADR 0004). Conferido no banco local em 2026-11-25:

- `ROLLBACK TO SAVEPOINT` solta o lock pego dentro dele. Só acontece no `23P01` ou no `40P01`, quando a linha também foi desfeita, então não há o que proteger.
- `RELEASE SAVEPOINT` passa o lock para a transação externa, que o mantém até o commit.

## Justificativa

O lock troca um comportamento que dependia de sorte por um determinístico: as gravações do mesmo profissional entram em fila, e a perdedora recebe o `23P01` da constraint, que vira `HorarioIndisponivel`. O custo é uma espera curta entre pacientes do mesmo profissional, enquanto a transação vencedora não fizer nada lento depois do INSERT. Profissionais diferentes não esperam um pelo outro.

## Consequências

- Gravações concorrentes no mesmo profissional deixaram de produzir deadlock. Validação em 2026-11-25, com processo novo a cada execução: 4 contatos criando no mesmo horário, 20 de 20 sem `40P01`, com exatamente 1 aceito e 3 `HorarioIndisponivel`. O mesmo para 4 contatos remarcando para o mesmo horário, 20 de 20, com as 3 consultas antigas dos perdedores ainda agendadas.
- Prova por mutação: sem o lock, a criação falhou em 5 de 20 execuções, com 55 deadlocks no log do Postgres. A falha chegou como `ConcorrenciaNaAgenda`, e não como erro cru. O teste de remarcação passou 20 de 20 também sem o lock, então sozinho ele não detecta a falta do lock. A remarcação usa o mesmo `AgendaPropria.criar`, coberto pelo teste de criação.
- O pior caso de uma gravação nos testes passa a incluir a espera pelo lock ([`prazos.py`](../../tests/concurrency/prazos.py)).
- `test_conflito_agendamento.py` passou a aceitar só o `23P01` como rejeição.
- A restrição 2 vale para a tarefa 7.2 e está registrada no [`status.md`](../status.md).

## Status

Aceita
