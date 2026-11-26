"""Combinacao da regra com o LLM (tarefa 7.2, revisao de 2026-11-26 do ADR 0012).

Cobre o curto-circuito na urgencia da regra, a uniao nas urgencias, o erro
permanente com a regra na hora e log de erro, o erro transitorio que sobe para o
retry do job e a saida invalida. Nenhum log leva o texto da mensagem.
"""
import pytest
from anthropic import APIConnectionError, AuthenticationError, BadRequestError
from structlog.testing import capture_logs

from app.classification.classificador import classificar
from app.classification.resultado import (
    ADMINISTRATIVO,
    AGENDAMENTO,
    CLINICO_BLOQUEADO,
    ORIGEM_LLM,
    ORIGEM_REGRA,
    SINTOMA,
    URGENCIA,
    Intencao,
)
from app.llm.anthropic_client import AnthropicClient
from app.llm.base import ConfigLLM
from app.llm.erros import ErroLLMPermanente, ErroLLMTransitorio
from tests.llm_falso import ClienteFalso, saida_json

TENANT = "11111111-1111-1111-1111-111111111111"


def _item(categoria, confianca, subtipo=None):
    return {"categoria": categoria, "subtipo": subtipo, "confianca": confianca}


def _classificar(texto, cliente):
    return classificar(texto, cliente_llm=cliente, tenant_id=TENANT)


# --- curto-circuito e uniao nas urgencias ----------------------------------


@pytest.mark.parametrize(
    "texto", ["estou com dor no peito agora", "Tentei me matar ano passado"]
)
def test_urgencia_da_regra_nao_chama_o_llm(texto):
    cliente = ClienteFalso(saida_json(_item(ADMINISTRATIVO, 0.9)))
    resultado = _classificar(texto, cliente)

    assert cliente.chamadas == []
    assert resultado.origem == ORIGEM_REGRA
    assert Intencao(URGENCIA) in resultado.intencoes


def test_urgencia_da_regra_vale_mesmo_com_o_llm_quebrado():
    """Sem chamada, um LLM que falharia nao atrasa nem derruba a urgencia."""
    cliente = ClienteFalso(erro=ErroLLMTransitorio("timeout"))
    resultado = _classificar("estou com dor no peito agora", cliente)
    assert Intencao(URGENCIA) in resultado.intencoes


def test_urgencia_so_do_llm_e_mantida():
    """Uniao: a regra nao viu urgencia, o LLM viu, e a urgencia fica."""
    texto = "minha mae caiu e nao acorda"
    cliente = ClienteFalso(saida_json(_item(URGENCIA, 0.8)))
    resultado = _classificar(texto, cliente)

    assert len(cliente.chamadas) == 1
    assert resultado.origem == ORIGEM_LLM
    assert resultado.intencoes == (Intencao(URGENCIA, confianca=0.8),)


def test_sem_urgencia_vale_o_llm_inteiro_sem_uniao_das_demais():
    """A regra ve clinico_bloqueado e o LLM nao: vale o LLM. So a urgencia e unida."""
    texto = "estou com dor nas costas"
    cliente = ClienteFalso(saida_json(_item(AGENDAMENTO, 0.9)))
    resultado = _classificar(texto, cliente)

    assert resultado.origem == ORIGEM_LLM
    assert resultado.intencoes == (Intencao(AGENDAMENTO, confianca=0.9),)


# --- erro permanente: regra na hora, log de erro ---------------------------


class _RespostaHttp:
    def __init__(self, status):
        self.request = object()
        self.status_code = status
        self.headers = {"request-id": "req_teste"}


class _SdkQueFalha:
    def __init__(self, erro):
        self._erro = erro
        self.messages = self

    def create(self, **_):
        raise self._erro


def _cliente_real_com_erro(classe_erro, status):
    erro = classe_erro("corpo do erro", response=_RespostaHttp(status), body=None)
    return AnthropicClient(_SdkQueFalha(erro), ConfigLLM(modelo="modelo-teste", max_tokens=10))


