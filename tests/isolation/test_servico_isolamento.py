"""Isolamento entre clinicas no servico de agendamento (tarefa 5.3, regra 6).

Pendencia registrada pelo rls-reviewer na 5.2: quando o servico carrega
agendamentos, regras e expediente do banco, nada de outra clinica pode influir na
decisao nem vazar na resposta.

As duas clinicas usam o MESMO telefone de contato, para o vazamento aparecer se a
carga ignorar o tenant. Toda verificacao passa pelo servico, numa sessao
app_clinicas sob RLS (regra 19). A conta de administracao so semeia os dados e
confere o banco depois.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.agenda import servico
from app.agenda.agenda_propria import AgendaPropria
from app.agenda.base import AgendamentoNaoEncontrado
from app.agenda.regras import (
    ABRIR_HANDOFF,
    ServicoNaoOferecido,
    classificar_cancelamento,
)
from app.core.conversas import conversa_travada
from app.handoff.abertura import MOTIVO_CONFIGURACAO_INVALIDA, abrir_handoff
from tests.cenarios_etapa5 import (
    AGORA,
    agendamentos,
    configurar_handoff,
    handoffs,
    limpar,
    mensagem,
    semear,
)

UTC = timezone.utc
CONTATO = "(00) 90000-0601"

# Quarta 03/03 14:00 UTC: 11:00 em Sao Paulo e 10:00 em Manaus, dentro dos dois
# expedientes e com antecedencia valida nos dois cenarios
INICIO = datetime(2027, 3, 3, 14, tzinfo=UTC)


@pytest.fixture
def cenarios():
    dados = semear()
    yield dados
    limpar(dados)


def _resultado_criar(cenario, inicio=INICIO, prof=None, serv=None):
    with conversa_travada(cenario["tenant"], CONTATO) as travada:
        return servico.criar(
            travada,
            profissional_id=prof or cenario["prof"],
            servico_id=serv or cenario["serv"],
            inicio=inicio,
            agora=AGORA,
        )


def _criar(cenario, **kwargs):
    return _resultado_criar(cenario, **kwargs).agendamento


def test_mesmo_telefone_em_outra_clinica_nao_gera_duplicado(cenarios):
    solo = _criar(cenarios["solo"])
    equipe = _criar(cenarios["equipe"])

    assert equipe.id != solo.id
    assert equipe.tenant_id == cenarios["equipe"]["tenant"]
    assert len(agendamentos(cenarios["equipe"]["tenant"], status="agendado")) == 1
    assert len(agendamentos(cenarios["solo"]["tenant"], status="agendado")) == 1


def test_remarcar_para_horario_do_mesmo_telefone_em_outra_clinica_nao_e_duplicado(
    cenarios,
):
    """Na remarcacao a duplicidade conta qualquer profissional (C7 da rodada 4). O
    agendamento do mesmo telefone em outra clinica nao pode entrar nessa conta."""
    alheio = _criar(cenarios["solo"])
    # 49 h depois de AGORA: dentro da janela de 48 h e do expediente da equipe
    antigo = _criar(cenarios["equipe"], inicio=INICIO - timedelta(hours=1))

    with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
        resultado = servico.remarcar(
            travada, antigo.id, novo_inicio=INICIO, agora=AGORA
        )

    assert resultado.situacao == servico.REMARCADO
    assert resultado.novo.inicio == INICIO
    equipe = {
        linha.id: linha.status for linha in agendamentos(cenarios["equipe"]["tenant"])
    }
    assert equipe == {antigo.id: "cancelado", resultado.novo.id: "agendado"}
    linha = agendamentos(cenarios["solo"]["tenant"], id=alheio.id)[0]
    assert (linha.status, linha.inicio) == ("agendado", INICIO)


def test_carga_de_agendamentos_nao_ve_outra_clinica(cenarios):
    _criar(cenarios["solo"])
    janela = (INICIO - timedelta(hours=1), INICIO + timedelta(hours=2))
    with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
        por_contato = AgendaPropria().listar_ativos(
            travada.session, *janela, contato_telefone=CONTATO
        )
        todos = AgendaPropria().listar_ativos(travada.session, *janela)
    assert por_contato == []
    assert todos == []


def test_ocupacao_de_outra_clinica_nao_tira_horario_da_disponibilidade(cenarios):
    """Regressao de regra, nao prova de isolamento: listar_ativos ja filtra pelo
    profissional da equipe, e o agendamento da outra clinica e de outro profissional.
    A prova de que a carga nao ve outra clinica esta no teste anterior, sem filtro."""
    _criar(cenarios["solo"])
    with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
        livres = servico.disponibilidade(
            travada,
            profissional_id=cenarios["equipe"]["prof"],
            servico_id=cenarios["equipe"]["serv"],
            dia=date(2027, 3, 3),
            agora=AGORA,
        )
    assert INICIO in livres.horarios


def test_cancelar_ou_remarcar_id_de_outra_clinica_nao_encontra(cenarios):
    alheio = _criar(cenarios["solo"])
    with pytest.raises(AgendamentoNaoEncontrado):
        with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
            servico.cancelar(travada, alheio.id, agora=AGORA)
    with pytest.raises(AgendamentoNaoEncontrado):
        with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
            servico.remarcar(
                travada,
                alheio.id,
                novo_inicio=INICIO + timedelta(hours=1),
                agora=AGORA,
            )
    linha = agendamentos(cenarios["solo"]["tenant"], id=alheio.id)[0]
    assert (linha.status, linha.inicio) == ("agendado", INICIO)
    # Nenhum handoff referencia o agendamento alheio, nem no cancelar nem no remarcar
    assert handoffs(cenarios["equipe"]["tenant"]) == []
    assert handoffs(cenarios["solo"]["tenant"]) == []


@pytest.mark.parametrize("trocar", [("prof",), ("serv",), ("prof", "serv")])
def test_profissional_ou_servico_de_outra_clinica_nao_e_oferecido(cenarios, trocar):
    """Com os dois ids da outra clinica, o par existe la. Sem o tenant, _duracao o
    acharia e o agendamento seria gravado: e o caso que prova o isolamento. Os pares
    misturados nao existem em clinica nenhuma e cobrem so a regra."""
    equipe, solo = cenarios["equipe"], cenarios["solo"]
    ids = {"prof": equipe["prof"], "serv": equipe["serv"]}
    ids.update({chave: solo[chave] for chave in trocar})
    with pytest.raises(ServicoNaoOferecido):
        _criar(equipe, prof=ids["prof"], serv=ids["serv"])
    assert agendamentos(equipe["tenant"]) == []
    assert agendamentos(solo["tenant"]) == []


def test_clinica_sem_regras_nao_usa_as_regras_de_outra(cenarios):
    """Com as regras de outra clinica, o servico criaria e listaria horarios. Sem
    regras, abre handoff na propria clinica e em nenhuma outra."""
    sem = cenarios["sem_cadastro"]
    resultado = _resultado_criar(sem)
    with conversa_travada(sem["tenant"], CONTATO) as travada:
        disponivel = servico.disponibilidade(
            travada,
            profissional_id=sem["prof"],
            servico_id=sem["serv"],
            dia=date(2027, 3, 3),
            agora=AGORA,
        )
    assert (resultado.situacao, resultado.agendamento) == (
        servico.AGUARDA_HANDOFF,
        None,
    )
    assert (disponivel.situacao, disponivel.horarios) == (servico.AGUARDA_HANDOFF, [])
    assert agendamentos(sem["tenant"]) == []
    assert [linha.motivo for linha in handoffs(sem["tenant"])] == [
        MOTIVO_CONFIGURACAO_INVALIDA,
        MOTIVO_CONFIGURACAO_INVALIDA,
    ]
    assert handoffs(cenarios["equipe"]["tenant"]) == []
    assert handoffs(cenarios["solo"]["tenant"]) == []


def test_disponibilidade_com_profissional_e_servico_de_outra_clinica(cenarios):
    """O par existe na outra clinica. Sem o tenant, a grade dela seria devolvida."""
    with pytest.raises(ServicoNaoOferecido):
        with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
            servico.disponibilidade(
                travada,
                profissional_id=cenarios["solo"]["prof"],
                servico_id=cenarios["solo"]["serv"],
                dia=date(2027, 3, 3),
                agora=AGORA,
            )


def test_expediente_de_outra_clinica_nao_aparece(cenarios):
    with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
        alheio = AgendaPropria().expediente(travada.session, cenarios["solo"]["prof"])
        proprio = AgendaPropria().expediente(
            travada.session, cenarios["equipe"]["prof"]
        )
    assert alheio == []
    assert proprio  # controle positivo: a leitura funciona para a propria clinica


# --- handoffs (tarefa 5.4) --------------------------------------------------------


def _handoffs_vistos(tenant):
    """Handoffs que a sessao app_clinicas da clinica enxerga, sob RLS."""
    with conversa_travada(tenant, CONTATO) as travada:
        return travada.session.execute(text("SELECT id FROM handoffs")).scalars().all()


def test_handoff_de_uma_clinica_nao_e_visto_pela_outra(cenarios):
    equipe, solo = cenarios["equipe"], cenarios["solo"]
    with conversa_travada(equipe["tenant"], CONTATO) as travada:
        aberto = abrir_handoff(travada, MOTIVO_CONFIGURACAO_INVALIDA, agora=AGORA)

    assert _handoffs_vistos(solo["tenant"]) == []
    assert _handoffs_vistos(equipe["tenant"]) == [aberto.id]  # controle positivo


def test_configuracao_do_handoff_vem_da_propria_clinica(cenarios):
    """As duas clinicas tem configuracao diferente. Sem o tenant, a leitura poderia
    pegar o plantao, o texto ou o prazo da outra."""
    equipe, solo = cenarios["equipe"], cenarios["solo"]
    configurar_handoff(solo["tenant"], plantao="(00) 3000-0602", texto="Solo.", prazo=60)
    configurar_handoff(equipe["tenant"], plantao="(00) 3000-0601", texto="Equipe.")

    with conversa_travada(equipe["tenant"], CONTATO) as travada:
        aberto = abrir_handoff(travada, MOTIVO_CONFIGURACAO_INVALIDA, agora=AGORA)

    linha = handoffs(equipe["tenant"])[0]
    assert (linha.notificado_para, linha.texto_paciente, linha.responder_ate) == (
        "(00) 3000-0601",
        "Equipe.",
        None,
    )
    assert aberto.texto_paciente == "Equipe."
    assert handoffs(solo["tenant"]) == []


@pytest.mark.parametrize("referencia", ["agendamento_id", "mensagem_id"])
def test_handoff_nao_referencia_agendamento_ou_mensagem_de_outra_clinica(
    cenarios, referencia
):
    """O id existe na outra clinica. A FK composta (ADR 0007) recusa a referencia,
    mesmo pela abertura de handoff."""
    equipe, solo = cenarios["equipe"], cenarios["solo"]
    alheios = {
        "agendamento_id": _criar(solo).id,
        "mensagem_id": mensagem(solo["tenant"], CONTATO),
    }
    with pytest.raises(IntegrityError) as erro:
        with conversa_travada(equipe["tenant"], CONTATO) as travada:
            abrir_handoff(
                travada,
                MOTIVO_CONFIGURACAO_INVALIDA,
                agora=AGORA,
                **{referencia: alheios[referencia]},
            )
    assert erro.value.orig.pgcode == "23503"
    assert handoffs(equipe["tenant"]) == []
    assert handoffs(solo["tenant"]) == []


def test_cancelar_id_de_outra_clinica_nao_abre_handoff(cenarios):
    """Fora da janela na equipe, mas o agendamento e do solo: nao e encontrado, e
    nenhum handoff referencia o agendamento alheio."""
    # Terca 02/03 14:00 UTC, 10:00 em Manaus: 26 h depois de AGORA, dentro da
    # antecedencia e do expediente do solo, e fora da janela da equipe
    inicio = datetime(2027, 3, 2, 14, tzinfo=UTC)
    with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
        janela, politica = travada.session.execute(
            text(
                "SELECT janela_cancelamento_horas, politica_cancelamento_fora_janela "
                "FROM regras_agendamento"
            )
        ).one()
    # Controle: com as regras da propria equipe, este pedido abriria handoff. Se o
    # cenario mudar e o horario voltar para dentro da janela, o teste falha aqui.
    assert classificar_cancelamento(AGORA, inicio, janela, politica) == ABRIR_HANDOFF

    alheio = _criar(cenarios["solo"], inicio=inicio)
    with pytest.raises(AgendamentoNaoEncontrado):
        with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
            servico.cancelar(travada, alheio.id, agora=AGORA)
    linha = agendamentos(cenarios["solo"]["tenant"], id=alheio.id)[0]
    assert (linha.status, linha.inicio) == ("agendado", inicio)
    assert handoffs(cenarios["equipe"]["tenant"]) == []
    assert handoffs(cenarios["solo"]["tenant"]) == []
