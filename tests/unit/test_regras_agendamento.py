"""Regras determinísticas da etapa 5: Q-21 duracao, Q-22 cancelamento (ADR 0009) e
as regras da tarefa 5.2 (antecedencia, expediente, conflito e duplicidade).

Funcoes puras, base do servico de agendamento (5.3). Nao tocam no banco. A
semantica de cada regra esta na secao 7 de docs/arquitetura.md.

2027-03-01 e uma segunda-feira. Em 2027, Sao Paulo e UTC-3 e Manaus e UTC-4, os dois
sem horario de verao.
"""
from datetime import datetime, time, timedelta, timezone

import pytest

from app.agenda.base import Agendamento
from app.agenda.regras import (
    ABRIR_HANDOFF,
    CANCELAR_TARDIO,
    DENTRO_JANELA,
    POLITICA_ACEITAR_E_MARCAR,
    POLITICA_HANDOFF,
    AgendamentoDuplicado,
    AntecedenciaExcedida,
    AntecedenciaInsuficiente,
    ConfiguracaoInvalida,
    FaixaExpediente,
    ForaDoExpediente,
    HorarioIndisponivel,
    HorarioNoPassado,
    MisturaDeTenants,
    RegrasClinica,
    RegraViolada,
    ServicoNaoOferecido,
    calcular_fim,
    classificar_cancelamento,
    faixas_do_dia,
    intervalos_conflitam,
    pedido_repetido,
    regras_da_clinica,
    resolver_duracao_minutos,
    validar_antecedencia,
    validar_expediente,
    verificar_conflito,
    verificar_duplicidade,
)

SP = "America/Sao_Paulo"
MANAUS = "America/Manaus"
UTC = timezone.utc

# --- Q-21 duracao -------------------------------------------------------------


def test_duracao_usa_servico_quando_nao_ha_override():
    assert resolver_duracao_minutos(30, None) == 30


def test_duracao_usa_override_do_profissional_quando_existe():
    assert resolver_duracao_minutos(30, 45) == 45


def test_override_zero_nao_e_tratado_como_ausente():
    # 0 e um valor explicito, diferente de None. A regra respeita o que foi gravado.
    assert resolver_duracao_minutos(30, 0) == 0


def test_calcular_fim_soma_a_duracao_ao_inicio():
    inicio = datetime(2027, 3, 1, 9, 0, tzinfo=timezone.utc)
    assert calcular_fim(inicio, 30) == inicio + timedelta(minutes=30)


# --- Q-22 cancelamento fora da janela -----------------------------------------

_AGORA = datetime(2027, 3, 1, 9, 0, tzinfo=timezone.utc)


def test_cancelamento_dentro_da_janela_e_normal():
    # Consulta daqui a 72h, janela de 48h: ha antecedencia suficiente
    inicio = _AGORA + timedelta(hours=72)
    assert (
        classificar_cancelamento(_AGORA, inicio, 48, POLITICA_HANDOFF) == DENTRO_JANELA
    )


def test_antecedencia_igual_a_janela_ainda_e_dentro():
    inicio = _AGORA + timedelta(hours=48)
    assert (
        classificar_cancelamento(_AGORA, inicio, 48, POLITICA_HANDOFF) == DENTRO_JANELA
    )


def test_fora_da_janela_com_politica_handoff_abre_handoff():
    inicio = _AGORA + timedelta(hours=12)
    assert (
        classificar_cancelamento(_AGORA, inicio, 48, POLITICA_HANDOFF) == ABRIR_HANDOFF
    )


def test_fora_da_janela_com_politica_aceitar_marca_tardio():
    inicio = _AGORA + timedelta(hours=12)
    assert (
        classificar_cancelamento(_AGORA, inicio, 48, POLITICA_ACEITAR_E_MARCAR)
        == CANCELAR_TARDIO
    )


def test_politica_desconhecida_levanta():
    inicio = _AGORA + timedelta(hours=12)
    with pytest.raises(ValueError):
        classificar_cancelamento(_AGORA, inicio, 48, "xyz")


def test_um_segundo_abaixo_da_janela_e_fora():
    inicio = _AGORA + timedelta(hours=48) - timedelta(seconds=1)
    assert (
        classificar_cancelamento(_AGORA, inicio, 48, POLITICA_HANDOFF) == ABRIR_HANDOFF
    )


