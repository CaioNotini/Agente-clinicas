"""Servico de agendamento da tarefa 5.3 nos dois cenarios (ADR 0004 e ADR 0009).

Cada operacao roda dentro de conversa_travada, numa sessao app_clinicas, como no
worker. O contato sai da conversa travada. Os dados de apoio e as assercoes sobre
o banco usam a conta de administracao (tests/cenarios_etapa5.py).

Ver os cenarios em tests/cenarios_etapa5.py. Sao Paulo e UTC-3 e Manaus e UTC-4.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.agenda import servico
from app.agenda.agenda_propria import AgendaPropria
from app.agenda.base import AgendamentoNaoEncontrado
from app.agenda.regras import (
    AgendamentoDuplicado,
    AntecedenciaInsuficiente,
    ConfiguracaoInvalida,
    ForaDoExpediente,
    HorarioIndisponivel,
    ServicoNaoOferecido,
)
from app.core.conversas import conversa_travada
from tests.cenarios_etapa5 import AGORA, agendamentos, limpar, semear

UTC = timezone.utc
CONTATO = "(00) 90000-0501"
OUTRO_CONTATO = "(00) 90000-0502"
SP = "America/Sao_Paulo"


def _sp(dia, hora, minuto=0):
    """Horario de parede em Sao Paulo, como instante UTC."""
    return datetime(2027, 3, dia, hora, minuto, tzinfo=UTC) + timedelta(hours=3)


def _mn(dia, hora, minuto=0):
    """Horario de parede em Manaus, como instante UTC."""
    return datetime(2027, 3, dia, hora, minuto, tzinfo=UTC) + timedelta(hours=4)


T_EQUIPE = _sp(2, 10)  # terca 10:00, 25 h depois de AGORA
T_EQUIPE_LONGE = _sp(5, 10)  # sexta 10:00, 97 h depois de AGORA
T_SOLO = _mn(3, 10)  # quarta 10:00, 50 h depois de AGORA


@pytest.fixture
def cenarios():
    dados = semear()
    yield dados
    limpar(dados)


def _criar(cenario, contato, inicio, *, prof="prof", serv="serv", agora=AGORA):
    with conversa_travada(cenario["tenant"], contato) as travada:
        return servico.criar(
            travada,
            profissional_id=cenario[prof],
            servico_id=cenario[serv],
            inicio=inicio,
            agora=agora,
        )


def _cancelar(cenario, contato, agendamento_id, agora):
    with conversa_travada(cenario["tenant"], contato) as travada:
        return servico.cancelar(travada, agendamento_id, agora=agora)


def _remarcar(cenario, contato, agendamento_id, novo_inicio, agora=AGORA):
    with conversa_travada(cenario["tenant"], contato) as travada:
        return servico.remarcar(
            travada, agendamento_id, novo_inicio=novo_inicio, agora=agora
        )


def _disponibilidade(cenario, dia, *, prof="prof", agora=AGORA):
    with conversa_travada(cenario["tenant"], CONTATO) as travada:
        return servico.disponibilidade(
            travada,
            profissional_id=cenario[prof],
            servico_id=cenario["serv"],
            dia=dia,
            agora=agora,
        )


# --- criar ------------------------------------------------------------------------


def test_criar_nos_dois_cenarios_usa_a_duracao_de_cada_um(cenarios):
    equipe = _criar(cenarios["equipe"], CONTATO, T_EQUIPE)
    solo = _criar(cenarios["solo"], CONTATO, T_SOLO)

    assert (equipe.fim - equipe.inicio, equipe.status) == (
        timedelta(minutes=30),
        "agendado",
    )
    assert solo.fim - solo.inicio == timedelta(minutes=60)  # override do profissional
    assert equipe.contato_telefone == CONTATO
    assert len(agendamentos(cenarios["equipe"]["tenant"])) == 1
    assert len(agendamentos(cenarios["solo"]["tenant"])) == 1


def test_pedido_repetido_devolve_o_existente(cenarios):
    primeiro = _criar(cenarios["equipe"], CONTATO, T_EQUIPE)
    segundo = _criar(cenarios["equipe"], CONTATO, T_EQUIPE)

    assert segundo.id == primeiro.id
    assert len(agendamentos(cenarios["equipe"]["tenant"])) == 1


def test_pedido_repetido_vale_mesmo_fora_da_antecedencia(cenarios):
    # O pedido repetido nao cria nada, entao a antecedencia nao se aplica a ele
    primeiro = _criar(cenarios["equipe"], CONTATO, T_EQUIPE)
    depois = T_EQUIPE - timedelta(minutes=30)
    assert _criar(cenarios["equipe"], CONTATO, T_EQUIPE, agora=depois).id == primeiro.id


def test_outro_horario_sobreposto_do_mesmo_contato_e_duplicado(cenarios):
    _criar(cenarios["equipe"], CONTATO, T_EQUIPE)
    with pytest.raises(AgendamentoDuplicado):
        _criar(
            cenarios["equipe"], CONTATO, T_EQUIPE + timedelta(minutes=15), prof="prof2"
        )
    # Com o mesmo profissional tambem: a duplicidade vem antes do conflito na ordem
    # da secao 7 da arquitetura, entao o contato nao recebe HorarioIndisponivel
    with pytest.raises(AgendamentoDuplicado):
        _criar(cenarios["equipe"], CONTATO, T_EQUIPE + timedelta(minutes=15))
    assert len(agendamentos(cenarios["equipe"]["tenant"])) == 1


def test_mesmo_profissional_ocupado_por_outro_contato_e_indisponivel(cenarios):
    _criar(cenarios["equipe"], CONTATO, T_EQUIPE)
    with pytest.raises(HorarioIndisponivel):
        _criar(cenarios["equipe"], OUTRO_CONTATO, T_EQUIPE + timedelta(minutes=15))


def test_regras_da_clinica_aplicadas_em_cada_cenario(cenarios):
    inicio = datetime(2027, 3, 1, 17, tzinfo=UTC)  # 5 h depois de AGORA
    _criar(cenarios["equipe"], CONTATO, inicio)
    with pytest.raises(AntecedenciaInsuficiente):
        _criar(cenarios["solo"], CONTATO, inicio)
    with pytest.raises(ForaDoExpediente):
        _criar(cenarios["equipe"], OUTRO_CONTATO, _sp(2, 12, 30))  # almoco


@pytest.mark.parametrize(
    "prof,serv", [("prof", "serv_outro"), ("prof_inativo", "serv")]
)
def test_servico_nao_oferecido(cenarios, prof, serv):
    with pytest.raises(ServicoNaoOferecido):
        _criar(cenarios["equipe"], CONTATO, T_EQUIPE, prof=prof, serv=serv)
    assert agendamentos(cenarios["equipe"]["tenant"]) == []


def test_clinica_sem_regras_e_configuracao_invalida(cenarios):
    with pytest.raises(ConfiguracaoInvalida):
        _criar(cenarios["sem_cadastro"], CONTATO, T_EQUIPE)


def test_profissional_sem_expediente_e_configuracao_invalida(cenarios):
    with pytest.raises(ConfiguracaoInvalida):
        _criar(cenarios["equipe"], CONTATO, T_EQUIPE, prof="prof_sem_expediente")
    with pytest.raises(ConfiguracaoInvalida):
        _disponibilidade(
            cenarios["equipe"], date(2027, 3, 2), prof="prof_sem_expediente"
        )


def test_transacao_continua_utilizavel_depois_de_regra_violada(cenarios):
    equipe = cenarios["equipe"]
    with conversa_travada(equipe["tenant"], CONTATO) as travada:
        servico.criar(
            travada,
            profissional_id=equipe["prof"],
            servico_id=equipe["serv"],
            inicio=T_EQUIPE,
            agora=AGORA,
        )
        with pytest.raises(AgendamentoDuplicado):
            servico.criar(
                travada,
                profissional_id=equipe["prof2"],
                servico_id=equipe["serv"],
                inicio=T_EQUIPE,
                agora=AGORA,
            )
        servico.criar(
            travada,
            profissional_id=equipe["prof"],
            servico_id=equipe["serv"],
            inicio=T_EQUIPE + timedelta(hours=1),
            agora=AGORA,
        )
    assert len(agendamentos(equipe["tenant"], status="agendado")) == 2


# --- cancelar ---------------------------------------------------------------------


def test_cancelamento_por_cenario_e_antecedencia(cenarios):
    equipe, solo = cenarios["equipe"], cenarios["solo"]

    # Equipe, 25 h antes com janela de 48 h e politica handoff: nada muda
    ag = _criar(equipe, CONTATO, T_EQUIPE)
    resultado = _cancelar(equipe, CONTATO, ag.id, AGORA)
    assert resultado.situacao == servico.AGUARDA_HANDOFF
    assert agendamentos(equipe["tenant"], id=ag.id)[0].status == "agendado"

    # Equipe, 50 h antes: cancelamento normal
    resultado = _cancelar(equipe, CONTATO, ag.id, T_EQUIPE - timedelta(hours=50))
    assert resultado.situacao == servico.CANCELADO
    linha = agendamentos(equipe["tenant"], id=ag.id)[0]
    assert (linha.status, linha.cancelado_fora_da_janela) == ("cancelado", False)

    # Solo, 30 h antes com janela de 24 h: cancelamento normal
    ag = _criar(solo, CONTATO, T_SOLO)
    assert _cancelar(solo, CONTATO, ag.id, T_SOLO - timedelta(hours=30)).situacao == (
        servico.CANCELADO
    )

    # Solo, 12 h antes com aceitar_e_marcar: cancela e marca tardio
    ag = _criar(solo, OUTRO_CONTATO, T_SOLO)
    resultado = _cancelar(solo, OUTRO_CONTATO, ag.id, T_SOLO - timedelta(hours=12))
    assert resultado.situacao == servico.CANCELADO_TARDIO
    linha = agendamentos(solo["tenant"], id=ag.id)[0]
    assert (linha.status, linha.cancelado_fora_da_janela) == ("cancelado", True)


def test_cancelar_agendamento_de_outro_contato_cancelado_ou_inexistente(cenarios):
    equipe = cenarios["equipe"]
    ag = _criar(equipe, CONTATO, T_EQUIPE_LONGE)
    with pytest.raises(AgendamentoNaoEncontrado):
        _cancelar(equipe, OUTRO_CONTATO, ag.id, AGORA)
    _cancelar(equipe, CONTATO, ag.id, AGORA)
    with pytest.raises(AgendamentoNaoEncontrado):
        _cancelar(equipe, CONTATO, ag.id, AGORA)
    with pytest.raises(AgendamentoNaoEncontrado):
        _cancelar(equipe, CONTATO, 2_000_000_000, AGORA)
    assert agendamentos(equipe["tenant"], id=ag.id)[0].status == "cancelado"


# --- remarcar ---------------------------------------------------------------------


def test_remarcar_dentro_da_janela(cenarios):
    equipe = cenarios["equipe"]
    antigo = _criar(equipe, CONTATO, T_EQUIPE_LONGE)
    resultado = _remarcar(
        equipe, CONTATO, antigo.id, T_EQUIPE_LONGE + timedelta(hours=1)
    )

    assert resultado.situacao == servico.REMARCADO
    assert resultado.novo.inicio == T_EQUIPE_LONGE + timedelta(hours=1)
    assert resultado.novo.profissional_id == antigo.profissional_id
    linhas = {linha.id: linha for linha in agendamentos(equipe["tenant"])}
    assert linhas[antigo.id].status == "cancelado"
    assert linhas[antigo.id].cancelado_fora_da_janela is False
    assert linhas[resultado.novo.id].status == "agendado"


def test_remarcar_fora_da_janela_com_handoff_nao_muda_nada(cenarios):
    equipe = cenarios["equipe"]
    antigo = _criar(equipe, CONTATO, T_EQUIPE)
    resultado = _remarcar(equipe, CONTATO, antigo.id, T_EQUIPE_LONGE)

    assert (resultado.situacao, resultado.novo) == (servico.AGUARDA_HANDOFF, None)
    assert [linha.status for linha in agendamentos(equipe["tenant"])] == ["agendado"]


def test_remarcar_fora_da_janela_com_aceitar_marca_o_antigo(cenarios):
    solo = cenarios["solo"]
    antigo = _criar(solo, CONTATO, T_SOLO)
    agora = T_SOLO - timedelta(hours=12)
    resultado = _remarcar(solo, CONTATO, antigo.id, _mn(4, 10), agora=agora)

    assert resultado.situacao == servico.REMARCADO
    linhas = {linha.id: linha for linha in agendamentos(solo["tenant"])}
    assert (linhas[antigo.id].status, linhas[antigo.id].cancelado_fora_da_janela) == (
        "cancelado",
        True,
    )
    assert linhas[resultado.novo.id].status == "agendado"


def test_remarcacao_que_falha_mantem_o_antigo(cenarios):
    equipe = cenarios["equipe"]
    antigo = _criar(equipe, CONTATO, T_EQUIPE_LONGE)
    _criar(equipe, OUTRO_CONTATO, T_EQUIPE_LONGE + timedelta(hours=1))

    with conversa_travada(equipe["tenant"], CONTATO) as travada:
        with pytest.raises(HorarioIndisponivel):
            servico.remarcar(
                travada,
                antigo.id,
                novo_inicio=T_EQUIPE_LONGE + timedelta(hours=1),
                agora=AGORA,
            )
        # A transacao segue e confirma: o cancelamento do antigo precisa ter sido desfeito

    assert [linha.status for linha in agendamentos(equipe["tenant"])] == [
        "agendado",
        "agendado",
    ]


def test_remarcar_para_o_mesmo_inicio_nao_muda_nada(cenarios):
    equipe = cenarios["equipe"]
    antigo = _criar(equipe, CONTATO, T_EQUIPE_LONGE)
    resultado = _remarcar(equipe, CONTATO, antigo.id, T_EQUIPE_LONGE)
    assert resultado.situacao == servico.INALTERADO
    assert [(linha.id, linha.status) for linha in agendamentos(equipe["tenant"])] == [
        (antigo.id, "agendado")
    ]


def test_remarcar_agendamento_de_outro_contato_nao_encontra(cenarios):
    equipe = cenarios["equipe"]
    antigo = _criar(equipe, CONTATO, T_EQUIPE_LONGE)
    with pytest.raises(AgendamentoNaoEncontrado):
        _remarcar(equipe, OUTRO_CONTATO, antigo.id, T_EQUIPE_LONGE + timedelta(hours=1))


# --- disponibilidade --------------------------------------------------------------


def _grade(dia, inicio_h, fim_h, minutos, local):
    """Inicios de inicio_h a fim_h (exclusivo do ultimo que nao cabe), em passos."""
    inicios, atual = [], local(dia, inicio_h)
    while atual + timedelta(minutes=minutos) <= local(dia, fim_h):
        inicios.append(atual)
        atual += timedelta(minutes=minutos)
    return inicios


def test_disponibilidade_da_equipe_tira_o_ocupado(cenarios):
    equipe = cenarios["equipe"]
    esperado = _grade(2, 8, 12, 30, _sp) + [
        _sp(2, 13, 30) + timedelta(minutes=30 * i) for i in range(9)
    ]
    assert _disponibilidade(equipe, date(2027, 3, 2)) == esperado

    _criar(equipe, OUTRO_CONTATO, T_EQUIPE)
    livres = _disponibilidade(equipe, date(2027, 3, 2))
    assert T_EQUIPE not in livres
    assert len(livres) == len(esperado) - 1


def test_disponibilidade_aplica_a_antecedencia_minima(cenarios):
    # Agora e terca 08:30 em Sao Paulo. Com 2 h de minima, o primeiro inicio e 10:30.
    agora = _sp(2, 8, 30)
    livres = _disponibilidade(cenarios["equipe"], date(2027, 3, 2), agora=agora)
    assert livres[0] == _sp(2, 10, 30)


def test_disponibilidade_de_domingo_e_vazia(cenarios):
    assert _disponibilidade(cenarios["equipe"], date(2027, 3, 7)) == []


def test_disponibilidade_do_solo_usa_o_override(cenarios):
    assert _disponibilidade(cenarios["solo"], date(2027, 3, 3)) == _grade(
        3, 9, 17, 60, _mn
    )


def test_disponibilidade_junta_faixas_contiguas(cenarios):
    # Quinta 08-12 e 12-14, 90 min: 11:00 a 12:30 atravessa a divisa das faixas
    livres = _disponibilidade(
        cenarios["equipe"], date(2027, 3, 4), prof="prof_contiguo"
    )
    assert livres == [_sp(4, 8), _sp(4, 9, 30), _sp(4, 11), _sp(4, 12, 30)]


def test_disponibilidade_sem_cadastro_e_configuracao_invalida(cenarios):
    with pytest.raises(ConfiguracaoInvalida):
        _disponibilidade(cenarios["sem_cadastro"], date(2027, 3, 2))


# --- provider: sem regras de negocio ----------------------------------------------


def test_provider_disponibilidade_ignora_a_antecedencia(cenarios):
    """O provider responde so expediente e ocupacao. A antecedencia e do servico."""
    equipe = cenarios["equipe"]
    with conversa_travada(equipe["tenant"], CONTATO) as travada:
        livres = AgendaPropria().disponibilidade(
            travada.session,
            profissional_id=equipe["prof"],
            dia=date(2027, 3, 1),
            duracao_minutos=30,
            fuso=SP,
        )
    assert livres[0] == _sp(1, 8)  # antes de AGORA, que e 09:00 em Sao Paulo
    assert _disponibilidade(equipe, date(2027, 3, 1))[0] == _sp(1, 11)


def test_provider_cancelar_marca_fora_da_janela(cenarios):
    equipe = cenarios["equipe"]
    ag = _criar(equipe, CONTATO, T_EQUIPE_LONGE)
    with conversa_travada(equipe["tenant"], CONTATO) as travada:
        cancelado = AgendaPropria().cancelar(
            travada.session, ag.id, fora_da_janela=True
        )
    assert cancelado.status == "cancelado"
    assert agendamentos(equipe["tenant"], id=ag.id)[0].cancelado_fora_da_janela is True


def test_provider_listar_ativos_e_obter(cenarios):
    equipe = cenarios["equipe"]
    a = _criar(equipe, CONTATO, T_EQUIPE_LONGE)
    b = _criar(equipe, OUTRO_CONTATO, T_EQUIPE_LONGE, prof="prof2")
    c = _criar(equipe, CONTATO, T_EQUIPE_LONGE + timedelta(hours=4))
    _cancelar(equipe, CONTATO, c.id, AGORA)
    agenda = AgendaPropria()
    janela = (T_EQUIPE_LONGE, T_EQUIPE_LONGE + timedelta(hours=5))
    with conversa_travada(equipe["tenant"], CONTATO) as travada:
        session = travada.session
        por_prof = agenda.listar_ativos(
            session, *janela, profissional_id=equipe["prof"]
        )
        por_contato = agenda.listar_ativos(session, *janela, contato_telefone=CONTATO)
        todos = agenda.listar_ativos(session, *janela)
        lido = agenda.obter(session, c.id)
        inexistente = agenda.obter(session, 2_000_000_000)
    assert [x.id for x in por_prof] == [a.id]
    assert [x.id for x in por_contato] == [a.id]
    assert sorted(x.id for x in todos) == sorted([a.id, b.id])
    assert (lido.id, lido.status) == (c.id, "cancelado")
    assert inexistente is None
