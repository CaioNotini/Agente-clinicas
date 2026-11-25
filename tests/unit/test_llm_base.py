"""Formato do contrato do LLMClient (etapa 6.1). Sem API e sem banco."""
import pytest

from app.llm.base import ChamadaFerramenta, ConfigLLM, LLMClient, RespostaLLM


def test_llmclient_e_abstrata_e_nao_instancia():
    with pytest.raises(TypeError):
        LLMClient()


def test_config_llm_nao_tem_campo_de_chave_nem_amostragem():
    campos = ConfigLLM.__dataclass_fields__
    assert "modelo" in campos
    assert "max_tokens" in campos
    assert "esforco" in campos
    # A chave vai direto ao SDK, e a versao 2026-10-21 recusa temperature/top_p/top_k
    for proibido in ("api_key", "chave", "temperature", "top_p", "top_k"):
        assert proibido not in campos


def test_config_llm_esforco_tem_padrao_none():
    config = ConfigLLM(modelo="modelo-x", max_tokens=100)
    assert config.esforco is None


def test_resposta_llm_carrega_a_telemetria():
    resposta = RespostaLLM(
        texto="oi",
        chamadas_ferramenta=(ChamadaFerramenta(id="t1", nome="criar", entrada={}),),
        motivo_parada="end_turn",
        tokens_entrada=3,
        tokens_saida=5,
        latencia_ms=12,
        modelo="modelo-x",
        id_requisicao="req_1",
    )
    assert resposta.tokens_entrada == 3
    assert resposta.tokens_saida == 5
    assert resposta.latencia_ms == 12
    assert resposta.chamadas_ferramenta[0].nome == "criar"
