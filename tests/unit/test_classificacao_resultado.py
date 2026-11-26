"""Formato da saida da classificacao e limites de confianca (tarefa 7.1, ADR 0012).

Cobre a validacao das dataclasses, que a 7.2 usa para descartar uma saida invalida do
LLM, e aplicar_limites, que descarta intencoes abaixo do limite da categoria.
"""
import pytest

from app.classification.resultado import (
    ADMINISTRATIVO,
    AGENDAMENTO,
    AMBIGUO,
    CLINICO_BLOQUEADO,
    LIMITES,
    ORIGEM_LLM,
    ORIGEM_REGRA,
    PERGUNTA,
    SINTOMA,
    SUBTIPO_PADRAO,
    URGENCIA,
    Decisao,
    Intencao,
    IntencaoInvalida,
    ResultadoClassificacao,
    aplicar_limites,
)

# --- Intencao ---


@pytest.mark.parametrize("categoria", [ADMINISTRATIVO, AGENDAMENTO, URGENCIA])
def test_intencao_sem_subtipo_nas_categorias_comuns(categoria):
    assert Intencao(categoria).subtipo is None


@pytest.mark.parametrize("subtipo", [PERGUNTA, SINTOMA])
def test_clinico_bloqueado_aceita_os_dois_subtipos(subtipo):
    assert Intencao(CLINICO_BLOQUEADO, subtipo=subtipo).subtipo == subtipo


def test_subtipo_padrao_e_sintoma():
    assert SUBTIPO_PADRAO == SINTOMA


@pytest.mark.parametrize(
    "categoria", [AMBIGUO, "", "Urgencia", "clinico", None, "saudacao"]
)
def test_categoria_fora_da_lista_e_recusada(categoria):
    with pytest.raises(IntencaoInvalida):
        Intencao(categoria)


@pytest.mark.parametrize("subtipo", [None, "", "diagnostico", "PERGUNTA"])
def test_clinico_bloqueado_sem_subtipo_valido_e_recusado(subtipo):
    with pytest.raises(IntencaoInvalida):
        Intencao(CLINICO_BLOQUEADO, subtipo=subtipo)


@pytest.mark.parametrize("categoria", [ADMINISTRATIVO, AGENDAMENTO, URGENCIA])
def test_subtipo_fora_de_clinico_bloqueado_e_recusado(categoria):
    with pytest.raises(IntencaoInvalida):
        Intencao(categoria, subtipo=PERGUNTA)


@pytest.mark.parametrize("confianca", [0, 0.0, 0.5, 1, 1.0])
def test_confianca_nos_limites_de_0_a_1(confianca):
    assert Intencao(URGENCIA, confianca=confianca).confianca == confianca


@pytest.mark.parametrize(
    "confianca", [-0.01, 1.01, 2, float("nan"), float("inf"), "0.9", True]
)
def test_confianca_invalida_e_recusada(confianca):
    with pytest.raises(IntencaoInvalida):
        Intencao(URGENCIA, confianca=confianca)


# --- ResultadoClassificacao ---


def test_resultado_vazio_e_valido_nas_duas_origens():
    assert ResultadoClassificacao((), ORIGEM_REGRA).intencoes == ()
    assert ResultadoClassificacao((), ORIGEM_LLM).intencoes == ()


@pytest.mark.parametrize("origem", ["", "humano", None, "LLM"])
def test_origem_invalida_e_recusada(origem):
    with pytest.raises(IntencaoInvalida):
        ResultadoClassificacao((), origem)


def test_categoria_repetida_e_recusada():
    with pytest.raises(IntencaoInvalida):
        ResultadoClassificacao(
            (
                Intencao(CLINICO_BLOQUEADO, PERGUNTA, 0.9),
                Intencao(CLINICO_BLOQUEADO, SINTOMA, 0.8),
            ),
            ORIGEM_LLM,
        )


def test_lista_precisa_ser_tupla():
    # Lista mutavel quebraria o frozen da dataclass
    with pytest.raises(IntencaoInvalida):
        ResultadoClassificacao([Intencao(URGENCIA)], ORIGEM_REGRA)


def test_origem_regra_nao_tem_confianca():
    with pytest.raises(IntencaoInvalida):
        ResultadoClassificacao((Intencao(URGENCIA, confianca=0.9),), ORIGEM_REGRA)


def test_origem_llm_exige_confianca():
    with pytest.raises(IntencaoInvalida):
        ResultadoClassificacao((Intencao(URGENCIA),), ORIGEM_LLM)


# --- Limites ---


def test_limites_iniciais_do_adr_0012():
    assert LIMITES == {
        URGENCIA: 0.5,
        CLINICO_BLOQUEADO: 0.5,
        ADMINISTRATIVO: 0.7,
        AGENDAMENTO: 0.7,
    }


def _llm(*intencoes):
    return ResultadoClassificacao(tuple(intencoes), ORIGEM_LLM)


@pytest.mark.parametrize(
    "intencao, aceita",
    [
        (Intencao(URGENCIA, confianca=0.49), False),
        (Intencao(URGENCIA, confianca=0.5), True),
        (Intencao(CLINICO_BLOQUEADO, SINTOMA, 0.49), False),
        (Intencao(CLINICO_BLOQUEADO, PERGUNTA, 0.5), True),
        (Intencao(ADMINISTRATIVO, confianca=0.69), False),
        (Intencao(ADMINISTRATIVO, confianca=0.7), True),
        (Intencao(AGENDAMENTO, confianca=0.69), False),
        (Intencao(AGENDAMENTO, confianca=0.7), True),
        (Intencao(AGENDAMENTO, confianca=0.0), False),
        (Intencao(URGENCIA, confianca=1.0), True),
    ],
)
def test_limite_por_categoria_na_origem_llm(intencao, aceita):
    assert (intencao in aplicar_limites(_llm(intencao))) is aceita


def test_urgencia_em_0_6_e_aceita_e_agendamento_em_0_6_nao():
    # O caso que motivou os dois limites no ADR 0012
    urgencia = Intencao(URGENCIA, confianca=0.6)
    agendamento = Intencao(AGENDAMENTO, confianca=0.6)
    assert aplicar_limites(_llm(urgencia, agendamento)) == (urgencia,)


def test_tudo_abaixo_do_limite_deixa_a_lista_vazia():
    resultado = _llm(
        Intencao(ADMINISTRATIVO, confianca=0.3),
        Intencao(URGENCIA, confianca=0.2),
    )
    assert aplicar_limites(resultado) == ()


def test_origem_regra_aceita_sem_comparar_limite():
    intencoes = (
        Intencao(ADMINISTRATIVO),
        Intencao(AGENDAMENTO),
        Intencao(CLINICO_BLOQUEADO, SINTOMA),
        Intencao(URGENCIA),
    )
    assert aplicar_limites(ResultadoClassificacao(intencoes, ORIGEM_REGRA)) == intencoes


def test_decisao_vazia_e_ambiguo():
    assert Decisao(()).ambiguo is True
    assert Decisao((Intencao(ADMINISTRATIVO),)).ambiguo is False
