```
Papel: Diagnóstico da instabilidade dos testes de concorrência, feito em 2026-11-25. Não reflete o estado atual.
Entrada: docs/status.md
Relaciona-se com: ../status.md, ../arquitetura.md, ../decisions/0004-conflito-de-horario.md, ../decisions/0006-provisionamento-de-roles.md, 2026-11-25-rodada5.md
```

# Diagnóstico da instabilidade dos testes de concorrência

Feito em 2026-11-25, no commit `434a90e`, antes da tarefa 7.1. Nenhum arquivo de `app/` ou de `tests/` foi alterado. O banco local foi usado só para leitura, com uma exceção autorizada: a limpeza das sobras descrita em H4.

## Resumo

Há dois problemas diferentes.

1. **O estouro de 10 s é um deadlock real entre gravações concorrentes no mesmo horário.** Com 4 contatos gravando ao mesmo tempo, os INSERTs se travam na constraint de exclusão de `agendamentos`. A nova tentativa do serviço volta a travar, cada ciclo custa 1 s (`deadlock_timeout`), e o `40P01` acaba saindo do serviço como `OperationalError` cru. O teste leva cerca de 11,3 s e passa do limite de 10 s do pytest. É timing: aparece quando as conexões do pool são novas e quase não aparece com o pool aquecido, por isso a suíte completa e a CI passam.
2. **As 93 falhas da primeira execução foram de autenticação.** As roles `app_clinicas` e `worker_jobs` do banco local estavam com senhas diferentes das do ambiente. Os testes que rodaram antes de `test_senhas_roles.py`, que reaplica as senhas, falharam. Depois dele, tudo passou.

## Fatos de partida

- `test_varios_contatos_pelo_mesmo_horario_so_um_vence` usa 4 threads, `Barrier(4)` com espera de 5 s, `join(timeout=15)` por thread e o limite global de 10 s do `pytest-timeout`.
- O lock da conversa usa `lock_timeout` de 5 s (`LOCK_TIMEOUT_MS` em [`conversas.py`](../../app/core/conversas.py)).
- O serviço repete a inserção no `40P01` até `TENTATIVAS_DEADLOCK = 3`, logo em seguida, sem espera ([`servico.py`](../../app/agenda/servico.py)).
- No banco local: Postgres 15.20, `deadlock_timeout = 1s`, `lock_timeout = 0` por padrão.
- No Windows, o estouro do `pytest-timeout` (método `thread`) encerra o processo inteiro, sem rodar as fixtures de limpeza.

## Hipóteses

### H2 e H3: soma de tempos e deadlock. Confirmadas

**Execução.** O arquivo rodou sozinho 3 vezes com `--timeout=60`.

| Execução | Resultado | Duração do teste |
| -------- | --------- | ---------------- |
| 1 | falhou | 11,26 s |
| 2 | passou | 0,27 s |
| 3 | passou | 0,26 s |

Na execução 1, a falha não foi de tempo, foi de resultado:

```
AssertionError: ['OperationalError: 40P01', 'OperationalError: 40P01', 'OperationalError: 40P01', 'aceito']
```

**Evidência no log do Postgres** (`docker logs`):

```
ERROR:  deadlock detected
DETAIL:  Process 607 waits for ShareLock on transaction 29399; blocked by process 612.
         Process 612 waits for ShareLock on transaction 29400; blocked by process 607.
CONTEXT: while checking exclusion constraint on tuple (0,129) in relation "agendamentos"
```

O mesmo padrão se repete a cada 1 s (19:35:38,6, 39,6, 40,6, 41,6...), com pares diferentes entre os 4 processos, todos inserindo o mesmo profissional e horário com contatos diferentes.

**Mecanismo.**

- Na constraint de exclusão, cada INSERT grava a linha e só depois procura conflitos. Duas gravações simultâneas veem a linha uma da outra, ainda não confirmada, e esperam uma pela outra. O Postgres detecta o ciclo depois de `deadlock_timeout` (1 s) e aborta uma delas.
- A vítima volta ao SAVEPOINT e tenta de novo na hora. Com 3 ou mais gravações ainda abertas, a nova linha forma outro ciclo.
- Cada thread perdedora pode gastar as 3 tentativas, a 1 s por ciclo. Por isso o total fica perto de 11 s.
- Esgotadas as tentativas, o `40P01` sobe como `OperationalError`. Isso contraria o contrato do serviço ("nenhum erro cru do banco chega ao chamador", na docstring do teste).
- Com só 2 gravações, o ciclo se resolve na primeira nova tentativa, porque a sobrevivente não espera mais pela vítima.