def test_janela_nula_desliga_a_regra():
    inicio = _AGORA + timedelta(minutes=10)
    assert (
        classificar_cancelamento(_AGORA, inicio, None, POLITICA_HANDOFF)
        == DENTRO_JANELA
    )


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(hours=-2)])
def test_cancelar_horario_que_ja_passou_recusa(delta):
    with pytest.raises(HorarioNoPassado):
        classificar_cancelamento(_AGORA, _AGORA + delta, 48, POLITICA_HANDOFF)


# --- hierarquia de erros --------------------------------------------------------


@pytest.mark.parametrize(
    "erro",
    [
        HorarioNoPassado,
        AntecedenciaInsuficiente,
        AntecedenciaExcedida,
        ForaDoExpediente,
        HorarioIndisponivel,
        AgendamentoDuplicado,
    ],
)
def test_violacoes_de_regra_sao_regra_violada(erro):
    assert issubclass(erro, RegraViolada)


def test_configuracao_invalida_fica_fora_de_regra_violada():
    # Erro de cadastro gera alerta ou handoff, nunca "horario indisponivel"
    assert not issubclass(ConfiguracaoInvalida, RegraViolada)
    assert not issubclass(RegraViolada, ConfiguracaoInvalida)


# --- configuracao da clinica ----------------------------------------------------


def _regras(minima=None, maxima=None, janela=None, fuso=SP, politica=POLITICA_HANDOFF):
    return RegrasClinica(
        fuso=fuso,
        antecedencia_minima_horas=minima,
        antecedencia_maxima_dias=maxima,
        janela_cancelamento_horas=janela,
        politica_cancelamento_fora_janela=politica,
    )


class _Linha:
    """Linha de regras_agendamento como vem do banco."""

    def __init__(self, minima=2, maxima=60, janela=48, politica=POLITICA_HANDOFF):
        self.antecedencia_minima_horas = minima
        self.antecedencia_maxima_dias = maxima
        self.janela_cancelamento_horas = janela
        self.politica_cancelamento_fora_janela = politica


def test_regras_da_clinica_le_a_linha():
    regras = regras_da_clinica(MANAUS, _Linha(24, 30, 24, POLITICA_ACEITAR_E_MARCAR))
    assert regras == _regras(24, 30, 24, MANAUS, POLITICA_ACEITAR_E_MARCAR)


def test_clinica_sem_linha_de_regras_e_configuracao_invalida():
    with pytest.raises(ConfiguracaoInvalida):
        regras_da_clinica(SP, None)


def test_colunas_nulas_sao_aceitas_e_desligam_regras():
    assert regras_da_clinica(SP, _Linha(None, None, None)) == _regras()


@pytest.mark.parametrize(
    "linha",
    [_Linha(minima=-1), _Linha(maxima=-1), _Linha(janela=-1), _Linha(politica="xyz")],
)
def test_valor_invalido_na_linha_e_configuracao_invalida(linha):
    with pytest.raises(ConfiguracaoInvalida):
        regras_da_clinica(SP, linha)


def test_fuso_invalido_e_configuracao_invalida():
    with pytest.raises(ConfiguracaoInvalida):
        regras_da_clinica("Marte/Olympus", _Linha())


# --- antecedencia ---------------------------------------------------------------

_AGORA_52 = datetime(2027, 3, 1, 12, tzinfo=UTC)


def test_antecedencia_igual_a_minima_passa():
    validar_antecedencia(_AGORA_52, _AGORA_52 + timedelta(hours=2), _regras(minima=2))


def test_antecedencia_um_segundo_abaixo_da_minima_recusa():
    inicio = _AGORA_52 + timedelta(hours=2) - timedelta(seconds=1)
    with pytest.raises(AntecedenciaInsuficiente):
        validar_antecedencia(_AGORA_52, inicio, _regras(minima=2))


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(hours=-1)])
def test_inicio_agora_ou_no_passado_recusa(delta):
    with pytest.raises(HorarioNoPassado):
        validar_antecedencia(_AGORA_52, _AGORA_52 + delta, _regras(minima=0))


def test_horario_no_passado_vale_mesmo_sem_regra_de_minima():
    with pytest.raises(HorarioNoPassado):
        validar_antecedencia(_AGORA_52, _AGORA_52 - timedelta(minutes=1), _regras())


def test_minima_nula_desliga_a_regra():
    validar_antecedencia(_AGORA_52, _AGORA_52 + timedelta(minutes=1), _regras())


