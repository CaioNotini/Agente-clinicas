"""Classificacao com LLM: leitura da saida estruturada (tarefa 7.2, ADR 0012).

O LLMClient e um duble, sem rede. Cada criterio de saida invalida do ADR 0012 tem
um caso, e todos levam a SaidaInvalida com um codigo fixo de motivo.
"""
import json

import pytest

from app.classification.llm import (
    ESQUEMA_CLASSIFICACAO,
    MOTIVO_FORMATO,
    MOTIVO_JSON,
    MOTIVO_PARADA,
    PROMPT_CLASSIFICACAO,
    SaidaInvalida,
    classificar_por_llm,
)
from app.classification.resultado import (
    ADMINISTRATIVO,
    AGENDAMENTO,
    CLINICO_BLOQUEADO,
    ORIGEM_LLM,
    PERGUNTA,
    SINTOMA,
    URGENCIA,
    Intencao,
)
from tests.llm_falso import ClienteFalso

TENANT = "11111111-1111-1111-1111-111111111111"


def _saida(*intencoes):
    return json.dumps({"intencoes": list(intencoes)})


def _item(categoria, confianca, subtipo=None):
    return {"categoria": categoria, "subtipo": subtipo, "confianca": confianca}


def _classificar(cliente, texto="mensagem qualquer"):
    return classificar_por_llm(texto, cliente_llm=cliente, tenant_id=TENANT)


# --- saida valida ----------------------------------------------------------


@pytest.mark.parametrize(
    "item, esperada",
    [
        (_item(URGENCIA, 0.9), Intencao(URGENCIA, confianca=0.9)),
        (_item(ADMINISTRATIVO, 0.8), Intencao(ADMINISTRATIVO, confianca=0.8)),
        (_item(AGENDAMENTO, 0.75), Intencao(AGENDAMENTO, confianca=0.75)),
        (
            _item(CLINICO_BLOQUEADO, 0.6, PERGUNTA),
            Intencao(CLINICO_BLOQUEADO, subtipo=PERGUNTA, confianca=0.6),
        ),
        (
            _item(CLINICO_BLOQUEADO, 0.6, SINTOMA),
            Intencao(CLINICO_BLOQUEADO, subtipo=SINTOMA, confianca=0.6),
        ),
    ],
)
def test_saida_valida_de_cada_categoria(item, esperada):
    resultado = _classificar(ClienteFalso(_saida(item)))
    assert resultado.origem == ORIGEM_LLM
    assert resultado.intencoes == (esperada,)


def test_varias_intencoes_mantem_a_ordem_e_as_confiancas():
    cliente = ClienteFalso(_saida(_item(AGENDAMENTO, 0.9), _item(ADMINISTRATIVO, 0.4)))
    resultado = _classificar(cliente)
    # Confianca abaixo do limite continua no resultado: o limite e aplicado depois,
    # em aplicar_limites, e o log mostra o que o modelo devolveu.
    assert resultado.intencoes == (
        Intencao(AGENDAMENTO, confianca=0.9),
        Intencao(ADMINISTRATIVO, confianca=0.4),
    )


def test_lista_vazia_e_valida():
    resultado = _classificar(ClienteFalso(_saida()))
    assert resultado.intencoes == ()
    assert resultado.origem == ORIGEM_LLM


@pytest.mark.parametrize("confianca", [0, 1, 0.0, 1.0])
def test_confianca_nos_extremos_e_valida(confianca):
    resultado = _classificar(ClienteFalso(_saida(_item(AGENDAMENTO, confianca))))
    assert resultado.intencoes[0].confianca == confianca


# --- a chamada -------------------------------------------------------------


def test_chamada_leva_so_a_mensagem_atual_com_prompt_e_esquema():
    cliente = ClienteFalso(_saida())
    _classificar(cliente, texto="quanto custa a consulta?")

    assert len(cliente.chamadas) == 1
    chamada = cliente.chamadas[0]
    assert chamada["tenant_id"] == TENANT
    assert chamada["system"] == PROMPT_CLASSIFICACAO
    assert chamada["mensagens"] == [{"role": "user", "content": "quanto custa a consulta?"}]
    assert chamada["esquema_saida"] == ESQUEMA_CLASSIFICACAO
    assert chamada["ferramentas"] is None


