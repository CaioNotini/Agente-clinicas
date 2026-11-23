"""Regras da tarefa 5.2 aplicadas nos dois cenarios do publico-alvo (ADR 0009).

Cenario equipe: clinica com recepcao (docs/fake_clinic/clinica.md), fuso
America/Sao_Paulo, antecedencia de 2 h a 60 dias, janela de 48 h, politica 'handoff',
expediente com almoco e sabado de manha.
Cenario solo: consultorio sem recepcao (docs/fake_clinic/consultorio_solo.md), fuso
America/Manaus, antecedencia de 24 h a 30 dias, janela de 24 h, politica
'aceitar_e_marcar', expediente de segunda a sexta das 09:00 as 17:00.

Os dados sao semeados com a conta de administracao (cnotini). A configuracao e lida
como a aplicacao vai ler, numa sessao app_clinicas com app.tenant_id definido.
O mesmo pedido, no mesmo instante, tem resultado diferente em cada cenario.

2027-03-01 e uma segunda-feira.
"""
import uuid
from datetime import datetime, time, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from app.agenda.regras import (
    ABRIR_HANDOFF,
    CANCELAR_TARDIO,
    DENTRO_JANELA,
    AntecedenciaExcedida,
    AntecedenciaInsuficiente,
    ConfiguracaoInvalida,
    FaixaExpediente,
    ForaDoExpediente,
    classificar_cancelamento,
    regras_da_clinica,
    validar_antecedencia,
    validar_expediente,
)
from app.config import MIGRATION_DATABASE_URL
from app.db.database import SessionLocal

engine_admin = create_engine(MIGRATION_DATABASE_URL)

UTC = timezone.utc
AGORA = datetime(2027, 3, 1, 12, tzinfo=UTC)

# (dia_semana, inicio, fim), 0 = segunda
_EXPEDIENTE_EQUIPE = [
    *[(d, time(8), time(12)) for d in range(0, 6)],
    *[(d, time(13, 30), time(18)) for d in range(0, 4)],
    (4, time(13, 30), time(17)),
]
_EXPEDIENTE_SOLO = [(d, time(9), time(17)) for d in range(0, 5)]


def _semear(conexao, *, fuso, politica, minima, maxima, janela, expediente):
    tenant_id = str(uuid.uuid4())
    conexao.execute(
        text(
            "INSERT INTO clinicas (tenant_id, nome, ativo, fuso) VALUES (:t, 'C', true, :f)"
        ),
        {"t": tenant_id, "f": fuso},
    )
    prof = conexao.execute(
        text(
            "INSERT INTO profissionais (tenant_id, nome, ativo) VALUES (:t, 'P', true) RETURNING id"
        ),
        {"t": tenant_id},
    ).scalar()
    if politica is not None:
        conexao.execute(
            text(
                "INSERT INTO regras_agendamento (tenant_id, antecedencia_minima_horas, "
                "antecedencia_maxima_dias, janela_cancelamento_horas, "
                "politica_cancelamento_fora_janela) VALUES (:t, :mi, :ma, :j, :p)"
            ),
            {"t": tenant_id, "mi": minima, "ma": maxima, "j": janela, "p": politica},
        )
    for dia, ini, fim in expediente:
        conexao.execute(
            text(
                "INSERT INTO horarios_trabalho (tenant_id, profissional_id, dia_semana, "
                "hora_inicio, hora_fim, ativo) VALUES (:t, :p, :d, :i, :f, true)"
            ),
            {"t": tenant_id, "p": prof, "d": dia, "i": ini, "f": fim},
        )
    return {"tenant": tenant_id, "prof": prof}


@pytest.fixture(scope="module")
def cenarios():
    with engine_admin.begin() as conexao:
        dados = {
            "equipe": _semear(
                conexao,
                fuso="America/Sao_Paulo",
                politica="handoff",
                minima=2,
                maxima=60,
                janela=48,
                expediente=_EXPEDIENTE_EQUIPE,
            ),
            "solo": _semear(
                conexao,
                fuso="America/Manaus",
                politica="aceitar_e_marcar",
                minima=24,
                maxima=30,
                janela=24,
                expediente=_EXPEDIENTE_SOLO,
            ),
            # Cadastro incompleto: sem linha em regras_agendamento e sem expediente
            "sem_cadastro": _semear(
                conexao,
                fuso="America/Sao_Paulo",
                politica=None,
                minima=None,
                maxima=None,
                janela=None,
                expediente=[],
            ),
        }
    yield dados
    with engine_admin.begin() as conexao:
        for cenario in dados.values():
            for tabela in (
                "horarios_trabalho",
                "regras_agendamento",
                "profissionais",
                "clinicas",
            ):
                conexao.execute(
                    text(f"DELETE FROM {tabela} WHERE tenant_id = :t"),
                    {"t": cenario["tenant"]},
                )