def test_maxima_ultimo_dia_permitido_passa_e_o_seguinte_recusa():
    # Hoje e 01/03 local. Com 30 dias, o ultimo dia e 31/03, a qualquer hora.
    validar_antecedencia(
        _AGORA_52, datetime(2027, 3, 31, 20, tzinfo=UTC), _regras(maxima=30)
    )
    with pytest.raises(AntecedenciaExcedida):
        validar_antecedencia(
            _AGORA_52, datetime(2027, 4, 1, 12, tzinfo=UTC), _regras(maxima=30)
        )


def test_maxima_usa_a_data_no_fuso_da_clinica():
    # 01/04 03:30 UTC e 01/04 00:30 em Sao Paulo (passa do limite de 31/03) e
    # 31/03 23:30 em Manaus (ainda dentro). Por diferenca de instantes, os dois
    # seriam recusados, porque passam de 30 x 24 h depois de agora.
    inicio = datetime(2027, 4, 1, 3, 30, tzinfo=UTC)
    with pytest.raises(AntecedenciaExcedida):
        validar_antecedencia(_AGORA_52, inicio, _regras(maxima=30, fuso=SP))
    validar_antecedencia(_AGORA_52, inicio, _regras(maxima=30, fuso=MANAUS))


def test_maxima_nula_desliga_a_regra():
    validar_antecedencia(_AGORA_52, datetime(2030, 1, 1, tzinfo=UTC), _regras())


def test_antecedencia_sem_fuso_levanta_value_error():
    with pytest.raises(ValueError):
        validar_antecedencia(_AGORA_52, datetime(2027, 3, 2, 12), _regras())
    with pytest.raises(ValueError):
        validar_antecedencia(
            datetime(2027, 3, 1, 12), datetime(2027, 3, 2, 12, tzinfo=UTC), _regras()
        )


# --- expediente -----------------------------------------------------------------


def _faixa(dia, ini, fim, ativo=True):
    return FaixaExpediente(dia_semana=dia, hora_inicio=ini, hora_fim=fim, ativo=ativo)


# Clinica com equipe (clinica.md, secao 6): seg a sex com almoco, sab de manha.
_EXPEDIENTE_EQUIPE = [
    *[_faixa(d, time(8), time(12)) for d in range(0, 5)],
    *[_faixa(d, time(13, 30), time(18)) for d in range(0, 4)],
    _faixa(4, time(13, 30), time(17)),
    _faixa(5, time(8), time(12)),
    _faixa(6, time(8), time(12), ativo=False),  # domingo fechado, faixa inativa
]


def _sp(dia, hora, minuto=0):
    """Horario de parede em Sao Paulo (UTC-3 em 2027), como instante UTC."""
    return datetime(2027, 3, dia, hora, minuto, tzinfo=UTC) + timedelta(hours=3)


def test_dentro_da_faixa_passa():
    validar_expediente(_sp(1, 9), _sp(1, 9, 30), _EXPEDIENTE_EQUIPE, SP)


def test_terminar_exatamente_no_fim_da_faixa_passa():
    validar_expediente(_sp(1, 11, 30), _sp(1, 12), _EXPEDIENTE_EQUIPE, SP)


def test_comecar_exatamente_no_inicio_da_faixa_passa():
    validar_expediente(_sp(1, 8), _sp(1, 8, 30), _EXPEDIENTE_EQUIPE, SP)


def test_comecar_dentro_e_terminar_fora_recusa():
    with pytest.raises(ForaDoExpediente):
        validar_expediente(_sp(1, 11, 45), _sp(1, 12, 15), _EXPEDIENTE_EQUIPE, SP)


def test_horario_de_almoco_recusa():
    with pytest.raises(ForaDoExpediente):
        validar_expediente(_sp(1, 12, 30), _sp(1, 13), _EXPEDIENTE_EQUIPE, SP)


def test_domingo_com_faixa_inativa_recusa():
    # 07/03/2027 e domingo
    with pytest.raises(ForaDoExpediente):
        validar_expediente(_sp(7, 9), _sp(7, 9, 30), _EXPEDIENTE_EQUIPE, SP)


def test_faixas_contiguas_valem_como_uma_so():
    faixas = [_faixa(0, time(8), time(12)), _faixa(0, time(12), time(18))]
    validar_expediente(_sp(1, 11, 30), _sp(1, 12, 30), faixas, SP)


