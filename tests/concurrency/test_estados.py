"""Testes da maquina de estados da conversa (etapa 4.1).

Verifica o grafo de transicoes de app/core/estados.py contra o grafo aprovado em
docs/decisions/0003-grafo-de-transicoes.md: toda transicao valida e aceita, e
toda transicao invalida e rejeitada com TransicaoInvalida.

Observacao de escopo: estes testes sao unitarios (nao tocam no banco), mas
etapas.md autoriza para a etapa 4 apenas tests/concurrency/. Ficam aqui para nao
editar um diretorio fora da lista da etapa. Registrado como pendencia em
docs/status.md.
"""
import itertools

import pytest

from app.core.estados import (
    AGUARDANDO_CONFIRMACAO,
    COLETANDO_INFO,
    ENCERRADA,
    ESCALADA,
    ESTADO_INICIAL,
    ESTADOS,
    IDLE,
    TransicaoInvalida,
    transicao_permitida,
    validar_transicao,
)

# Grafo esperado, escrito a mao a partir do ADR 0003. Nao e importado de
# estados.py de proposito: se o codigo mudar o grafo, este teste tem que acusar.
GRAFO_ESPERADO = {
    IDLE: {COLETANDO_INFO, ESCALADA},
    COLETANDO_INFO: {AGUARDANDO_CONFIRMACAO, ESCALADA, ENCERRADA, IDLE},
    AGUARDANDO_CONFIRMACAO: {COLETANDO_INFO, ESCALADA, ENCERRADA, IDLE},
    ESCALADA: {IDLE, ENCERRADA},
    ENCERRADA: {IDLE},
}

# Pares validos e invalidos derivados do grafo esperado, cobrindo ESTADOS x ESTADOS
PARES_VALIDOS = [
    (origem, destino)
    for origem, destinos in GRAFO_ESPERADO.items()
    for destino in destinos
]
PARES_INVALIDOS = [
    (origem, destino)
    for origem, destino in itertools.product(ESTADOS, ESTADOS)
    if destino not in GRAFO_ESPERADO[origem]
]


def test_cinco_estados_conhecidos():
    assert ESTADOS == {IDLE, COLETANDO_INFO, AGUARDANDO_CONFIRMACAO, ESCALADA, ENCERRADA}
    assert ESTADO_INICIAL == IDLE


@pytest.mark.parametrize("origem,destino", PARES_VALIDOS)
def test_transicao_valida_e_aceita(origem, destino):
    assert transicao_permitida(origem, destino) is True
    # Nao deve levantar
    validar_transicao(origem, destino)


@pytest.mark.parametrize("origem,destino", PARES_INVALIDOS)
def test_transicao_invalida_e_rejeitada(origem, destino):
    assert transicao_permitida(origem, destino) is False
    with pytest.raises(TransicaoInvalida):
        validar_transicao(origem, destino)


def test_idle_para_encerrada_removida_do_grafo():
    """Controle: idle -> encerrada foi retirada do grafo (ADR 0003)."""
    assert transicao_permitida(IDLE, ENCERRADA) is False
    with pytest.raises(TransicaoInvalida):
        validar_transicao(IDLE, ENCERRADA)


def test_transicao_para_o_mesmo_estado_e_rejeitada():
    """Nao existe laco: nenhum estado transita para ele mesmo."""
    for estado in ESTADOS:
        assert transicao_permitida(estado, estado) is False
        with pytest.raises(TransicaoInvalida):
            validar_transicao(estado, estado)


def test_estado_de_origem_desconhecido():
    assert transicao_permitida("inexistente", IDLE) is False
    with pytest.raises(TransicaoInvalida, match="origem desconhecido"):
        validar_transicao("inexistente", IDLE)


def test_estado_de_destino_desconhecido():
    assert transicao_permitida(IDLE, "inexistente") is False
    with pytest.raises(TransicaoInvalida, match="destino desconhecido"):
        validar_transicao(IDLE, "inexistente")
