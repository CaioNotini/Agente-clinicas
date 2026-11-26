"""Regra de prioridade entre intencoes, decidir() (tarefa 7.1, ADR 0012).

Criterio de pronto da etapa 7: a funcao e testada com todas as combinacoes das 4
categorias que podem estar na lista (16 subconjuntos, incluindo a lista vazia) e com
os dois subtipos de clinico_bloqueado.

A tabela ESPERADO e escrita a mao, sem derivar a ordem por codigo, para o teste nao
repetir o algoritmo que ele verifica.
"""
from itertools import permutations

import pytest

from app.classification.resultado import (
    ADMINISTRATIVO,
    AGENDAMENTO,
    CLINICO_BLOQUEADO,
    ORIGEM_LLM,
    PERGUNTA,
    SINTOMA,
    URGENCIA,
    Decisao,
    Intencao,
    IntencaoInvalida,
    ResultadoClassificacao,
    aplicar_limites,
    decidir,
)

U, C, A, G = URGENCIA, CLINICO_BLOQUEADO, ADMINISTRATIVO, AGENDAMENTO

# subconjunto de entrada -> ordem esperada de tratamento. () e ambiguo.
ESPERADO = {
    (): (),
    (U,): (U,),
    (C,): (C,),
    (A,): (A,),
    (G,): (G,),
    (U, C): (U,),
    (U, A): (U,),
    (U, G): (U,),
    (C, A): (C, A),
    (C, G): (C, G),
    (A, G): (A, G),
    (U, C, A): (U,),
    (U, C, G): (U,),
    (U, A, G): (U,),
    (C, A, G): (C, A, G),
    (U, C, A, G): (U,),
}


def _intencao(categoria, subtipo):
    return Intencao(categoria, subtipo=subtipo if categoria == C else None)


def test_tabela_cobre_os_16_subconjuntos():
    assert len(ESPERADO) == 16
    assert {frozenset(chave) for chave in ESPERADO} == {
        frozenset(c for c, bit in zip((U, C, A, G), f"{n:04b}") if bit == "1")
        for n in range(16)
    }


@pytest.mark.parametrize("subtipo", [PERGUNTA, SINTOMA])
@pytest.mark.parametrize(
    "entrada", list(ESPERADO), ids=lambda e: "+".join(e) or "vazia"
)
def test_prioridade_em_todas_as_combinacoes(entrada, subtipo):
    decisao = decidir(tuple(_intencao(c, subtipo) for c in entrada))
    assert isinstance(decisao, Decisao)
    assert tuple(i.categoria for i in decisao.itens) == ESPERADO[entrada]
    assert decisao.ambiguo is (ESPERADO[entrada] == ())


@pytest.mark.parametrize("subtipo", [PERGUNTA, SINTOMA])
@pytest.mark.parametrize(
    "entrada", [e for e in ESPERADO if len(e) > 1], ids=lambda e: "+".join(e)
)
def test_ordem_de_entrada_nao_muda_a_decisao(entrada, subtipo):
    # O LLM devolve as intencoes em qualquer ordem. A decisao nao pode depender dela.
    saidas = {
        tuple(
            i.categoria for i in decidir(tuple(_intencao(c, subtipo) for c in p)).itens
        )
        for p in permutations(entrada)
    }
    assert saidas == {ESPERADO[entrada]}


@pytest.mark.parametrize("subtipo", [PERGUNTA, SINTOMA])
def test_subtipo_e_confianca_chegam_intactos_na_decisao(subtipo):
    clinico = Intencao(C, subtipo=subtipo, confianca=0.55)
    agendamento = Intencao(G, confianca=0.9)
    assert decidir((agendamento, clinico)).itens == (clinico, agendamento)


def test_urgencia_descarta_as_demais_e_fica_sozinha():
    urgencia = Intencao(U, confianca=0.5)
    decisao = decidir(
        (Intencao(G, confianca=0.99), urgencia, Intencao(C, PERGUNTA, 1.0))
    )
    assert decisao.itens == (urgencia,)


def test_categoria_repetida_e_recusada():
    with pytest.raises(IntencaoInvalida):
        decidir((Intencao(A), Intencao(A)))


def test_entrada_nao_e_alterada():
    entrada = (Intencao(G), Intencao(A))
    decidir(entrada)
    assert entrada == (Intencao(G), Intencao(A))


# --- limites + prioridade, o caminho completo do resultado do LLM ---


def _decidir_llm(*intencoes):
    return decidir(
        aplicar_limites(ResultadoClassificacao(tuple(intencoes), ORIGEM_LLM))
    )


def test_urgencia_abaixo_do_limite_nao_bloqueia_as_demais():
    decisao = _decidir_llm(Intencao(U, confianca=0.4), Intencao(G, confianca=0.9))
    assert tuple(i.categoria for i in decisao.itens) == (G,)


def test_lista_vazia_depois_dos_limites_vira_ambiguo():
    decisao = _decidir_llm(Intencao(A, confianca=0.69), Intencao(G, confianca=0.1))
    assert decisao.ambiguo is True


def test_resultado_vazio_do_llm_vira_ambiguo():
    assert _decidir_llm().ambiguo is True