def test_faixas_sobrepostas_valem_como_uma_so():
    faixas = [_faixa(0, time(11), time(14)), _faixa(0, time(8), time(12))]
    validar_expediente(_sp(1, 9), _sp(1, 13, 30), faixas, SP)


def test_faixas_com_intervalo_entre_elas_nao_se_juntam():
    faixas = [_faixa(0, time(8), time(12)), _faixa(0, time(12, 1), time(18))]
    with pytest.raises(ForaDoExpediente):
        validar_expediente(_sp(1, 11, 30), _sp(1, 12, 30), faixas, SP)


def test_faixa_de_outro_dia_nao_conta():
    faixas = [_faixa(1, time(8), time(18))]  # so terca
    with pytest.raises(ForaDoExpediente):
        validar_expediente(_sp(1, 9), _sp(1, 9, 30), faixas, SP)


def test_dia_da_semana_vem_da_data_local():
    # Segunda 21:00 em Manaus e terca 01:00 em UTC. Com o dia de UTC, seria recusado.
    faixas = [_faixa(0, time(20), time(23))]
    inicio = datetime(2027, 3, 2, 1, tzinfo=UTC)
    validar_expediente(inicio, inicio + timedelta(minutes=30), faixas, MANAUS)


def test_intervalo_que_atravessa_a_meia_noite_local_recusa():
    faixas = [_faixa(0, time(0), time(23, 59)), _faixa(1, time(0), time(23, 59))]
    inicio = _sp(1, 23, 30)  # segunda 23:30 a terca 00:30 em Sao Paulo
    with pytest.raises(ForaDoExpediente):
        validar_expediente(inicio, inicio + timedelta(hours=1), faixas, SP)


@pytest.mark.parametrize(
    "faixas",
    [[], [_faixa(0, time(8), time(12), ativo=False)]],
)
def test_profissional_sem_faixa_ativa_e_configuracao_invalida(faixas):
    with pytest.raises(ConfiguracaoInvalida):
        validar_expediente(_sp(1, 9), _sp(1, 9, 30), faixas, SP)


@pytest.mark.parametrize(
    "faixa",
    [
        _faixa(0, None, time(12)),
        _faixa(0, time(8), None),
        _faixa(None, time(8), time(12)),
        _faixa(7, time(8), time(12)),
        _faixa(0, time(12), time(8)),
        _faixa(0, time(8), time(8)),
    ],
)
def test_faixa_ativa_incompleta_ou_invertida_e_configuracao_invalida(faixa):
    faixas = [_faixa(0, time(8), time(18)), faixa]
    with pytest.raises(ConfiguracaoInvalida):
        validar_expediente(_sp(1, 9), _sp(1, 9, 30), faixas, SP)


def test_faixa_inativa_incompleta_e_ignorada():
    faixas = [_faixa(0, time(8), time(18)), _faixa(0, None, None, ativo=False)]
    validar_expediente(_sp(1, 9), _sp(1, 9, 30), faixas, SP)


def test_expediente_sem_fuso_levanta_value_error():
    with pytest.raises(ValueError):
        validar_expediente(
            datetime(2027, 3, 1, 9), datetime(2027, 3, 1, 10), _EXPEDIENTE_EQUIPE, SP
        )


# --- conflito -------------------------------------------------------------------


def _ag(id_, prof, contato, inicio, minutos=30, status="agendado", tenant="t"):
    return Agendamento(
        id=id_,
        tenant_id=tenant,
        profissional_id=prof,
        servico_id=1,
        contato_telefone=contato,
        inicio=inicio,
        fim=inicio + timedelta(minutes=minutos),
        status=status,
    )


_DEZ = datetime(2027, 3, 2, 13, tzinfo=UTC)  # 10:00 em Sao Paulo
_MEIA = timedelta(minutes=30)
_QUINZE = timedelta(minutes=15)


def test_intervalos_adjacentes_nao_conflitam():
    assert not intervalos_conflitam(_DEZ, _DEZ + _MEIA, _DEZ + _MEIA, _DEZ + 2 * _MEIA)
    assert not intervalos_conflitam(_DEZ + _MEIA, _DEZ + 2 * _MEIA, _DEZ, _DEZ + _MEIA)


