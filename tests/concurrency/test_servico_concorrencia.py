"""Corridas pelo mesmo horario passando pelo servico (tarefa 5.3, ADR 0004).

O servico traduz o 23P01 em HorarioIndisponivel, ou devolve o existente no pedido
repetido, e tenta de novo no 40P01. Nenhum erro cru do banco chega ao chamador, e a
transacao continua utilizavel depois do erro tratado.

Para forcar o caminho do 23P01, a gravacao B le a agenda antes de A confirmar,
fica esperando na constraint e so recebe o conflito quando A confirma. A espera de
B e confirmada em pg_locks antes de A confirmar, sem sleep fixo.
"""
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.agenda import servico
from app.agenda.regras import HorarioIndisponivel
from app.core.conversas import ConversaTravada, conversa_travada
from app.db.database import SessionLocal
from tests.cenarios_etapa5 import AGORA, agendamentos, engine_admin, limpar, semear

UTC = timezone.utc
# Terca 02/03 10:00 em Sao Paulo
INICIO = datetime(2027, 3, 2, 13, tzinfo=UTC)


@pytest.fixture
def cenarios():
    dados = semear()
    yield dados
    limpar(dados)


def _criar(travada, equipe, inicio=INICIO):
    return servico.criar(
        travada,
        profissional_id=equipe["prof"],
        servico_id=equipe["serv"],
        inicio=inicio,
        agora=AGORA,
    ).agendamento


def _esperar_bloqueio(timeout=5.0):
    """Espera ate alguma transacao estar parada esperando outra (lock nao concedido)."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        with engine_admin.connect() as conexao:
            if conexao.execute(
                text(
                    "SELECT count(*) FROM pg_locks "
                    "WHERE NOT granted AND locktype = 'transactionid'"
                )
            ).scalar():
                return
        time.sleep(0.02)
    raise AssertionError("a segunda gravacao nao chegou a esperar a primeira")


def test_varios_contatos_pelo_mesmo_horario_so_um_vence(cenarios):
    equipe = cenarios["equipe"]
    total = 4
    largada = threading.Barrier(total)
    resultados = []
    trava = threading.Lock()

    def pedir(indice):
        contato = f"(00) 90000-07{indice:02d}"
        try:
            with conversa_travada(equipe["tenant"], contato) as travada:
                largada.wait(timeout=5)
                _criar(travada, equipe)
                time.sleep(0.2)
            resultado = "aceito"
        except HorarioIndisponivel:
            resultado = "indisponivel"
        except Exception as erro:  # noqa: BLE001 - registrado para a assercao mostrar
            resultado = f"{type(erro).__name__}: {getattr(getattr(erro, 'orig', None), 'pgcode', '')}"
        with trava:
            resultados.append(resultado)

    threads = [threading.Thread(target=pedir, args=(i,)) for i in range(total)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert sorted(resultados) == ["aceito"] + ["indisponivel"] * (total - 1), resultados
    assert len(agendamentos(equipe["tenant"], status="agendado")) == 1


def _gravacao_a_segura(equipe, contato, pronto, liberar, erros):
    """A grava e segura a transacao aberta ate o sinal de liberar."""
    try:
        with conversa_travada(equipe["tenant"], contato) as travada:
            _criar(travada, equipe)
            pronto.set()
            assert liberar.wait(timeout=10)
    except Exception as erro:  # noqa: BLE001 - repassado para a thread principal
        erros.append(erro)
        pronto.set()


def test_23p01_vira_indisponivel_e_a_transacao_segue(cenarios):
    equipe = cenarios["equipe"]
    pronto, liberar, erros, saida_b = threading.Event(), threading.Event(), [], {}
    thread_a = threading.Thread(
        target=_gravacao_a_segura,
        args=(equipe, "(00) 90000-0801", pronto, liberar, erros),
    )
    thread_a.start()
    assert pronto.wait(timeout=5)

    def gravacao_b():
        try:
            with conversa_travada(equipe["tenant"], "(00) 90000-0802") as travada:
                try:
                    _criar(travada, equipe)
                    saida_b["primeira"] = "aceita"
                except HorarioIndisponivel:
                    saida_b["primeira"] = "indisponivel"
                # A mesma transacao continua utilizavel e confirma outro horario
                saida_b["segunda"] = _criar(
                    travada, equipe, INICIO + timedelta(hours=1)
                )
        except Exception as erro:  # noqa: BLE001 - repassado para a thread principal
            saida_b["erro"] = erro

    thread_b = threading.Thread(target=gravacao_b)
    thread_b.start()
    _esperar_bloqueio()
    liberar.set()
    thread_a.join(timeout=10)
    thread_b.join(timeout=10)

    assert erros == [] and "erro" not in saida_b, (erros, saida_b)
    assert saida_b["primeira"] == "indisponivel"
    ativos = agendamentos(equipe["tenant"], status="agendado")
    assert sorted(linha.inicio for linha in ativos) == [
        INICIO,
        INICIO + timedelta(hours=1),
    ]


def test_pedido_repetido_na_corrida_devolve_o_existente(cenarios):
    """Mesmo contato por fora da fila (sem o lock da conversa): o 23P01 devolve o existente.

    Simula uma entrada futura que nao passa pela ordem por conversa, como o painel.
    """
    equipe = cenarios["equipe"]
    contato = "(00) 90000-0803"
    pronto, liberar, erros, saida_b = threading.Event(), threading.Event(), [], {}
    thread_a = threading.Thread(
        target=_gravacao_a_segura, args=(equipe, contato, pronto, liberar, erros)
    )
    thread_a.start()
    assert pronto.wait(timeout=5)

    def gravacao_b_sem_lock():
        session = SessionLocal()
        try:
            session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"),
                {"t": equipe["tenant"]},
            )
            travada = ConversaTravada(
                id=0,
                tenant_id=equipe["tenant"],
                contato_telefone=contato,
                estado_conversa="idle",
                session=session,
            )
            saida_b["agendamento"] = _criar(travada, equipe)
            session.commit()
        except Exception as erro:  # noqa: BLE001 - repassado para a thread principal
            session.rollback()
            saida_b["erro"] = erro
        finally:
            session.close()

    thread_b = threading.Thread(target=gravacao_b_sem_lock)
    thread_b.start()
    _esperar_bloqueio()
    liberar.set()
    thread_a.join(timeout=10)
    thread_b.join(timeout=10)

    assert erros == [] and "erro" not in saida_b, (erros, saida_b)
    ativos = agendamentos(equipe["tenant"], status="agendado")
    assert len(ativos) == 1
    assert saida_b["agendamento"].id == ativos[0].id
