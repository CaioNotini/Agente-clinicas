```
Papel: registra como o conflito de horario de agendamentos e garantido e por que inicio e fim usam timestamptz.
Entrada: docs/status.md
Relaciona-se com: ../arquitetura.md (secao 7, modelo de dados), ../etapas.md (etapa 5), ../../app/db/models.py, ../../migrations/versions/b131d6ee6471_cria_tabela_agendamentos.py, ../../tests/isolation/test_isolation_rls.py
```

# 0004: Conflito de horario de agendamentos

## Contexto

A etapa 5 (ver [`etapas.md`](../etapas.md)) agenda, remarca e cancela consultas. A tabela `agendamentos` entra na seção 7 de [`arquitetura.md`](../arquitetura.md) com profissional, serviço, data e hora e status. Dois pacientes diferentes podem tentar reservar o mesmo horário do mesmo profissional ao mesmo tempo. O lock por conversa da etapa 4 serializa mensagens de um mesmo contato, mas não impede essa corrida entre contatos distintos, porque a chave do lock é `(tenant_id, contato_telefone)`. Era preciso uma barreira que não dependesse da ordem nem da sessão da aplicação.

As demais tabelas do schema guardam tempo em `timestamp` sem fuso. Agendamento precisa comparar instantes de forma não ambígua, inclusive na virada de horário de verão, o que exige fuso explícito.

## Alternativas consideradas

- **Checar conflito só em código antes de inserir.** Descartada: duas transações concorrentes leem a agenda livre e inserem as duas, porque a checagem e a inserção não são atômicas sob concorrência.
- **Lock na linha do profissional com SELECT ... FOR UPDATE durante a reserva.** Descartada como barreira principal: serializa por profissional, mas a garantia depende de todo caminho de escrita lembrar de travar antes de inserir, o que não é verificável no banco.
- **Advisory lock por chave derivada de profissional e slot.** Descartada: sem schema novo, mas a garantia fica em convenção de chave e disciplina de uso, mais difícil de auditar que uma constraint.
- **Constraint EXCLUDE no banco.** Escolhida.
- **Guardar inicio e fim em timestamp sem fuso, como as demais tabelas.** Descartada para esta tabela: comparar instantes sem fuso é ambíguo na virada de horário de verão.

## Decisão

O conflito é garantido por uma constraint `EXCLUDE USING gist` em `agendamentos`, sobre `tenant_id` com igualdade, `profissional_id` com igualdade e `tstzrange(inicio, fim)` com sobreposição, restrita a `status = 'agendado'`. O intervalo é semiaberto `[inicio, fim)`, então horários adjacentes não conflitam. A constraint precisa da extensão `btree_gist` para os operadores de igualdade de `tenant_id` (uuid) e `profissional_id` (integer) dentro do índice gist. A violação chega como SQLSTATE `23P01`. Com duas gravações concorrentes do mesmo horário, a perdedora também pode receber `40P01` (deadlock detectado na verificação da constraint), observado em 2026-11-18 por [`test_conflito_agendamento.py`](../../tests/concurrency/test_conflito_agendamento.py). Nos dois casos só uma gravação é aceita. O `AgendaPropria` deixa o erro do banco subir, e o serviço de agendamento o traduz (ver Consequências).

A função pura de conflito (`intervalos_conflitam`, em [`regras.py`](../../app/agenda/regras.py), tarefa 5.2) usa a mesma semântica de intervalo semiaberto, para o código e o banco concordarem. A constraint é a barreira que vale sob concorrência. A função pura serve à decisão e aos testes sem banco.

As colunas `inicio` e `fim` usam `timestamptz`, com os instantes gravados em UTC. As colunas de tempo com fuso no schema são estas e `handoffs.responder_ate` ([ADR 0009](./0009-agendamento-handoff-etapa5.md)). As demais usam `timestamp` sem fuso. A coluna `status` assume apenas `agendado` e `cancelado`, garantido por CHECK.

## Justificativa

Uma constraint no banco não depende da ordem de execução nem de a aplicação lembrar de travar algo. O Postgres rejeita a segunda inserção conflitante mesmo sob duas transações simultâneas. O intervalo semiaberto deixa consultas encostadas, como 10:00 a 10:30 e 10:30 a 11:00, conviverem sem falso conflito. O `timestamptz` remove a ambiguidade de fuso na comparação de instantes.

## Consequências

- A imagem do banco precisa ter `btree_gist`. Confirmado na imagem `pgvector/pgvector:pg15` usada no Docker local e no CI. A migration habilita a extensão antes de criar a constraint.
- Implementado na tarefa 5.3, em [`servico.py`](../../app/agenda/servico.py): a inserção de agendamento roda dentro de um SAVEPOINT, porque o `23P01` e o `40P01` abortam a transação corrente. Os dois códigos têm tratamento diferente:
  - `23P01` é conflito de fato. O código relê sob RLS: se o conflitante for do mesmo paciente, profissional e início, devolve o existente (idempotência na corrida). Caso contrário, levanta `HorarioIndisponivel`. A mesma idempotência vale na verificação prévia, antes de gravar: o pedido repetido devolve o existente nos dois caminhos.
  - `40P01` é deadlock, não indisponibilidade. O horário pode estar livre, porque a outra transação ainda pode ser desfeita. A operação é tentada de novo, até 3 vezes no total, e só um `23P01` na nova tentativa vira `HorarioIndisponivel`. Se as 3 derem `40P01`, o erro sobe e o job segue o caminho normal de nova tentativa do worker.
- Agendamentos cancelados não entram no conflito, porque a constraint é restrita a `status = 'agendado'`. Remarcar marca o antigo como cancelado antes de criar o novo, na mesma transação.
- Na remarcação, o pedido repetido não vale. A regra fica na seção 7 da [arquitetura](../arquitetura.md#7-modelo-de-dados).
- A tabela tem RLS, FORCE e policy `isolamento_tenant`, está em `TABELAS_TENANT` e é coberta pelos testes de isolamento, como exige o CLAUDE.md. A escrita cruzada no teste de isolamento usa dados válidos e exige `match="row-level security"`, para a policy ser a única barreira.
- O fuso por clínica foi decidido no [ADR 0009](./0009-agendamento-handoff-etapa5.md). O armazenamento continua em UTC, e `AgendaPropria.criar` rejeita horários sem fuso.

## Status

Aceita. Revisada em 2026-11-18: o conflito concorrente também chega como `40P01`, e a tradução dos erros fica marcada como planejada para a 5.3. Revisada em 2026-11-23: só o `23P01` vira `HorarioIndisponivel`, e o `40P01` leva a uma nova tentativa. A função pura de conflito passa a existir na tarefa 5.2, e o fuso deixa de estar em aberto. Na 5.3, o SAVEPOINT e a tradução passam a estar implementados, e o pedido repetido devolve o existente também na verificação prévia.
