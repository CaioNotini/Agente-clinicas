"""Duas gravacoes concorrentes do mesmo horario: so uma e aceita (B7, ADR 0004).

As duas sessoes app_clinicas inserem o mesmo horario do mesmo profissional antes
de qualquer commit. Sem a constraint EXCLUDE, as duas seriam gravadas.

A perdedora e rejeitada com 23P01 (exclusion_violation): ela espera o lock da
agenda do profissional (ADR 0011), e quando a outra confirma, encontra o conflito.
Antes do lock, tambem podia receber 40P01, quando as duas ja tinham inserido no
indice gist e cada uma esperava a tupla da outra.

Usa o cenario e a sessao dos testes de integracao de AgendaPropria, com os dados
de apoio criados e removidos pela conta de administracao.
"""
import threading
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.agenda.agenda_propria import AgendaPropria
from tests.concurrency.prazos import (
    DEADLOCK_TIMEOUT,
    ESPERA_SINAL,
    juntar,
    limite_pytest,
)
from tests.integration.test_agenda_propria import (  # noqa: F401 - cenario e fixture
    TELEFONE,
    cenario,
    engine_admin,
    sessao_tenant,
)

INICIO = datetime(2027, 5, 3, 14, 0, tzinfo=timezone.utc)
FIM = datetime(2027, 5, 3, 14, 30, tzinfo=timezone.utc)

# Codigos com que a gravacao perdedora pode ser rejeitada (ver docstring)
REJEICOES_ESPERADAS = {"23P01"}

# Tempo que cada transacao fica aberta depois do insert, para a outra inserir antes do commit
ESPERA_ANTES_DO_COMMIT = 0.5

# Prazo (tests/concurrency/prazos.py). Sem lock_timeout nesta sessao, a espera da
# segunda termina no commit da primeira ou quando o banco aborta um deadlock.
PRAZO = ESPERA_SINAL + ESPERA_ANTES_DO_COMMIT + DEADLOCK_TIMEOUT


@pytest.mark.timeout(limite_pytest(PRAZO))
def test_duas_gravacoes_concorrentes_do_mesmo_horario_so_uma_e_aceita(cenario):
    tenant, profissional, servico = cenario
    largada = threading.Barrier(2)
    resultados = []
    trava_resultados = threading.Lock()

    def gravar():
        try:
            with sessao_tenant(tenant) as session:
                largada.wait(timeout=ESPERA_SINAL)
                AgendaPropria().criar(
                    session,
                    profissional_id=profissional,
                    servico_id=servico,
                    contato_telefone=TELEFONE,
                    inicio=INICIO,
                    fim=FIM,
                )
                time.sleep(ESPERA_ANTES_DO_COMMIT)
            resultado = "aceito"
        except DBAPIError as erro:
            # 23P01 vem como IntegrityError e 40P01 como OperationalError
            resultado = getattr(erro.orig, "pgcode", None) or type(erro).__name__
        except Exception as erro:  # noqa: BLE001 - registrado para a assercao mostrar
            resultado = type(erro).__name__
        with trava_resultados:
            resultados.append(resultado)

    threads = [threading.Thread(target=gravar) for _ in range(2)]
    for thread in threads:
        thread.start()
    vivas = juntar(threads, PRAZO)

    assert not vivas, (vivas, resultados)
    assert len(resultados) == 2, resultados
    assert resultados.count("aceito") == 1, resultados
    rejeicao = next(r for r in resultados if r != "aceito")
    assert rejeicao in REJEICOES_ESPERADAS, resultados
    with engine_admin.connect() as conexao:
        ativos = conexao.execute(
            text(
                "SELECT COUNT(*) FROM agendamentos WHERE tenant_id = :t "
                "AND profissional_id = :p AND inicio = :i AND status = 'agendado'"
            ),
            {"t": str(tenant), "p": profissional, "i": INICIO},
        ).scalar()
    assert ativos == 1