@pytest.mark.parametrize(
    "classe_erro, status, causa",
    [(AuthenticationError, 401, "AuthenticationError"), (BadRequestError, 400, "BadRequestError")],
)
def test_erro_permanente_usa_a_regra_e_loga_com_nivel_de_erro(classe_erro, status, causa):
    texto = "estou com dor nas costas"
    cliente = _cliente_real_com_erro(classe_erro, status)

    with capture_logs() as logs:
        resultado = _classificar(texto, cliente)

    assert resultado.origem == ORIGEM_REGRA
    assert resultado.intencoes == (Intencao(CLINICO_BLOQUEADO, subtipo=SINTOMA),)

    eventos = [log for log in logs if log["event"] == "classificacao_llm_erro_permanente"]
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento["log_level"] == "error"
    assert evento["tenant_id"] == TENANT
    assert evento["erro"] == "ErroLLMPermanente"
    assert evento["causa"] == causa
    assert texto not in repr(logs)


def test_erro_permanente_sem_causa_loga_causa_vazia():
    cliente = ClienteFalso(erro=ErroLLMPermanente("sem causa"))
    with capture_logs() as logs:
        resultado = _classificar("quanto custa a consulta?", cliente)

    assert resultado.origem == ORIGEM_REGRA
    assert resultado.intencoes == (Intencao(ADMINISTRATIVO),)
    evento = next(log for log in logs if log["event"] == "classificacao_llm_erro_permanente")
    assert evento["causa"] is None


def test_erro_permanente_com_regra_vazia_devolve_lista_vazia():
    """Sem nada na regra, o fallback e a lista vazia, que vira ambiguo em decidir()."""
    cliente = ClienteFalso(erro=ErroLLMPermanente("x"))
    resultado = _classificar("oi", cliente)
    assert resultado.origem == ORIGEM_REGRA
    assert resultado.intencoes == ()


# --- erro transitorio: sobe para o retry do job ----------------------------


def test_erro_transitorio_sobe_sem_fallback():
    cliente = ClienteFalso(erro=ErroLLMTransitorio("503"))
    with capture_logs() as logs:
        with pytest.raises(ErroLLMTransitorio):
            _classificar("quanto custa a consulta?", cliente)
    assert not [log for log in logs if log["event"].startswith("classificacao")]


def test_erro_de_conexao_do_sdk_sobe_como_transitorio():
    sdk = _SdkQueFalha(APIConnectionError(request=object()))
    cliente = AnthropicClient(sdk, ConfigLLM(modelo="modelo-teste", max_tokens=10))
    with pytest.raises(ErroLLMTransitorio):
        _classificar("quanto custa a consulta?", cliente)


# --- saida invalida: regra, com aviso --------------------------------------


@pytest.mark.parametrize(
    "texto_llm, motivo_parada, motivo",
    [
        ("nao e json", "end_turn", "json"),
        (saida_json(_item("ambiguo", 0.9)), "end_turn", "formato"),
        (saida_json(_item(AGENDAMENTO, 0.9)), "refusal", "motivo_parada"),
        ('{"intencoes": [', "max_tokens", "motivo_parada"),
    ],
)
def test_saida_invalida_usa_a_regra_e_loga_aviso(texto_llm, motivo_parada, motivo):
    texto = "posso tomar dipirona para essa dor?"
    cliente = ClienteFalso(texto_llm, motivo_parada=motivo_parada)

    with capture_logs() as logs:
        resultado = _classificar(texto, cliente)

    assert resultado.origem == ORIGEM_REGRA
    assert resultado.intencoes[0].categoria == CLINICO_BLOQUEADO
    eventos = [log for log in logs if log["event"] == "classificacao_saida_invalida"]
    assert len(eventos) == 1
    assert eventos[0]["log_level"] == "warning"
    assert eventos[0]["motivo"] == motivo
    assert eventos[0]["tenant_id"] == TENANT
    assert texto not in repr(logs)
