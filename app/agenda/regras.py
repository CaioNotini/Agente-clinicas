"""Regras deterministicas da etapa 5 (Q-21 duracao, Q-22 cancelamento), ADR 0009.

Funcoes puras, sem banco, base do servico de agendamento (5.3). A janela de
cancelamento e medida entre dois instantes, entao independe do fuso: o fuso da
clinica (ADR 0009) importa para regras expressas em horario de parede e para a
exibicao, nao para esta diferenca em horas. A conversao de fuso fica em
app/core/fuso.py.
"""
from datetime import datetime, timedelta
from typing import Optional

# Politicas de cancelamento fora da janela (coluna regras_agendamento)
POLITICA_HANDOFF = "handoff"
POLITICA_ACEITAR_E_MARCAR = "aceitar_e_marcar"

# Resultado de classificar_cancelamento
DENTRO_JANELA = "dentro_janela"
ABRIR_HANDOFF = "abrir_handoff"
CANCELAR_TARDIO = "cancelar_tardio"

# Motivo de handoff aberto por cancelamento fora da janela (handoffs.motivo)
MOTIVO_CANCELAMENTO_FORA_DA_JANELA = "cancelamento_fora_da_janela"


def resolver_duracao_minutos(duracao_servico: int, override: Optional[int]) -> int:
    """Duracao que vale no agendamento: o override do profissional, se houver.

    override None usa a duracao do servico. override 0 e um valor explicito e vence,
    porque e diferente de ausente.
    """
    return duracao_servico if override is None else override


def calcular_fim(inicio: datetime, duracao_minutos: int) -> datetime:
    """Fim do agendamento a partir do inicio e da duracao em minutos."""
    return inicio + timedelta(minutes=duracao_minutos)


def classificar_cancelamento(
    agora: datetime, inicio: datetime, janela_horas: int, politica: str
) -> str:
    """Classifica um pedido de cancelamento conforme a antecedencia e a politica.

    Dentro da janela (antecedencia maior ou igual a janela): cancelamento normal.
    Fora da janela: handoff abre handoff e so cancela apos decisao humana, e
    aceitar_e_marcar cancela na hora e marca como tardio.
    """
    dentro = inicio - agora >= timedelta(hours=janela_horas)
    if dentro:
        return DENTRO_JANELA
    if politica == POLITICA_HANDOFF:
        return ABRIR_HANDOFF
    if politica == POLITICA_ACEITAR_E_MARCAR:
        return CANCELAR_TARDIO
    raise ValueError(f"politica desconhecida: {politica!r}")