**Por que passa do limite.** As esperas internas do teste somam mais que 10 s: o `Barrier` pode esperar 5 s, cada `join` espera até 15 s, e a cadeia de deadlocks chega a cerca de 9 s (3 tentativas por perdedora, 1 s cada, encadeadas). O `pytest-timeout` dispara antes de qualquer espera interna do teste e mata o processo.

**Não houve deadlock com o lock da conversa.** Cada thread usa um contato diferente, então os locks de conversa não competem. Os ciclos do log são todos na constraint de exclusão.

### H1: primeira conexão e diferença de ambiente. Causa de timing, não do erro

**Frequência medida, sempre com `--timeout=60` e junitxml no scratchpad:**

| Condição | Falhas | Observação |
| -------- | ------ | ---------- |
| Processo novo a cada execução, 10 vezes | 3 de 10 | As 3 falhas levaram cerca de 11,8 s. Uma passou em 5,6 s, sinal de deadlock resolvido na nova tentativa |
| Mesmo processo, pool aquecido, 10 vezes | 0 de 10 | 0,41 s cada |
| Mesmo processo, pool descartado antes de cada execução, 10 vezes | 2 de 10 | 10,7 s e 11,5 s |

O gatilho está ligado às conexões novas do pool, e não ao código Python "frio" (compilação de SQL e configuração do ORM). Na suíte completa, os testes de concorrência anteriores já aquecem o pool, por isso ela passa.

**Medição da conexão** (sem imprimir URL nem credenciais):

| Medida | Tempo |
| ------ | ----- |
| Conexão nova pelo engine da aplicação (`localhost`) | 25 ms |
| Conexão vinda do pool | 2 ms |
| TCP puro em `127.0.0.1` na porta do banco | 27 ms |
| TCP puro em `::1` na mesma porta | 0,5 ms |
| Resolução de `localhost` | 4,7 ms |

**Conclusão.**

- A primeira conexão não leva segundos. Leva cerca de 25 ms. A H1 como causa do estouro está descartada.
- A diferença entre o TCP em IPv4 (27 ms) e em IPv6 (0,5 ms), sem o Postgres envolvido, é compatível com o custo do encaminhamento de porta do Docker Desktop no Windows. Não confirmei qual dos dois caminhos o libpq usa.
- Esse atraso desloca o instante em que cada thread chega ao INSERT e muda a chance de as gravações se sobreporem. Ele perturba o timing, mas não causa o deadlock.
- A CI roda em Linux, com o Postgres como serviço do runner e conexões locais muito mais rápidas, e passa. Não testei se o deadlock também aparece no Linux com conexões novas. Isso fica **inconclusivo**: o mecanismo do Postgres é o mesmo, então a falha deve ser possível lá, só mais rara.

### H4: dados deixados por execução interrompida. Confirmada, sem efeito nas 93 falhas

- Antes de qualquer limpeza, o banco local tinha 15 clínicas de nome `C`, o nome usado por `semear()` em [`cenarios_etapa5.py`](../../tests/cenarios_etapa5.py), com profissionais, serviços e regras, e nenhum agendamento.
- Elas foram criadas em 5 instantes (19:35:37, 19:36:09, 19:37:04, 19:37:15 e 19:37:29), que coincidem com os 5 processos mortos pelo `pytest-timeout` nesta sessão. São 3 clínicas por `semear()`.
- Não há agendamento porque quem venceu a corrida ainda não tinha feito o commit quando o processo morreu.
- Isso confirma que o estouro deixa sobras, porque a fixture `cenarios` não roda `limpar()`. Não foi preciso forçar outro estouro.
- As sobras não afetaram a suíte: ela passou com `500 passed` com elas no banco.
- **Limpeza feita:** `limpar()` do próprio projeto, aplicado só aos 15 tenants desses instantes, por um script no scratchpad. Depois: 0 clínicas e 0 profissionais no banco local, e a suíte de novo com `500 passed, 4 deselected`.

### H5: banco não pronto na subida. Confirmada como causa das 93 falhas

O log do Postgres desde a subida do contêiner (19:27:46):

```
LOG:  database system was not properly shut down; automatic recovery in progress
LOG:  database system is ready to accept connections
19:32  FATAL: password authentication failed for user "app_clinicas"   (1)
19:33  FATAL: password authentication failed for user "app_clinicas"   (63)
19:33  FATAL: password authentication failed for user "worker_jobs"    (25)
```

Nas execuções normais da suíte aparecem só 1 ou 2 falhas de senha por role. Elas parecem vir dos casos negativos de [`test_senhas_roles.py`](../../tests/integration/test_senhas_roles.py). Na primeira execução foram 89, número próximo das 93 falhas.

**Mecanismo provável.**

- As roles do volume local estavam com senhas diferentes das do ambiente atual.
- Os testes de `tests/concurrency/`, que rodam antes de `tests/integration/` em ordem alfabética, falharam na autenticação.
- Quando `test_senhas_roles.py` rodou [`scripts/definir_senhas.py`](../../scripts/definir_senhas.py), as senhas foram reaplicadas a partir do ambiente, e as execuções seguintes passaram.