def _ler_config(cenario):
    """Le fuso, regras e expediente pela sessao app_clinicas, sob RLS.

    Sem WHERE tenant_id de proposito: e assim que a aplicacao le, com o RLS como
    barreira (ADR 0002). O set_config vale so nesta transacao, entao nao pode haver
    commit entre ele e as consultas. A garantia de isolamento fica em tests/isolation/.
    """
    session = SessionLocal()
    try:
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": cenario["tenant"]},
        )
        fuso = session.execute(text("SELECT fuso FROM clinicas")).scalar()
        linha = session.execute(
            text(
                "SELECT antecedencia_minima_horas, antecedencia_maxima_dias, "
                "janela_cancelamento_horas, politica_cancelamento_fora_janela "
                "FROM regras_agendamento"
            )
        ).first()
        faixas = [
            FaixaExpediente(
                dia_semana=f.dia_semana,
                hora_inicio=f.hora_inicio,
                hora_fim=f.hora_fim,
                ativo=f.ativo,
            )
            for f in session.execute(
                text(
                    "SELECT dia_semana, hora_inicio, hora_fim, ativo FROM horarios_trabalho "
                    "WHERE profissional_id = :p"
                ),
                {"p": cenario["prof"]},
            )
        ]
    finally:
        session.rollback()
        session.close()
    return fuso, linha, faixas


def _validar_pedido(cenario, inicio, minutos=30):
    fuso, linha, faixas = _ler_config(cenario)
    regras = regras_da_clinica(fuso, linha)
    fim = inicio + timedelta(minutes=minutos)
    validar_antecedencia(AGORA, inicio, regras)
    validar_expediente(inicio, fim, faixas, regras.fuso)


def test_segunda_a_tarde_no_mesmo_dia(cenarios):
    # 01/03 17:00 UTC: 14:00 em Sao Paulo e 13:00 em Manaus, 5 h depois de agora
    inicio = datetime(2027, 3, 1, 17, tzinfo=UTC)
    _validar_pedido(cenarios["equipe"], inicio)
    with pytest.raises(AntecedenciaInsuficiente):
        _validar_pedido(cenarios["solo"], inicio)


def test_sabado_de_manha(cenarios):
    # 06/03 14:00 UTC: sabado 11:00 em Sao Paulo e 10:00 em Manaus
    inicio = datetime(2027, 3, 6, 14, tzinfo=UTC)
    _validar_pedido(cenarios["equipe"], inicio)
    with pytest.raises(ForaDoExpediente):
        _validar_pedido(cenarios["solo"], inicio)


def test_quarenta_e_cinco_dias_a_frente(cenarios):
    # 15/04 14:00 UTC: quinta 11:00 em Sao Paulo e 10:00 em Manaus
    inicio = datetime(2027, 4, 15, 14, tzinfo=UTC)
    _validar_pedido(cenarios["equipe"], inicio)
    with pytest.raises(AntecedenciaExcedida):
        _validar_pedido(cenarios["solo"], inicio)


def test_horario_de_almoco_so_vale_para_a_equipe(cenarios):
    # 03/03 16:00 UTC: quarta 13:00 em Sao Paulo (almoco) e 12:00 em Manaus
    inicio = datetime(2027, 3, 3, 16, tzinfo=UTC)
    with pytest.raises(ForaDoExpediente):
        _validar_pedido(cenarios["equipe"], inicio)
    _validar_pedido(cenarios["solo"], inicio)


@pytest.mark.parametrize(
    "horas,equipe,solo",
    [
        (72, DENTRO_JANELA, DENTRO_JANELA),
        (30, ABRIR_HANDOFF, DENTRO_JANELA),
        (12, ABRIR_HANDOFF, CANCELAR_TARDIO),
    ],
)
def test_cancelamento_por_cenario(cenarios, horas, equipe, solo):
    inicio = AGORA + timedelta(hours=horas)
    for nome, esperado in (("equipe", equipe), ("solo", solo)):
        fuso, linha, _ = _ler_config(cenarios[nome])
        regras = regras_da_clinica(fuso, linha)
        resultado = classificar_cancelamento(
            AGORA,
            inicio,
            regras.janela_cancelamento_horas,
            regras.politica_cancelamento_fora_janela,
        )
        assert resultado == esperado, nome


def test_clinica_sem_regras_e_configuracao_invalida(cenarios):
    fuso, linha, _ = _ler_config(cenarios["sem_cadastro"])
    assert linha is None
    with pytest.raises(ConfiguracaoInvalida):
        regras_da_clinica(fuso, linha)


def test_profissional_sem_expediente_e_configuracao_invalida(cenarios):
    fuso, _, faixas = _ler_config(cenarios["sem_cadastro"])
    assert faixas == []
    inicio = datetime(2027, 3, 2, 14, tzinfo=UTC)
    with pytest.raises(ConfiguracaoInvalida):
        validar_expediente(inicio, inicio + timedelta(minutes=30), faixas, fuso)


def test_config_de_uma_clinica_nao_aparece_na_sessao_da_outra(cenarios):
    """A leitura de regras e expediente respeita o tenant da sessao.

    Complementar aos testes de tests/isolation/. O controle positivo mostra que o
    profissional da equipe tem faixas, para o [] da leitura cruzada nao passar por
    falta de dados.
    """
    _, linha_equipe, faixas_equipe = _ler_config(cenarios["equipe"])
    assert linha_equipe is not None
    assert faixas_equipe

    _, linha, faixas = _ler_config(
        {
            "tenant": cenarios["sem_cadastro"]["tenant"],
            "prof": cenarios["equipe"]["prof"],
        }
    )
    assert linha is None
    assert faixas == []
