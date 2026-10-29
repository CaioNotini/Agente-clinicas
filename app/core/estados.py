"""Maquina de estados da conversa: estados e transicoes deterministicas (etapa 4.1).

Implementa a decisao D-08 da arquitetura (estado explicito em
conversas.estado_conversa, com 5 estados). O grafo de transicoes validas esta
registrado em docs/decisions/0003-grafo-de-transicoes.md.

Este modulo e puro: nao toca no banco e nao decide qual transicao tomar. Ele so
diz se uma transicao e permitida. A escrita do novo estado e a decisao de qual
transicao aplicar sao responsabilidade do chamador. A decisao dirigida por
conteudo (classificacao de intencao) entra a partir da etapa 7, fora do escopo
da etapa 4.
"""

# Os cinco estados da conversa (arquitetura, secao 7 e D-08)
IDLE = "idle"
COLETANDO_INFO = "coletando_info"
AGUARDANDO_CONFIRMACAO = "aguardando_confirmacao"
ESCALADA = "escalada"
ENCERRADA = "encerrada"

# Estado inicial de uma conversa recem-criada
ESTADO_INICIAL = IDLE

ESTADOS = frozenset(
    {IDLE, COLETANDO_INFO, AGUARDANDO_CONFIRMACAO, ESCALADA, ENCERRADA}
)

# Grafo de transicoes validas: origem -> destinos permitidos.
# Ver docs/decisions/0003-grafo-de-transicoes.md para a justificativa de cada aresta.
TRANSICOES = {
    IDLE: frozenset({COLETANDO_INFO, ESCALADA}),
    COLETANDO_INFO: frozenset({AGUARDANDO_CONFIRMACAO, ESCALADA, ENCERRADA, IDLE}),
    AGUARDANDO_CONFIRMACAO: frozenset({COLETANDO_INFO, ESCALADA, ENCERRADA, IDLE}),
    ESCALADA: frozenset({IDLE, ENCERRADA}),
    ENCERRADA: frozenset({IDLE}),
}


class TransicaoInvalida(Exception):
    """A transicao pedida nao e permitida pelo grafo, ou envolve estado desconhecido."""


def transicao_permitida(origem: str, destino: str) -> bool:
    """Diz se a transicao origem -> destino e permitida pelo grafo.

    Estados desconhecidos (fora de ESTADOS) nunca sao permitidos.
    """
    return destino in TRANSICOES.get(origem, frozenset())


def validar_transicao(origem: str, destino: str) -> None:
    """Levanta TransicaoInvalida se a transicao origem -> destino nao for permitida.

    Distingue estado desconhecido de transicao proibida apenas na mensagem de erro.
    """
    if origem not in ESTADOS:
        raise TransicaoInvalida(f"estado de origem desconhecido: {origem!r}")
    if destino not in ESTADOS:
        raise TransicaoInvalida(f"estado de destino desconhecido: {destino!r}")
    if not transicao_permitida(origem, destino):
        raise TransicaoInvalida(f"transicao proibida: {origem!r} -> {destino!r}")
