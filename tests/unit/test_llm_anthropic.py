"""AnthropicClient: normalizacao da resposta e traducao de erros (etapa 6.2).

O SDK entra por duble, entao os testes nao tocam a API nem a rede. As excecoes de
status sao construidas com uma resposta falsa minima, porque traduzir_erro so le
status_code e request_id delas.
"""
import pytest
from anthropic import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    BadRequestError,
)
from structlog.testing import capture_logs

from app.core.erros import ErroPermanente
from app.llm import anthropic_client
from app.llm.anthropic_client import AnthropicClient, traduzir_erro
from app.llm.base import ConfigLLM
from app.llm.erros import ErroLLM, ErroLLMPermanente, ErroLLMTransitorio

# --- dubles do SDK ---------------------------------------------------------


class _BlocoTexto:
    type = "text"

    def __init__(self, texto):
        self.text = texto


class _BlocoFerramenta:
    type = "tool_use"

    def __init__(self, id_, nome, entrada):
        self.id = id_
        self.name = nome
        self.input = entrada


class _Uso:
    def __init__(self, entrada, saida):
        self.input_tokens = entrada
        self.output_tokens = saida


class _Mensagem:
    def __init__(
        self,
        content,
        stop_reason="end_turn",
        modelo="claude-haiku",
        request_id="req_abc",
        uso=(7, 3),
    ):
        self.content = content
        self.stop_reason = stop_reason
        self.model = modelo
        self.usage = _Uso(*uso)
        self._request_id = request_id


class _SdkFalso:
    """messages.create devolve a mensagem dada ou levanta o erro dado."""

    def __init__(self, resposta=None, erro=None):
        self._resposta = resposta
        self._erro = erro
        self.chamada = None
        self.messages = self

    def create(self, **kwargs):
        self.chamada = kwargs
        if self._erro is not None:
            raise self._erro
        return self._resposta


class _RequisicaoFalsa:
    pass


class _RespostaFalsa:
    """Minimo que APIStatusError le: request, status_code e headers.get."""

    def __init__(self, status_code, request_id="req_xyz"):
        self.request = _RequisicaoFalsa()
        self.status_code = status_code
        self._headers = {"request-id": request_id}

    @property
    def headers(self):
        return self._headers


def _erro_status(status_code):
    return APIStatusError(
        "erro do sdk com corpo sensivel",
        response=_RespostaFalsa(status_code),
        body=None,
    )


_CONFIG = ConfigLLM(modelo="claude-haiku", max_tokens=1024)


# --- normalizacao ----------------------------------------------------------


def test_normaliza_texto_tokens_modelo_e_id():
    msg = _Mensagem(
        [_BlocoTexto("ola "), _BlocoTexto("mundo")],
        stop_reason="end_turn",
        modelo="claude-haiku",
        request_id="req_123",
        uso=(11, 5),
    )
    cliente = AnthropicClient(_SdkFalso(resposta=msg), _CONFIG)
    resp = cliente.completar(
        tenant_id="t_1", system="s", mensagens=[{"role": "user", "content": "oi"}]
    )
    assert resp.texto == "ola mundo"
    assert resp.tokens_entrada == 11
    assert resp.tokens_saida == 5
    assert resp.modelo == "claude-haiku"
    assert resp.id_requisicao == "req_123"
    assert resp.motivo_parada == "end_turn"
    assert resp.chamadas_ferramenta == ()


def test_normaliza_chamadas_de_ferramenta():
    msg = _Mensagem(
        [_BlocoFerramenta("tu_1", "agendar", {"dia": "2026-01-10"})],
        stop_reason="tool_use",
    )
    cliente = AnthropicClient(_SdkFalso(resposta=msg), _CONFIG)
    resp = cliente.completar(tenant_id="t_1", system="s", mensagens=[])
    assert len(resp.chamadas_ferramenta) == 1
    chamada = resp.chamadas_ferramenta[0]
    assert chamada.id == "tu_1"
    assert chamada.nome == "agendar"
    assert chamada.entrada == {"dia": "2026-01-10"}


def test_motivo_parada_desconhecido_vai_verbatim_sem_keyerror():
    msg = _Mensagem([_BlocoTexto("x")], stop_reason="motivo_novo_do_provedor")
    cliente = AnthropicClient(_SdkFalso(resposta=msg), _CONFIG)
    resp = cliente.completar(tenant_id="t_1", system="s", mensagens=[])
    assert resp.motivo_parada == "motivo_novo_do_provedor"


