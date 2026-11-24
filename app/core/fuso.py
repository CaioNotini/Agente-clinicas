"""Conversao para o fuso da clinica (Q-23, ADR 0009).

O armazenamento e sempre em UTC. As regras de antecedencia, janela de cancelamento
e lembretes, e a exibicao ao paciente, usam o fuso da clinica. Esta e a funcao unica
de conversao, e o nome do fuso e validado na leitura das regras da clinica. A
aplicacao ainda nao grava clinicas.fuso.

tzdata entra no requirements porque o Windows nao traz a base de fusos do sistema,
e sem ela o zoneinfo nao encontra 'America/Sao_Paulo'.
"""
from datetime import date, datetime, time, timezone
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


def instante_local(dia: date, hora: time, nome_fuso: str) -> datetime:
    """Instante UTC do horario de parede dia e hora no fuso da clinica.

    Usada para montar a grade de disponibilidade a partir das faixas de expediente,
    que sao horarios de parede.
    """
    return datetime.combine(dia, hora, tzinfo=ZoneInfo(nome_fuso)).astimezone(
        timezone.utc
    )