def test_esquema_fecha_os_objetos_e_lista_as_quatro_categorias():
    """A saida estruturada exige additionalProperties false e campos obrigatorios."""
    item = ESQUEMA_CLASSIFICACAO["properties"]["intencoes"]["items"]
    assert ESQUEMA_CLASSIFICACAO["additionalProperties"] is False
    assert item["additionalProperties"] is False
    assert set(item["required"]) == {"categoria", "subtipo", "confianca"}
    assert set(item["properties"]["categoria"]["enum"]) == {
        URGENCIA,
        CLINICO_BLOQUEADO,
        ADMINISTRATIVO,
        AGENDAMENTO,
    }
    assert "ambiguo" not in json.dumps(ESQUEMA_CLASSIFICACAO)


def test_prompt_nao_cita_nome_de_modelo():
    assert "claude" not in PROMPT_CLASSIFICACAO.lower()


# --- saida invalida (ADR 0012) ---------------------------------------------


@pytest.mark.parametrize("motivo_parada", ["refusal", "max_tokens", None, "tool_use"])
def test_motivo_de_parada_diferente_de_end_turn_e_invalido(motivo_parada):
    # Mesmo com um JSON valido no texto, o corte ou a recusa invalidam a saida
    cliente = ClienteFalso(_saida(_item(URGENCIA, 0.9)), motivo_parada=motivo_parada)
    with pytest.raises(SaidaInvalida) as exc:
        _classificar(cliente)
    assert exc.value.motivo == MOTIVO_PARADA


@pytest.mark.parametrize("texto", ["", "nao e json", '{"intencoes": [', "texto {}"])
def test_json_malformado_e_invalido(texto):
    with pytest.raises(SaidaInvalida) as exc:
        _classificar(ClienteFalso(texto))
    assert exc.value.motivo == MOTIVO_JSON


@pytest.mark.parametrize(
    "dados",
    [
        {},  # falta intencoes
        [],  # nao e objeto
        "texto",
        {"intencoes": None},
        {"intencoes": "urgencia"},
        {"intencoes": [{"categoria": URGENCIA, "subtipo": None}]},  # falta confianca
        {"intencoes": [{"subtipo": None, "confianca": 0.9}]},  # falta categoria
        {"intencoes": [{"categoria": URGENCIA, "confianca": 0.9}]},  # falta subtipo
        {"intencoes": ["urgencia"]},
    ],
)
def test_estrutura_fora_do_formato_e_invalida(dados):
    with pytest.raises(SaidaInvalida) as exc:
        _classificar(ClienteFalso(json.dumps(dados)))
    assert exc.value.motivo == MOTIVO_FORMATO


@pytest.mark.parametrize(
    "itens",
    [
        [_item("financeiro", 0.9)],  # categoria desconhecida
        [_item("ambiguo", 0.9)],  # ambiguo nunca entra na lista
        [_item(AGENDAMENTO, 0.9), _item(AGENDAMENTO, 0.8)],  # categoria repetida
        [_item(AGENDAMENTO, 1.5)],  # confianca acima de 1
        [_item(AGENDAMENTO, -0.1)],  # confianca abaixo de 0
        [_item(AGENDAMENTO, "0.9")],  # confianca como texto
        [_item(AGENDAMENTO, True)],  # booleano nao e confianca
        [_item(AGENDAMENTO, None)],  # origem llm exige confianca
        [_item(AGENDAMENTO, 0.9, SINTOMA)],  # subtipo fora de clinico_bloqueado
        [_item(CLINICO_BLOQUEADO, 0.9)],  # clinico sem subtipo
        [_item(CLINICO_BLOQUEADO, 0.9, "grave")],  # subtipo desconhecido
        [_item(["urgencia"], 0.9)],  # categoria que nem e texto
    ],
)
def test_criterios_de_saida_invalida_do_adr_0012(itens):
    with pytest.raises(SaidaInvalida) as exc:
        _classificar(ClienteFalso(_saida(*itens)))
    assert exc.value.motivo == MOTIVO_FORMATO


def test_uma_intencao_invalida_descarta_a_saida_inteira():
    """Saida invalida e descartada por inteiro, sem aproveitar as intencoes validas."""
    cliente = ClienteFalso(_saida(_item(URGENCIA, 0.9), _item("financeiro", 0.9)))
    with pytest.raises(SaidaInvalida):
        _classificar(cliente)


def test_motivo_da_saida_invalida_nao_repete_o_que_o_modelo_escreveu():
    eco = "texto que o paciente escreveu"
    cliente = ClienteFalso(_saida(_item(eco, 0.9)))
    with pytest.raises(SaidaInvalida) as exc:
        _classificar(cliente)
    assert eco not in str(exc.value)
    assert eco not in exc.value.motivo
