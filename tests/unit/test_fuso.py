"""Conversao para o fuso da clinica (Q-23, ADR 0009).

O armazenamento e sempre em UTC. As regras e a exibicao usam o fuso da clinica,
por uma funcao unica. O nome do fuso e validado antes de gravar. tzdata entra no
requirements porque o Windows nao traz a base de fusos do sistema.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.fuso import FUSO_PADRAO, para_fuso_clinica, validar_fuso


def test_fuso_padrao_e_sao_paulo():
    assert FUSO_PADRAO == "America/Sao_Paulo"


@pytest.mark.parametrize("nome", ["America/Sao_Paulo", "America/Manaus", "UTC"])
def test_validar_fuso_aceita_nome_iana_valido(nome):
    # Nao levanta
    validar_fuso(nome)


@pytest.mark.parametrize("nome", ["Nao/Existe", "America/Nenhuma", "", "Sao Paulo"])
def test_validar_fuso_rejeita_nome_invalido(nome):
    with pytest.raises(ValueError):
        validar_fuso(nome)


def test_conversao_para_sao_paulo_usa_offset_menos_3():
    # Brasil sem horario de verao desde 2019: Sao Paulo e -03:00 o ano todo
    instante = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    local = para_fuso_clinica(instante, "America/Sao_Paulo")
    assert local.utcoffset() == timedelta(hours=-3)
    assert local.hour == 9


def test_conversao_para_manaus_usa_offset_menos_4():
    instante = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    local = para_fuso_clinica(instante, "America/Manaus")
    assert local.utcoffset() == timedelta(hours=-4)
    assert local.hour == 8


def test_conversao_preserva_o_instante():
    instante = datetime(2026, 7, 1, 15, 30, tzinfo=timezone.utc)
    local = para_fuso_clinica(instante, "America/Manaus")
    # O instante absoluto nao muda, so a representacao local
    assert local == instante


def test_conversao_rejeita_datetime_sem_fuso():
    naive = datetime(2026, 1, 15, 12, 0)
    with pytest.raises(ValueError):
        para_fuso_clinica(naive, "America/Sao_Paulo")
