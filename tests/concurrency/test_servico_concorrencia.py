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
from app.agenda.agenda_propria import AgendaPropria
from app.agenda.regras import AgendamentoDuplicado, HorarioIndisponivel
from app.core.conversas import ConversaTravada, conversa_travada
from app.db.database import SessionLocal
from tests.cenarios_etapa5 import AGORA, agendamentos, engine_admin, limpar, semear
from tests.concurrency.prazos import (
    ESPERA_LOCK,
    ESPERA_LIBERAR,
    ESPERA_SINAL,
    PIOR_CASO_GRAVACAO,
    SEGURA_ANTES_DO_COMMIT,
    juntar,
    limite_pytest,
)

UTC = timezone.utc
# Terca 02/03 10:00 em Sao Paulo
INICIO = datetime(2027, 3, 2, 13, tzinfo=UTC)

# Prazos (tests/concurrency/prazos.py). Varios contatos: lock da conversa, largada
# antes do INSERT, gravacao com as tentativas e a vencedora segurando o commit.
PRAZO_VARIOS = ESPERA_SINAL + ESPERA_LOCK + PIOR_CASO_GRAVACAO + SEGURA_ANTES_DO_COMMIT
# A e B: A chegou, B esperando na constraint, e a gravacao de B com as tentativas.
PRAZO_A_B = ESPERA_LIBERAR + PIOR_CASO_GRAVACAO


@pytest.fixture
def cenarios():
    dados = semear()
    yield dados
    limpar(dados)


def _criar(travada, equipe, inicio=INICIO, agenda=None):
    return servico.criar(
        travada,
        profissional_id=equipe["prof"],
        servico_id=equipe["serv"],
        inicio=inicio,
        agora=AGORA,
        agenda=agenda,
    ).agendamento


class _AgendaComLargada(AgendaPropria):
    """Solta as threads juntas logo antes do lock da agenda e do INSERT.

    A disputa que o lock do ADR 0011 resolve esta no INSERT. Uma largada no inicio
    da operacao deixa as threads chegarem espalhadas ao INSERT, e o teste passaria
    tambem sem o lock. So a primeira gravacao de cada thread espera: uma nova
    tentativa depois de um 40P01 nao pode ficar presa na largada.
    """

    def __init__(self, total):
        self._largada = threading.Barrier(total)
        self._ja_largou = threading.local()

    def criar(self, session, **campos):
        if not getattr(self._ja_largou, "valor", False):
            self._ja_largou.valor = True
            self._largada.wait(timeout=ESPERA_SINAL)
        return super().criar(session, **campos)