@pytest.mark.parametrize(
    "b_inicio,b_fim",
    [
        (_DEZ + _QUINZE, _DEZ + _MEIA + _QUINZE),  # sobrepoe o fim
        (_DEZ - _QUINZE, _DEZ + _QUINZE),  # sobrepoe o inicio
        (_DEZ + timedelta(minutes=5), _DEZ + timedelta(minutes=10)),  # contido
        (_DEZ - _MEIA, _DEZ + 2 * _MEIA),  # contem
        (_DEZ, _DEZ + _MEIA),  # igual
    ],
)
def test_intervalos_sobrepostos_conflitam(b_inicio, b_fim):
    assert intervalos_conflitam(_DEZ, _DEZ + _MEIA, b_inicio, b_fim)


def test_conflito_com_o_mesmo_profissional_recusa():
    ocupados = [_ag(1, prof=7, contato="a", inicio=_DEZ)]
    with pytest.raises(HorarioIndisponivel):
        verificar_conflito(_DEZ + _QUINZE, _DEZ + _MEIA + _QUINZE, 7, ocupados)


def test_conflito_ignora_outro_profissional_e_cancelados():
    ocupados = [
        _ag(1, prof=8, contato="a", inicio=_DEZ),
        _ag(2, prof=7, contato="b", inicio=_DEZ, status="cancelado"),
    ]
    verificar_conflito(_DEZ, _DEZ + _MEIA, 7, ocupados)


def test_conflito_adjacente_passa():
    ocupados = [_ag(1, prof=7, contato="a", inicio=_DEZ)]
    verificar_conflito(_DEZ + _MEIA, _DEZ + 2 * _MEIA, 7, ocupados)


# --- duplicidade ----------------------------------------------------------------

_CONTATO = "(00) 90000-0001"


def test_mesmo_contato_sobreposto_com_outro_profissional_e_duplicado():
    existentes = [_ag(1, prof=8, contato=_CONTATO, inicio=_DEZ)]
    with pytest.raises(AgendamentoDuplicado):
        verificar_duplicidade(
            _DEZ + _QUINZE, _DEZ + _MEIA + _QUINZE, _CONTATO, existentes
        )


def test_mesmo_contato_sem_sobreposicao_nao_e_duplicado():
    # Retorno com o mesmo profissional e o mesmo servico, em outro horario
    existentes = [_ag(1, prof=7, contato=_CONTATO, inicio=_DEZ)]
    verificar_duplicidade(_DEZ + _MEIA, _DEZ + 2 * _MEIA, _CONTATO, existentes)


def test_duplicidade_ignora_cancelados_e_outros_contatos():
    existentes = [
        _ag(1, prof=7, contato=_CONTATO, inicio=_DEZ, status="cancelado"),
        _ag(2, prof=8, contato="(00) 90000-0002", inicio=_DEZ),
    ]
    verificar_duplicidade(_DEZ, _DEZ + _MEIA, _CONTATO, existentes)


# --- segunda barreira de isolamento ----------------------------------------------
# A lista vem de uma sessao app_clinicas, e o RLS e a barreira principal. Uma lista
# com dois tenants indica bug na carga e nunca vira resposta ao paciente.


def test_mistura_de_tenants_fica_fora_das_outras_familias():
    assert not issubclass(MisturaDeTenants, RegraViolada)
    assert not issubclass(MisturaDeTenants, ConfiguracaoInvalida)


@pytest.mark.parametrize(
    "verificar,chave", [(verificar_conflito, 7), (verificar_duplicidade, _CONTATO)]
)
def test_lista_com_dois_tenants_levanta_mistura(verificar, chave):
    # Nenhum dos dois agendamentos se sobrepoe: a recusa vem so da mistura
    existentes = [
        _ag(1, prof=7, contato=_CONTATO, inicio=_DEZ + 4 * _MEIA, tenant="clinica-a"),
        _ag(
            2,
            prof=8,
            contato="(00) 90000-0002",
            inicio=_DEZ + 6 * _MEIA,
            tenant="clinica-b",
        ),
    ]
    with pytest.raises(MisturaDeTenants):
        verificar(_DEZ, _DEZ + _MEIA, chave, existentes)


@pytest.mark.parametrize(
    "verificar,chave", [(verificar_conflito, 7), (verificar_duplicidade, _CONTATO)]
)
def test_mistura_vence_a_regra_violada(verificar, chave):
    # O agendamento de outra clinica se sobrepoe. Sem a barreira, viraria
    # HorarioIndisponivel ou AgendamentoDuplicado e revelaria dado de outra clinica.
    existentes = [
        _ag(
            1,
            prof=8,
            contato="(00) 90000-0003",
            inicio=_DEZ + 4 * _MEIA,
            tenant="clinica-a",
        ),
        _ag(2, prof=7, contato=_CONTATO, inicio=_DEZ, tenant="clinica-b"),
    ]
    with pytest.raises(MisturaDeTenants):
        verificar(_DEZ, _DEZ + _MEIA, chave, existentes)


