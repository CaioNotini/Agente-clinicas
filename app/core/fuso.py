"""Conversao para o fuso da clinica (Q-23, ADR 0009).

O armazenamento e sempre em UTC. As regras de antecedencia, janela de cancelamento
e lembretes, e a exibicao ao paciente, usam o fuso da clinica. Esta e a funcao unica
de conversao, e o nome do fuso e validado antes de gravar.

tzdata entra no requirements porque o Windows nao traz a base de fusos do sistema,
e sem ela o zoneinfo nao encontra 'America/Sao_Paulo'.
"""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FUSO_PADRAO = "America/Sao_Paulo"


def validar_fuso(nome: str) -> None:
    """Levanta ValueError se nome nao for um fuso IANA conhecido."""
    try:
        ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError) as erro:
        raise ValueError(f"fuso invalido: {nome!r}") from erro


def para_fuso_clinica(instante: datetime, nome_fuso: str) -> datetime:
    """Converte um instante aware para o fuso da clinica, sem mudar o instante.

    Levanta ValueError se instante nao tiver fuso, para nao interpretar um horario
    ingenuo pelo fuso local do processo.
    """
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError("instante precisa ter fuso horario")
    return instante.astimezone(ZoneInfo(nome_fuso))