**Ressalvas.**

- A lista das 93 falhas não foi guardada. A ligação é pelo log, pela contagem e pelo horário, não por falha a falha.
- Não sei por que as senhas estavam diferentes. Não li o `.env`, por regra. As causas possíveis são uma mudança no `.env` ou um volume antigo.
- O "not properly shut down" mostra que o contêiner tinha sido derrubado sem desligamento limpo. Não há sinal de que isso tenha mudado senhas.

## Proposta de correção

Nada foi aplicado. Cada item precisa da aprovação do desenvolvedor.

### P1. Deadlock com 3 ou mais gravações no mesmo horário (produto, exige ADR)

O contrato do [ADR 0004](../decisions/0004-conflito-de-horario.md) é que nenhum erro cru do banco chegue ao chamador. Hoje ele falha com 3 ou mais pacientes disputando o mesmo horário ao mesmo tempo. Em produção, o `40P01` cru cairia no retry genérico do job, com backoff de 60 s, e o paciente esperaria. É raro, mas acontece de verdade.

Opções:

- **(a) Serializar as gravações por profissional** com `pg_advisory_xact_lock` sobre `(tenant_id, profissional_id)` antes do INSERT. Elimina o deadlock, porque as gravações do mesmo profissional passam a entrar em fila. O custo é uma espera curta entre pacientes do mesmo profissional. **Recomendada**, porque troca um comportamento probabilístico por um determinístico.
- **(b) Espera com variação aleatória entre as novas tentativas** e mais tentativas. Reduz a chance de o ciclo se repetir, mas continua probabilístico.
- **(c) Traduzir o `40P01` esgotado** para um erro de domínio transitório, em vez de deixar o `OperationalError` subir. Complementa (a) ou (b), mas sozinho não resolve.

Relação com a 7.2: a chamada ao LLM vai ficar dentro do lock da conversa. Ela não participa desse deadlock, que é entre contatos diferentes, mas deixa as transações mais longas. Uma transação longa que já tenha feito o INSERT segura a linha por mais tempo. Com (a), a fila por profissional também passaria a esperar o LLM se ele for chamado depois do INSERT. A ordem entre a chamada ao LLM e a gravação precisa ser definida na 7.2.

### P2. Tempos do teste coerentes com o limite do pytest (teste)

Só subir o limite do pytest não resolve, por dois motivos:

- Se o limite do pytest for menor que a soma das esperas internas, o processo é morto antes de o teste falhar com mensagem. As fixtures não rodam e ficam sobras no banco (H4).
- Se for muito maior, um travamento real demora a aparecer.

A regra proposta: **toda espera interna termina antes do limite do pytest, com margem.** Assim o teste falha pela própria asserção, que mostra os resultados de cada thread, e a limpeza roda. Para este teste:

- pior caso esperado dentro do teste = `Barrier` (5 s) + cadeia de deadlocks (3 tentativas por perdedora, 1 s cada, até cerca de 9 s) + o `sleep` de 0,2 s.
- os `join` devem ter um prazo único, calculado a partir desse pior caso, e não 15 s por thread.
- o limite do pytest do teste (`@pytest.mark.timeout`) deve ficar acima desse prazo, com margem.

Com a P1 aplicada, a cadeia de deadlocks some e os prazos podem ser bem menores. Os outros 3 testes do arquivo usam esperas de 5 e 10 s e merecem a mesma revisão.

### P3. Senhas das roles divergentes (procedimento e teste)

- Uma fixture de sessão que confere o login de `app_clinicas` e de `worker_jobs` antes da suíte e, se falhar, interrompe com a mensagem "rode `python -m scripts.definir_senhas`", sem mostrar a senha. Isso troca 93 falhas por uma mensagem clara.
- No [README](../../README.md), deixar explícito que `definir_senhas` deve rodar de novo depois de mudar o `.env` ou de recriar o volume.

### P4. Sobras de processo morto

Com a P2, o processo deixa de ser morto nesse cenário. Não proponho limpeza automática de sobras agora.

## O que ficou sem validação ou inconclusivo

- O deadlock não foi reproduzido em Linux. A afirmação de que ele é possível na CI vem do mecanismo do Postgres, não de execução.
- Não confirmei qual caminho (IPv4 ou IPv6) o libpq usa para `localhost` no Windows.
- A lista das 93 falhas não foi guardada. A causa vem do log do Postgres.
- O motivo de as senhas estarem divergentes não foi apurado.
- Este diagnóstico foi feito pelo mesmo modelo que ajuda a escrever o código e não substitui a validação do desenvolvedor.