def _esperar_bloqueio(timeout=ESPERA_SINAL):
    """Espera ate alguma transacao estar parada esperando outra (lock nao concedido)."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        with engine_admin.connect() as conexao:
            if conexao.execute(
                text(
                    "SELECT count(*) FROM pg_locks "
                    "WHERE NOT granted AND locktype IN ('transactionid', 'advisory')"
                )
            ).scalar():
                return
        time.sleep(0.02)
    raise AssertionError("a segunda gravacao nao chegou a esperar a primeira")


@pytest.mark.timeout(limite_pytest(PRAZO_VARIOS))
def test_varios_contatos_pelo_mesmo_horario_so_um_vence(cenarios):
    equipe = cenarios["equipe"]
    total = 4
    agenda = _AgendaComLargada(total)
    resultados = []
    trava = threading.Lock()

    def pedir(indice):
        contato = f"(00) 90000-07{indice:02d}"
        try:
            with conversa_travada(equipe["tenant"], contato) as travada:
                _criar(travada, equipe, agenda=agenda)
                time.sleep(SEGURA_ANTES_DO_COMMIT)
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
    vivas = juntar(threads, PRAZO_VARIOS)

    assert not vivas, (vivas, resultados)
    assert sorted(resultados) == ["aceito"] + ["indisponivel"] * (total - 1), resultados
    assert len(agendamentos(equipe["tenant"], status="agendado")) == 1


# Sexta 05/03 em Sao Paulo, 10:00 a 11:30: fora da janela de 48 h a partir de AGORA
INICIOS_ANTIGOS = [datetime(2027, 3, 5, 13, tzinfo=UTC) + timedelta(minutes=30 * i) for i in range(4)]


@pytest.mark.timeout(limite_pytest(PRAZO_VARIOS))
def test_varios_contatos_remarcando_para_o_mesmo_horario_so_um_vence(cenarios):
    """Remarcacao concorrente (ADR 0011): cada contato tem a propria consulta e todos
    pedem o mesmo novo horario. So um remarca, os outros recebem HorarioIndisponivel
    e as consultas antigas deles continuam agendadas."""
    equipe = cenarios["equipe"]
    total = len(INICIOS_ANTIGOS)
    contatos = [f"(00) 90000-09{indice:02d}" for indice in range(total)]
    antigos = {}
    for contato, inicio in zip(contatos, INICIOS_ANTIGOS):
        with conversa_travada(equipe["tenant"], contato) as travada:
            antigos[contato] = _criar(travada, equipe, inicio).id

    agenda = _AgendaComLargada(total)
    resultados = {}
    trava = threading.Lock()

    def remarcar(contato):
        try:
            with conversa_travada(equipe["tenant"], contato) as travada:
                resultado = servico.remarcar(
                    travada,
                    antigos[contato],
                    novo_inicio=INICIO,
                    agora=AGORA,
                    agenda=agenda,
                ).situacao
                time.sleep(SEGURA_ANTES_DO_COMMIT)
        except HorarioIndisponivel:
            resultado = "indisponivel"
        except Exception as erro:  # noqa: BLE001 - registrado para a assercao mostrar
            resultado = f"{type(erro).__name__}: {getattr(getattr(erro, 'orig', None), 'pgcode', '')}"
        with trava:
            resultados[contato] = resultado

    threads = [threading.Thread(target=remarcar, args=(c,)) for c in contatos]
    for thread in threads:
        thread.start()
    vivas = juntar(threads, PRAZO_VARIOS)

    assert not vivas, (vivas, resultados)
    assert sorted(resultados.values()) == sorted(
        [servico.REMARCADO] + ["indisponivel"] * (total - 1)
    ), resultados
    linhas = {linha.id: linha for linha in agendamentos(equipe["tenant"])}
    for contato, situacao in resultados.items():
        esperado = "cancelado" if situacao == servico.REMARCADO else "agendado"
        assert linhas[antigos[contato]].status == esperado, (contato, resultados)
    novos = [
        linha
        for linha in agendamentos(equipe["tenant"], status="agendado")
        if linha.inicio == INICIO
    ]
    assert len(novos) == 1


@pytest.mark.timeout(limite_pytest(PRAZO_A_B))
def test_lock_de_um_profissional_nao_bloqueia_outro(cenarios):
    """A segura o lock da agenda de prof. B grava o mesmo horario com prof2 sem esperar."""
    equipe = cenarios["equipe"]
    pronto, liberar, erros = threading.Event(), threading.Event(), []
    thread_a = threading.Thread(
        target=_gravacao_a_segura,
        args=(equipe, "(00) 90000-0805", pronto, liberar, erros),
    )
    thread_a.start()
    try:
        assert pronto.wait(timeout=ESPERA_SINAL)
        # Com lock por clinica, B esperaria A ate o lock_timeout e falharia
        with conversa_travada(equipe["tenant"], "(00) 90000-0806") as travada:
            outro = servico.criar(
                travada,
                profissional_id=equipe["prof2"],
                servico_id=equipe["serv"],
                inicio=INICIO,
                agora=AGORA,
            ).agendamento
        assert thread_a.is_alive(), "A deveria continuar segurando o lock"
    finally:
        liberar.set()
    vivas = juntar([thread_a], PRAZO_A_B)

    assert not vivas and erros == [], (vivas, erros)
    assert outro.profissional_id == equipe["prof2"]
    assert len(agendamentos(equipe["tenant"], status="agendado")) == 2


def _gravacao_a_segura(equipe, contato, pronto, liberar, erros):
    """A grava e segura a transacao aberta ate o sinal de liberar."""
    try:
        with conversa_travada(equipe["tenant"], contato) as travada:
            _criar(travada, equipe)
            pronto.set()
            assert liberar.wait(timeout=ESPERA_LIBERAR)
    except Exception as erro:  # noqa: BLE001 - repassado para a thread principal
        erros.append(erro)
        pronto.set()


@pytest.mark.timeout(limite_pytest(PRAZO_A_B))
def test_23p01_vira_indisponivel_e_a_transacao_segue(cenarios):
    equipe = cenarios["equipe"]
    pronto, liberar, erros, saida_b = threading.Event(), threading.Event(), [], {}
    thread_a = threading.Thread(
        target=_gravacao_a_segura,
        args=(equipe, "(00) 90000-0801", pronto, liberar, erros),
    )
    thread_a.start()
    assert pronto.wait(timeout=ESPERA_SINAL)

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
    vivas = juntar([thread_a, thread_b], PRAZO_A_B)

    assert not vivas, (vivas, erros, saida_b)
    assert erros == [] and "erro" not in saida_b, (erros, saida_b)
    assert saida_b["primeira"] == "indisponivel"
    ativos = agendamentos(equipe["tenant"], status="agendado")
    assert sorted(linha.inicio for linha in ativos) == [
        INICIO,
        INICIO + timedelta(hours=1),
    ]


@pytest.mark.timeout(limite_pytest(PRAZO_A_B))
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
    assert pronto.wait(timeout=ESPERA_SINAL)

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
    vivas = juntar([thread_a, thread_b], PRAZO_A_B)

    assert not vivas, (vivas, erros, saida_b)
    assert erros == [] and "erro" not in saida_b, (erros, saida_b)
    ativos = agendamentos(equipe["tenant"], status="agendado")
    assert len(ativos) == 1
    assert saida_b["agendamento"].id == ativos[0].id


@pytest.mark.timeout(limite_pytest(PRAZO_A_B))
def test_remarcacao_na_corrida_para_horario_do_contato_e_duplicado(cenarios):
    """Remarcacao que recebe 23P01 contra um agendamento do proprio contato (C7).

    Igual a verificacao previa: AgendamentoDuplicado, e o SAVEPOINT da remarcacao
    desfaz o cancelamento do antigo. B roda por fora do lock da conversa, como em
    test_pedido_repetido_na_corrida_devolve_o_existente, para chegar ao 23P01.
    """
    equipe = cenarios["equipe"]
    contato = "(00) 90000-0804"
    # Sexta 05/03 10:00 em Sao Paulo: 97 h depois de AGORA, dentro da janela de 48 h
    with conversa_travada(equipe["tenant"], contato) as travada:
        antigo = _criar(travada, equipe, datetime(2027, 3, 5, 13, tzinfo=UTC))

    pronto, liberar, erros, saida_b = threading.Event(), threading.Event(), [], {}
    thread_a = threading.Thread(
        target=_gravacao_a_segura, args=(equipe, contato, pronto, liberar, erros)
    )
    thread_a.start()
    assert pronto.wait(timeout=ESPERA_SINAL)

    def remarcacao_b_sem_lock():
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
            try:
                servico.remarcar(travada, antigo.id, novo_inicio=INICIO, agora=AGORA)
                saida_b["resultado"] = "remarcado"
            except AgendamentoDuplicado:
                saida_b["resultado"] = "duplicado"
            # A transacao segue utilizavel: o commit confirma o que sobrou dela
            session.commit()
        except Exception as erro:  # noqa: BLE001 - repassado para a thread principal
            session.rollback()
            saida_b["erro"] = erro
        finally:
            session.close()

    thread_b = threading.Thread(target=remarcacao_b_sem_lock)
    thread_b.start()
    _esperar_bloqueio()
    liberar.set()
    vivas = juntar([thread_a, thread_b], PRAZO_A_B)

    assert not vivas, (vivas, erros, saida_b)
    assert erros == [] and "erro" not in saida_b, (erros, saida_b)
    assert saida_b["resultado"] == "duplicado"
    linhas = {linha.id: linha for linha in agendamentos(equipe["tenant"])}
    assert linhas[antigo.id].status == "agendado"
    ativos = agendamentos(equipe["tenant"], status="agendado")
    assert sorted(linha.inicio for linha in ativos) == [
        INICIO,
        datetime(2027, 3, 5, 13, tzinfo=UTC),
    ]
