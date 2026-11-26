"""Classificacao real pela API da Anthropic (tarefa 7.2, regra 22 do CLAUDE.md).

Marcador llm_real: fora da CI e fora do pytest padrao. So o desenvolvedor roda, com
`pytest -m llm_real tests/llm_real/test_classificacao_real.py -v`, depois de aprovar
a execucao. A implementacao foi aprovada em 2026-11-26.

O que prova, e por que so um teste real prova:
- a API aceita o ESQUEMA_CLASSIFICACAO em output_config.format, coisa que o duble
  dos testes unitarios nao verifica;
- a saida volta valida pelo ADR 0012 com o max_tokens padrao, sem corte pelo
  raciocinio adaptativo;
- para mensagens claras, a categoria esperada aparece acima do limite dela.

Chama classificar_por_llm direto, sem a regra, para exercitar o caminho do LLM
tambem na urgencia. Uma chamada por mensagem, 6 no total. O modelo vem de
LLM_MODEL. As mensagens sao ficticias.
"""
import os
import uuid

import pytest
from structlog.testing import capture_logs

from app.classification.llm import classificar_por_llm
from app.classification.resultado import (
    ADMINISTRATIVO,
    AGENDAMENTO,
    CLINICO_BLOQUEADO,
    LIMITES,
    ORIGEM_LLM,
    PERGUNTA,
    SINTOMA,
    URGENCIA,
)
from app.llm.fabrica import criar_cliente_llm

_FALTANDO = [nome for nome in ("ANTHROPIC_API_KEY", "LLM_MODEL") if not os.getenv(nome)]
pytestmark = [
    pytest.mark.llm_real,
    pytest.mark.skipif(
        bool(_FALTANDO),
        reason=f"variaveis ausentes para o teste real: {', '.join(_FALTANDO)}",
    ),
]

TENANT_FICTICIO = str(uuid.UUID("11111111-1111-1111-1111-111111111111"))
TIMEOUT_REAL = 60

# (mensagem, categoria esperada, subtipo esperado ou None)
CASOS = [
    ("Qual o valor da consulta particular?", ADMINISTRATIVO, None),
    ("Quero marcar uma consulta para a semana que vem", AGENDAMENTO, None),
    ("Posso tomar ibuprofeno junto com o antibiotico?", CLINICO_BLOQUEADO, PERGUNTA),
    ("Estou com uma dor nas costas faz uns dias", CLINICO_BLOQUEADO, SINTOMA),
    ("Meu pai esta com o rosto torto e nao consegue falar direito", URGENCIA, None),
]


@pytest.fixture(scope="module")
def cliente():
    return criar_cliente_llm()


def _classificar(cliente, texto):
    with capture_logs() as logs:
        resultado = classificar_por_llm(texto, cliente_llm=cliente, tenant_id=TENANT_FICTICIO)
    return resultado, logs


@pytest.mark.timeout(TIMEOUT_REAL)
@pytest.mark.parametrize("texto, categoria, subtipo", CASOS)
def test_categoria_esperada_acima_do_limite(cliente, texto, categoria, subtipo):
    # SaidaInvalida aqui reprova o teste: a saida estruturada deveria vir valida
    resultado, logs = _classificar(cliente, texto)

    assert resultado.origem == ORIGEM_LLM
    por_categoria = {intencao.categoria: intencao for intencao in resultado.intencoes}
    assert categoria in por_categoria, resultado
    intencao = por_categoria[categoria]
    assert intencao.confianca >= LIMITES[categoria], resultado
    if subtipo is not None:
        assert intencao.subtipo == subtipo, resultado

    # Telemetria da chamada, sem a mensagem no log
    eventos = [log for log in logs if log.get("event") == "llm_chamada"]
    assert len(eventos) == 1
    assert eventos[0]["motivo_parada"] == "end_turn"
    assert eventos[0]["tokens_saida"] > 0
    assert texto not in repr(logs)


@pytest.mark.timeout(TIMEOUT_REAL)
def test_duas_intencoes_na_mesma_mensagem(cliente):
    """Decisao 23: "quero marcar e quanto custa?" tem duas intencoes."""
    resultado, _ = _classificar(cliente, "Quero marcar uma consulta e quanto custa?")

    aceitas = {
        intencao.categoria
        for intencao in resultado.intencoes
        if intencao.confianca >= LIMITES[intencao.categoria]
    }
    assert {AGENDAMENTO, ADMINISTRATIVO} <= aceitas, resultado
