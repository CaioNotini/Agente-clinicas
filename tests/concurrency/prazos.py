"""Prazos dos testes de concorrencia (P2 do diagnostico de 2026-11-25).

Regra: toda espera interna de um teste (Barrier, Event, cadeia de tentativas, join)
termina antes do limite do pytest, com margem. Assim o teste falha pela propria
assercao, mostrando o resultado de cada thread, e a limpeza das fixtures roda.

- O prazo do juntar vem do pior caso que o proprio codigo garante (lock_timeout
  vezes tentativas). Quando ele acaba, as threads ja terminaram sozinhas, e a
  limpeza nao fica esperando uma transacao aberta.
- O limite do pytest do teste e o prazo mais MARGEM, nunca abaixo do limite global.

Sem isso, o pytest-timeout (metodo thread) encerra o processo inteiro no Windows:
nada e relatado e os dados do teste ficam no banco
(docs/diagnosticos/2026-11-25-instabilidade-concorrencia.md).

ESPERA_SINAL foi reduzido de 5 s para 2 s com base em medicao local: uma conexao
nova ao banco leva cerca de 25 ms (Windows com Docker Desktop). Um
BrokenBarrierError ou um Event que nao chega na CI e o primeiro sinal de que esse
valor precisa subir.
"""
import math
import time

from app.agenda.servico import TENTATIVAS_DEADLOCK
from app.core.conversas import LOCK_TIMEOUT_MS

# timeout do pytest.ini. test_prazos.py confere que os dois sao iguais.
LIMITE_PYTEST_PADRAO = 10.0

# Espera por um sinal entre threads: Barrier, Event de "chegou" e o poll de pg_locks.
ESPERA_SINAL = 2.0

# Espera da thread que segura a transacao ate a principal libera-la: a principal
# confirma dois sinais antes (a thread chegou e a outra esta esperando).
ESPERA_LIBERAR = 2 * ESPERA_SINAL

# Maior espera de um lock dentro de uma transacao da aplicacao (lock_timeout).
ESPERA_LOCK = LOCK_TIMEOUT_MS / 1000

# deadlock_timeout padrao do Postgres, conferido no banco local. Limita a espera de
# quem grava sem lock_timeout ate o banco abortar um ciclo.
DEADLOCK_TIMEOUT = 1.0

# Pior caso de uma gravacao pelo servico: cada tentativa espera no maximo o
# lock_timeout, e o 40P01 tenta de novo ate TENTATIVAS_DEADLOCK.
PIOR_CASO_GRAVACAO = TENTATIVAS_DEADLOCK * ESPERA_LOCK

# Tempo que a gravacao vencedora segura a transacao antes do commit, para as
# outras chegarem a constraint enquanto ela esta aberta.
SEGURA_ANTES_DO_COMMIT = 0.2

# Folga para a assercao e a limpeza depois do prazo.
MARGEM = 3.0


def limite_pytest(prazo: float) -> int:
    """Limite do pytest para um teste cujo juntar usa este prazo."""
    return max(int(LIMITE_PYTEST_PADRAO), math.ceil(prazo + MARGEM))


def juntar(threads, prazo: float) -> list:
    """Espera todas as threads com um prazo unico. Devolve os nomes das que seguem vivas.

    Um join com timeout por thread soma os prazos. Aqui o prazo vale para o conjunto.
    """
    limite = time.monotonic() + prazo
    for thread in threads:
        thread.join(timeout=max(0.0, limite - time.monotonic()))
    return [thread.name for thread in threads if thread.is_alive()]