def test_nao_envia_parametros_de_amostragem():
    msg = _Mensagem([_BlocoTexto("x")])
    sdk = _SdkFalso(resposta=msg)
    AnthropicClient(sdk, _CONFIG).completar(tenant_id="t_1", system="s", mensagens=[])
    assert "temperature" not in sdk.chamada
    assert "top_p" not in sdk.chamada
    assert "top_k" not in sdk.chamada
    assert sdk.chamada["model"] == "claude-haiku"
    assert sdk.chamada["max_tokens"] == 1024


def test_latencia_medida_com_relogio_controlado(monkeypatch):
    tempos = iter([10.0, 10.25])  # 0,25 s entre inicio e fim
    monkeypatch.setattr(anthropic_client.time, "perf_counter", lambda: next(tempos))
    msg = _Mensagem([_BlocoTexto("x")])
    cliente = AnthropicClient(_SdkFalso(resposta=msg), _CONFIG)
    resp = cliente.completar(tenant_id="t_1", system="s", mensagens=[])
    assert resp.latencia_ms == 250


# --- traducao de erros -----------------------------------------------------


@pytest.mark.parametrize("status", [408, 409, 429, 500, 503, 529])
def test_status_transitorio(status):
    traduzido = traduzir_erro(_erro_status(status))
    assert isinstance(traduzido, ErroLLMTransitorio)
    assert not isinstance(traduzido, ErroPermanente)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
def test_status_permanente(status):
    traduzido = traduzir_erro(_erro_status(status))
    assert isinstance(traduzido, ErroLLMPermanente)
    assert isinstance(traduzido, ErroPermanente)


def test_conexao_e_timeout_sao_transitorios():
    conexao = APIConnectionError(request=_RequisicaoFalsa())
    timeout = APITimeoutError(request=_RequisicaoFalsa())
    assert isinstance(traduzir_erro(conexao), ErroLLMTransitorio)
    assert isinstance(traduzir_erro(timeout), ErroLLMTransitorio)


def test_apierror_sem_status_e_permanente():
    erro = APIResponseValidationError(
        response=_RespostaFalsa(200), body=None, message="contrato quebrado"
    )
    traduzido = traduzir_erro(erro)
    assert isinstance(traduzido, ErroLLMPermanente)
    assert isinstance(traduzido, ErroPermanente)


def test_mensagem_do_erro_nao_vaza_str_da_excecao():
    erro = BadRequestError(
        "erro do sdk com corpo sensivel",
        response=_RespostaFalsa(400),
        body=None,
    )
    traduzido = traduzir_erro(erro)
    texto = str(traduzido)
    assert "corpo sensivel" not in texto
    assert "status=400" in texto
    assert "request_id=req_xyz" in texto
    assert "BadRequestError" in texto


def test_hierarquia_dos_erros():
    assert issubclass(ErroLLMPermanente, ErroPermanente)
    assert issubclass(ErroLLMTransitorio, ErroLLM)
    assert not issubclass(ErroLLMTransitorio, ErroPermanente)


def test_erro_do_sdk_na_chamada_e_traduzido():
    cliente = AnthropicClient(_SdkFalso(erro=_erro_status(503)), _CONFIG)
    with pytest.raises(ErroLLMTransitorio):
        cliente.completar(tenant_id="t_1", system="s", mensagens=[])


# --- esquema_saida (saida estruturada, tarefa 7.2) -------------------------


@pytest.mark.parametrize("esquema", [{"type": "object"}, {}])
def test_esquema_saida_vai_ao_sdk_em_output_config(esquema):
    """Esquema preenchido, inclusive {}, vai como output_config.format json_schema."""
    sdk = _SdkFalso(resposta=_Mensagem([_BlocoTexto('{"ok": true}')]))
    cliente = AnthropicClient(sdk, _CONFIG)

    resp = cliente.completar(
        tenant_id="t_1",
        system="s",
        mensagens=[{"role": "user", "content": "oi"}],
        esquema_saida=esquema,
    )

    assert resp.texto == '{"ok": true}'
    assert sdk.chamada["output_config"] == {
        "format": {"type": "json_schema", "schema": esquema}
    }
    # O resto da chamada nao muda com o esquema
    assert sdk.chamada["model"] == "claude-haiku"
    assert sdk.chamada["messages"] == [{"role": "user", "content": "oi"}]


def test_sem_esquema_saida_chama_o_sdk_como_antes():
    sdk = _SdkFalso(resposta=_Mensagem([_BlocoTexto("ok")]))
    cliente = AnthropicClient(sdk, _CONFIG)

    resp = cliente.completar(
        tenant_id="t_1", system="s", mensagens=[{"role": "user", "content": "oi"}]
    )

    assert resp.texto == "ok"
    assert sdk.chamada == {
        "model": "claude-haiku",
        "max_tokens": 1024,
        "system": "s",
        "messages": [{"role": "user", "content": "oi"}],
        "tools": [],
    }
