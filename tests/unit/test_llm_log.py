"""Telemetria do AnthropicClient no log estruturado (etapa 6.3).

Cada chamada gera um evento: llm_chamada no sucesso, llm_chamada_falhou na falha.
Nenhum deles leva prompt, conteudo de mensagem, telefone nem str(e) (ADR 0010). O
SDK entra por duble, entao os testes nao tocam a API nem a rede.
"""
import pytest
from anthropic import APIConnectionError, APIStatusError
from structlog.testing import capture_logs

from app.llm.anthropic_client import AnthropicClient
from app.llm.base import ConfigLLM

_CONFIG = ConfigLLM(modelo="claude-haiku", max_tokens=1024)

# Conteudo sensivel que nunca pode aparecer em nenhum evento de log.
SYSTEM = "prompt de sistema secreto"
TEXTO_ENTRADA = "quero marcar consulta"
TELEFONE = "55999990000"
TEXTO_RESPOSTA = "posso ajudar com isso"


class _BlocoTexto:
    type = "text"

    def __init__(self, texto):
        self.text = texto


class _Uso:
    def __init__(self, entrada, saida):
        self.input_tokens = entrada
        self.output_tokens = saida


class _Mensagem:
    def __init__(self):
        self.content = [_BlocoTexto(TEXTO_RESPOSTA)]
        self.stop_reason = "end_turn"
        self.model = "claude-haiku"
        self.usage = _Uso(9, 4)
        self._request_id = "req_ok"


class _SdkFalso:
    def __init__(self, resposta=None, erro=None):
        self._resposta = resposta
        self._erro = erro
        self.messages = self

    def create(self, **kwargs):
        if self._erro is not None:
            raise self._erro
        return self._resposta


class _RequisicaoFalsa:
    pass


class _RespostaFalsa:
    def __init__(self, status_code, request_id="req_falha"):
        self.request = _RequisicaoFalsa()
        self.status_code = status_code
        self._headers = {"request-id": request_id}

    @property
    def headers(self):
        return self._headers


def _erro_status(status_code):
    return APIStatusError(
        "corpo sensivel do sdk", response=_RespostaFalsa(status_code), body=None
    )


def _mensagens():
    return [{"role": "user", "content": TEXTO_ENTRADA}]


def _chamar(sdk):
    cliente = AnthropicClient(sdk, _CONFIG)
    return cliente.completar(tenant_id="t_log", system=SYSTEM, mensagens=_mensagens())


def _sem_conteudo_sensivel(logs):
    texto = repr(logs)
    for sensivel in (SYSTEM, TEXTO_ENTRADA, TELEFONE, TEXTO_RESPOSTA):
        assert sensivel not in texto


# --- sucesso ---------------------------------------------------------------


def test_sucesso_emite_llm_chamada_com_os_campos():
    with capture_logs() as logs:
        _chamar(_SdkFalso(resposta=_Mensagem()))
    eventos = [log for log in logs if log["event"] == "llm_chamada"]
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento["log_level"] == "info"
    assert evento["tenant_id"] == "t_log"
    assert evento["modelo"] == "claude-haiku"
    assert evento["tokens_entrada"] == 9
    assert evento["tokens_saida"] == 4
    assert evento["motivo_parada"] == "end_turn"
    assert evento["id_requisicao"] == "req_ok"
    assert "latencia_ms" in evento


def test_sucesso_nao_loga_conteudo_sensivel():
    with capture_logs() as logs:
        _chamar(_SdkFalso(resposta=_Mensagem()))
    _sem_conteudo_sensivel(logs)


def test_latencia_do_log_bate_com_a_medida(monkeypatch):
    from app.llm import anthropic_client

    tempos = iter([5.0, 5.4])  # 0,4 s
    monkeypatch.setattr(anthropic_client.time, "perf_counter", lambda: next(tempos))
    with capture_logs() as logs:
        resp = _chamar(_SdkFalso(resposta=_Mensagem()))
    evento = [log for log in logs if log["event"] == "llm_chamada"][0]
    assert evento["latencia_ms"] == resp.latencia_ms == 400


# --- falha -----------------------------------------------------------------


def test_falha_permanente_emite_um_llm_chamada_falhou():
    from app.llm.erros import ErroLLMPermanente

    with capture_logs() as logs:
        with pytest.raises(ErroLLMPermanente):
            _chamar(_SdkFalso(erro=_erro_status(400)))
    assert [log for log in logs if log["event"] == "llm_chamada"] == []
    falhas = [log for log in logs if log["event"] == "llm_chamada_falhou"]
    assert len(falhas) == 1
    falha = falhas[0]
    assert falha["log_level"] == "warning"
    assert falha["tenant_id"] == "t_log"
    assert falha["modelo"] == "claude-haiku"
    assert falha["erro"] == "ErroLLMPermanente"
    assert falha["status"] == 400
    assert falha["id_requisicao"] == "req_falha"
    assert "latencia_ms" in falha
    assert "tokens_entrada" not in falha


def test_falha_transitoria_emite_um_llm_chamada_falhou():
    from app.llm.erros import ErroLLMTransitorio

    with capture_logs() as logs:
        with pytest.raises(ErroLLMTransitorio):
            _chamar(_SdkFalso(erro=_erro_status(503)))
    assert [log for log in logs if log["event"] == "llm_chamada"] == []
    falhas = [log for log in logs if log["event"] == "llm_chamada_falhou"]
    assert len(falhas) == 1
    assert falhas[0]["erro"] == "ErroLLMTransitorio"
    assert falhas[0]["status"] == 503


def test_falha_de_conexao_nao_tem_status_nem_id():
    from app.llm.erros import ErroLLMTransitorio

    sdk = _SdkFalso(erro=APIConnectionError(request=_RequisicaoFalsa()))
    with capture_logs() as logs:
        with pytest.raises(ErroLLMTransitorio):
            _chamar(sdk)
    falha = [log for log in logs if log["event"] == "llm_chamada_falhou"][0]
    assert falha["erro"] == "ErroLLMTransitorio"
    assert "status" not in falha
    assert "id_requisicao" not in falha


def test_falha_nao_loga_conteudo_sensivel_nem_str_do_erro():
    from app.llm.erros import ErroLLMPermanente

    with capture_logs() as logs:
        with pytest.raises(ErroLLMPermanente):
            _chamar(_SdkFalso(erro=_erro_status(400)))
    _sem_conteudo_sensivel(logs)
    assert "corpo sensivel do sdk" not in repr(logs)
