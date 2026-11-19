"""Duas gravacoes concorrentes do mesmo horario: so uma e aceita (B7, ADR 0004).

As duas sessoes app_clinicas inserem o mesmo horario do mesmo profissional antes
de qualquer commit. Sem a constraint EXCLUDE, as duas seriam gravadas.

A perdedora e rejeitada de duas formas, observadas em 2026-11-18:
- 23P01 (exclusion_violation), quando ela espera a outra confirmar e depois
  encontra o conflito.
- 40P01 (deadlock_detected), quando as duas ja inseriram no indice gist e cada
  uma espera a tupla ainda nao confirmada da outra. O Postgres aborta uma delas.
O ADR 0004 so preve o 23P01. A divergencia esta registrada em docs/status.md.

Usa o cenario e a sessao dos testes de integracao de AgendaPropria, com os dados
de apoio criados e removidos pela conta de administracao.
"""
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.agenda.agenda_propria import AgendaPropria
from tests.integration.test_agenda_propria import (  # noqa: F401 - cenario e fixture
    TELEFONE,
    cenario,
    engine_admin,
    sessao_tenant,
)

INICIO = datetime(2027, 5, 3, 14, 0, tzinfo=timezone.utc)
FIM = datetime(2027, 5, 3, 14, 30, tzinfo=timezone.utc)

# Codigos com que a gravacao perdedora pode ser rejeitada (ver docstring)
REJEICOES_ESPERADAS = {"23P01", "40P01"}

# Tempo que cada transacao fica aberta depois do insert, para a outra inserir antes do commit
ESPERA_ANTES_DO_COMMIT = 0.5


def test_duas_gravacoes_concorrentes_do_mesmo_horario_so_uma_e_aceita(cenario):
    tenant, profissional, servico = cenario
    largada = threading.Barrier(2)
    resultados = []
    trava_resultados = threading.Lock()

    def gravar():
        try:
            with sessao_tenant(tenant) as session:
                largada.wait(timeout=5)
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
    for thread in threads:
        thread.join(timeout=8)

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
