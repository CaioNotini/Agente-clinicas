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

from app.agenda import servico
from app.agenda.agenda_propria import AgendaPropria
from app.agenda.base import AgendamentoNaoEncontrado
from app.agenda.regras import ConfiguracaoInvalida, ServicoNaoOferecido
from app.core.conversas import conversa_travada
from tests.cenarios_etapa5 import AGORA, agendamentos, limpar, semear

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


def _criar(cenario, inicio=INICIO, prof=None, serv=None):
    with conversa_travada(cenario["tenant"], CONTATO) as travada:
        return servico.criar(
            travada,
            profissional_id=prof or cenario["prof"],
            servico_id=serv or cenario["serv"],
            inicio=inicio,
            agora=AGORA,
        )


def test_mesmo_telefone_em_outra_clinica_nao_gera_duplicado(cenarios):
    solo = _criar(cenarios["solo"])
    equipe = _criar(cenarios["equipe"])

    assert equipe.id != solo.id
    assert equipe.tenant_id == cenarios["equipe"]["tenant"]
    assert len(agendamentos(cenarios["equipe"]["tenant"], status="agendado")) == 1
    assert len(agendamentos(cenarios["solo"]["tenant"], status="agendado")) == 1


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
    _criar(cenarios["solo"])
    with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
        livres = servico.disponibilidade(
            travada,
            profissional_id=cenarios["equipe"]["prof"],
            servico_id=cenarios["equipe"]["serv"],
            dia=date(2027, 3, 3),
            agora=AGORA,
        )
    assert INICIO in livres


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


@pytest.mark.parametrize("trocar", ["prof", "serv"])
def test_profissional_ou_servico_de_outra_clinica_nao_e_oferecido(cenarios, trocar):
    equipe, solo = cenarios["equipe"], cenarios["solo"]
    ids = {"prof": equipe["prof"], "serv": equipe["serv"], trocar: solo[trocar]}
    with pytest.raises(ServicoNaoOferecido):
        _criar(equipe, prof=ids["prof"], serv=ids["serv"])
    assert agendamentos(equipe["tenant"]) == []
    assert agendamentos(solo["tenant"]) == []


def test_clinica_sem_regras_nao_usa_as_regras_de_outra(cenarios):
    with pytest.raises(ConfiguracaoInvalida):
        _criar(cenarios["sem_cadastro"])
    with pytest.raises(ConfiguracaoInvalida):
        with conversa_travada(cenarios["sem_cadastro"]["tenant"], CONTATO) as travada:
            servico.disponibilidade(
                travada,
                profissional_id=cenarios["sem_cadastro"]["prof"],
                servico_id=cenarios["sem_cadastro"]["serv"],
                dia=date(2027, 3, 3),
                agora=AGORA,
            )


def test_disponibilidade_com_profissional_de_outra_clinica_nao_e_oferecida(cenarios):
    """O expediente de outra clinica nao aparece pela sessao desta."""
    with pytest.raises(ServicoNaoOferecido):
        with conversa_travada(cenarios["equipe"]["tenant"], CONTATO) as travada:
            servico.disponibilidade(
                travada,
                profissional_id=cenarios["solo"]["prof"],
                servico_id=cenarios["equipe"]["serv"],
                dia=date(2027, 3, 3),
                agora=AGORA,
            )
