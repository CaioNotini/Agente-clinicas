"""Classificacao por regra, baseline da etapa 7 (tarefa 7.1, ADR 0012).

Funcao pura e rapida, sem banco nem rede, porque tambem serve a verificacao de
urgencia com human_mode ativo e, na etapa 9, a dispensa da espera do agrupamento.
Devolve ResultadoClassificacao com origem regra e confianca vazia.

Implementada pelo desenvolvedor. Contrato em tests/unit/test_classificacao_regra.py.
"""
from app.classification.resultado import ResultadoClassificacao


def classificar_por_regra(texto: str) -> ResultadoClassificacao:
    """Rotula o texto com as intencoes que a regra reconhece."""
    raise NotImplementedError(
        "classificar_por_regra: implementacao do desenvolvedor (tarefa 7.1)"
    )
