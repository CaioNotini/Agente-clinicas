"""Saida da classificacao, limites de confianca e decisao (tarefa 7.1, ADR 0012).

A regra (7.1) e o LLM (7.2) devolvem o mesmo ResultadoClassificacao. O LLM so
rotula: a ordem do que tratar sai de decidir(), funcao pura do codigo, igual para
as duas origens.

As dataclasses validam a forma na construcao. Uma saida do LLM fora do formato
(categoria desconhecida, repetida, ambiguo, confianca fora de 0 a 1 ou subtipo fora
de clinico_bloqueado) levanta IntencaoInvalida, e a 7.2 trata isso como saida
invalida, descartada por inteiro.
"""

from dataclasses import dataclass
from typing import Optional

ADMINISTRATIVO = "administrativo"
AGENDAMENTO = "agendamento"
CLINICO_BLOQUEADO = "clinico_bloqueado"
URGENCIA = "urgencia"
# ambiguo e a decisao quando nao sobra intencao aceita. Nunca entra na lista.
AMBIGUO = "ambiguo"

CATEGORIAS_INTENCAO = frozenset(
    {ADMINISTRATIVO, AGENDAMENTO, CLINICO_BLOQUEADO, URGENCIA}
)

PERGUNTA = "pergunta"
SINTOMA = "sintoma"
SUBTIPOS = frozenset({PERGUNTA, SINTOMA})
# Subtipo usado quando a origem nao sabe separar os dois casos (ADR 0012)
SUBTIPO_PADRAO = SINTOMA

ORIGEM_REGRA = "regra"
ORIGEM_LLM = "llm"
ORIGENS = frozenset({ORIGEM_REGRA, ORIGEM_LLM})

# Confianca minima para aceitar uma intencao de origem llm. Mais baixa em urgencia e
# clinico_bloqueado pela assimetria da secao 8.3 da arquitetura. Valores iniciais,
# calibrados na etapa 10 (Q-06).
LIMITES = {
    URGENCIA: 0.5,
    CLINICO_BLOQUEADO: 0.5,
    ADMINISTRATIVO: 0.7,
    AGENDAMENTO: 0.7,
}


class IntencaoInvalida(ValueError):
    """Intencao ou resultado fora do formato do ADR 0012."""


@dataclass(frozen=True)
class Intencao:
    """Uma intencao rotulada. subtipo so em clinico_bloqueado, confianca so na origem llm."""

    categoria: str
    subtipo: Optional[str] = None
    confianca: Optional[float] = None

    def __post_init__(self):
        if self.categoria not in CATEGORIAS_INTENCAO:
            raise IntencaoInvalida(f"categoria fora da lista: {self.categoria!r}")
        if self.categoria == CLINICO_BLOQUEADO:
            if self.subtipo not in SUBTIPOS:
                raise IntencaoInvalida(f"subtipo invalido: {self.subtipo!r}")
        elif self.subtipo is not None:
            raise IntencaoInvalida("subtipo so existe em clinico_bloqueado")
        if self.confianca is not None:
            # bool e subclasse de int e nao e uma confianca
            if isinstance(self.confianca, bool) or not isinstance(
                self.confianca, (int, float)
            ):
                raise IntencaoInvalida("confianca precisa ser numero")
            if not 0 <= self.confianca <= 1:
                raise IntencaoInvalida("confianca fora de 0 a 1")


@dataclass(frozen=True)
class ResultadoClassificacao:
    """Lista de intencoes, no maximo uma por categoria, e a origem que as produziu."""

    intencoes: tuple[Intencao, ...]
    origem: str

    def __post_init__(self):
        if self.origem not in ORIGENS:
            raise IntencaoInvalida(f"origem invalida: {self.origem!r}")
        if not isinstance(self.intencoes, tuple):
            raise IntencaoInvalida("intencoes precisa ser tupla")
        categorias = [intencao.categoria for intencao in self.intencoes]
        if len(categorias) != len(set(categorias)):
            raise IntencaoInvalida("categoria repetida na lista de intencoes")
        for intencao in self.intencoes:
            # A regra nao estima incerteza. O LLM sempre declara a confianca.
            if self.origem == ORIGEM_REGRA and intencao.confianca is not None:
                raise IntencaoInvalida("origem regra nao tem confianca")
            if self.origem == ORIGEM_LLM and intencao.confianca is None:
                raise IntencaoInvalida("origem llm exige confianca")


@dataclass(frozen=True)
class Decisao:
    """Intencoes na ordem em que devem ser tratadas. Vazia significa ambiguo."""

    itens: tuple[Intencao, ...]

    @property
    def ambiguo(self) -> bool:
        """True quando nenhuma intencao foi aceita."""
        return not self.itens


def aplicar_limites(resultado: ResultadoClassificacao) -> tuple[Intencao, ...]:
    """Intencoes aceitas. Na origem llm, descarta as abaixo do limite da categoria.

    Na origem regra todas sao aceitas, sem comparacao com limite (ADR 0012).
    """
    if resultado.origem == ORIGEM_REGRA:
        return resultado.intencoes
    return tuple(
        intencao
        for intencao in resultado.intencoes
        if intencao.confianca >= LIMITES[intencao.categoria]
    )


# Ordem de tratamento sem urgencia (ADR 0012): clinico_bloqueado primeiro, depois
# administrativo, que se resolve no mesmo turno, e por ultimo agendamento, que abre
# um fluxo de varios turnos. A prioridade e um dado, nao uma cadeia de ifs.
ORDEM_SEM_URGENCIA = (CLINICO_BLOQUEADO, ADMINISTRATIVO, AGENDAMENTO)


def decidir(intencoes: tuple[Intencao, ...]) -> Decisao:
    """Ordena as intencoes aceitas pela regra de prioridade do ADR 0012.

    1. Com urgencia, so ela: as demais sao descartadas (decisoes 13 e 23).
    2. Sem urgencia, a ordem de ORDEM_SEM_URGENCIA, qualquer que seja a ordem de
       entrada, porque o LLM devolve as intencoes em qualquer ordem.
    3. Nenhuma intencao: Decisao vazia, que e ambiguo.

    Funcao pura: nao altera a entrada e devolve as mesmas instancias de Intencao,
    com subtipo e confianca intactos.
    """
    categorias = [intencao.categoria for intencao in intencoes]
    if len(categorias) != len(set(categorias)):
        raise IntencaoInvalida("categoria repetida na lista de intencoes")

    for intencao in intencoes:
        if intencao.categoria == URGENCIA:
            return Decisao((intencao,))

    posicao = {categoria: indice for indice, categoria in enumerate(ORDEM_SEM_URGENCIA)}
    return Decisao(tuple(sorted(intencoes, key=lambda i: posicao[i.categoria])))