@pytest.mark.parametrize(
    "verificar,chave", [(verificar_conflito, 7), (verificar_duplicidade, _CONTATO)]
)
def test_lista_de_um_tenant_so_e_lista_vazia_passam(verificar, chave):
    verificar(_DEZ, _DEZ + _MEIA, chave, [])
    existentes = [
        _ag(1, prof=8, contato="(00) 90000-0003", inicio=_DEZ, tenant="clinica-a"),
        _ag(2, prof=7, contato=_CONTATO, inicio=_DEZ + 4 * _MEIA, tenant="clinica-a"),
    ]
    verificar(_DEZ, _DEZ + _MEIA, chave, existentes)


def test_mistura_detectada_tambem_com_gerador():
    # A funcao aceita Iterable. Consumir o gerador uma vez so nao pode esconder a mistura.
    existentes = (
        _ag(i, prof=8, contato="x", inicio=_DEZ, tenant=t)
        for i, t in ((1, "a"), (2, "b"))
    )
    with pytest.raises(MisturaDeTenants):
        verificar_conflito(_DEZ, _DEZ + _MEIA, 7, existentes)


# --- tarefa 5.3: pedido repetido, servico nao oferecido e faixas do dia ----------


def test_servico_nao_oferecido_e_regra_violada():
    assert issubclass(ServicoNaoOferecido, RegraViolada)


def test_pedido_repetido_encontra_o_mesmo_profissional_e_inicio():
    existente = _ag(1, prof=7, contato=_CONTATO, inicio=_DEZ)
    assert pedido_repetido(_DEZ, 7, _CONTATO, [existente]) == existente


@pytest.mark.parametrize(
    "existente",
    [
        _ag(1, prof=7, contato=_CONTATO, inicio=_DEZ, status="cancelado"),
        _ag(1, prof=8, contato=_CONTATO, inicio=_DEZ),
        _ag(1, prof=7, contato=_CONTATO, inicio=_DEZ + _QUINZE),
        _ag(1, prof=7, contato="(00) 90000-0002", inicio=_DEZ),
    ],
)
def test_pedido_repetido_exige_contato_profissional_inicio_e_ativo(existente):
    assert pedido_repetido(_DEZ, 7, _CONTATO, [existente]) is None


def test_pedido_repetido_recusa_mistura_de_tenants():
    existentes = [
        _ag(1, prof=7, contato=_CONTATO, inicio=_DEZ, tenant="a"),
        _ag(2, prof=8, contato="x", inicio=_DEZ + 4 * _MEIA, tenant="b"),
    ]
    with pytest.raises(MisturaDeTenants):
        pedido_repetido(_DEZ, 7, _CONTATO, existentes)


def test_duplicidade_ignora_o_pedido_repetido():
    # Exatamente o que o contato ja tem nao e duplicidade: o servico devolve o existente
    existentes = [_ag(1, prof=7, contato=_CONTATO, inicio=_DEZ)]
    verificar_duplicidade(_DEZ, _DEZ + _MEIA, _CONTATO, existentes, profissional_id=7)


def test_duplicidade_mesmo_profissional_outro_inicio_sobreposto():
    existentes = [_ag(1, prof=7, contato=_CONTATO, inicio=_DEZ)]
    with pytest.raises(AgendamentoDuplicado):
        verificar_duplicidade(
            _DEZ + _QUINZE,
            _DEZ + _MEIA + _QUINZE,
            _CONTATO,
            existentes,
            profissional_id=7,
        )


def test_faixas_do_dia_junta_as_contiguas_e_ignora_outros_dias():
    faixas = [
        _faixa(0, time(12), time(18)),
        _faixa(0, time(8), time(12)),
        _faixa(0, time(19), time(20)),
        _faixa(1, time(7), time(9)),
    ]
    assert faixas_do_dia(faixas, 0) == [(time(8), time(18)), (time(19), time(20))]
    assert faixas_do_dia(faixas, 2) == []


def test_faixas_do_dia_sem_faixa_ativa_e_configuracao_invalida():
    with pytest.raises(ConfiguracaoInvalida):
        faixas_do_dia([], 0)
