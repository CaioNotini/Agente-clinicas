"""Regras determinísticas da etapa 5 (Q-21 duracao, Q-22 cancelamento).

Funcoes puras, base do servico de agendamento (5.3). Nao tocam no banco.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.agenda.regras import (
    ABRIR_HANDOFF,
    CANCELAR_TARDIO,
    DENTRO_JANELA,
    POLITICA_ACEITAR_E_MARCAR,
    POLITICA_HANDOFF,
    calcular_fim,
    classificar_cancelamento,
    resolver_duracao_minutos,
)

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
