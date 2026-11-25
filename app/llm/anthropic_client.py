"""Implementacao do LLMClient sobre o SDK anthropic 2.14.0 (etapa 6.2, ADR 0010).

O cliente do SDK entra por injecao, entao os testes passam um duble e nunca tocam a
API nem a rede. completar monta as mensagens no formato da versao 2026-10-21 da API
(sem temperature/top_p/top_k), mede a latencia e normaliza a resposta em RespostaLLM.

Os erros do SDK sao traduzidos para a hierarquia de app.llm.erros. A mensagem do erro
leva so o tipo, o status HTTP e o id da requisicao, nunca str(e), que poderia repetir
dados da requisicao (ADR 0010). O worker grava a mensagem em jobs.last_error.
"""
import time

import structlog
from anthropic import APIConnectionError, APIError, APIStatusError

from app.llm.base import ChamadaFerramenta, ConfigLLM, LLMClient, RespostaLLM
from app.llm.erros import ErroLLM, ErroLLMPermanente, ErroLLMTransitorio

log_estruturado = structlog.get_logger(__name__)

# Status que o SDK (e agora o job) tratam como passiveis de nova tentativa, junto com
# qualquer >= 500. Espelha _should_retry do anthropic 2.14.0. O 529 cai no ramo >= 500.
STATUS_TRANSITORIOS = frozenset({408, 409, 429})


def _e_transitorio(status: int) -> bool:
    return status in STATUS_TRANSITORIOS or status >= 500


def traduzir_erro(exc: APIError) -> ErroLLM:
    """Traduz um erro do SDK para ErroLLMTransitorio ou ErroLLMPermanente.

    Conexao e timeout (APIConnectionError) sao sempre transitorios. Erros com status
    HTTP seguem a regra de _e_transitorio. Qualquer outro APIError sem status vira
    permanente, porque nao adianta repetir um contrato quebrado.
    """
    if isinstance(exc, APIConnectionError):
        return ErroLLMTransitorio(_mensagem(type(exc).__name__, None, None))
    if isinstance(exc, APIStatusError):
        status = exc.status_code
        destino = ErroLLMTransitorio if _e_transitorio(status) else ErroLLMPermanente
        return destino(_mensagem(type(exc).__name__, status, exc.request_id))
    return ErroLLMPermanente(_mensagem(type(exc).__name__, None, None))


def _mensagem(tipo: str, status, request_id) -> str:
    # So tipo, status e id da requisicao. Nunca str(e) nem o corpo da resposta.
    partes = [tipo]
    if status is not None:
        partes.append(f"status={status}")
    if request_id:
        partes.append(f"request_id={request_id}")
    return " ".join(partes)


class AnthropicClient(LLMClient):
    """LLMClient sobre o SDK da Anthropic. Recebe o cliente do SDK por injecao."""

    def __init__(self, cliente_sdk, config: ConfigLLM):
        self._sdk = cliente_sdk
        self._config = config

    def completar(
        self,
        *,
        tenant_id,
        system: str,
        mensagens: list,
        ferramentas=None,
        esquema_saida=None,
    ) -> RespostaLLM:
        inicio = time.perf_counter()
        try:
            resposta = self._sdk.messages.create(
                model=self._config.modelo,
                max_tokens=self._config.max_tokens,
                system=system,
                messages=mensagens,
                tools=ferramentas or [],
            )
        except APIError as exc:
            latencia_ms = round((time.perf_counter() - inicio) * 1000)
            self._logar_falha(tenant_id, latencia_ms, exc)
            raise traduzir_erro(exc) from exc
        latencia_ms = round((time.perf_counter() - inicio) * 1000)
        resultado = _normalizar(resposta, latencia_ms)
        # So telemetria: tokens, latencia e identificacao. Nunca prompt, conteudo de
        # mensagem nem telefone (ADR 0010). A persistencia em tabela fica na etapa 10.
        log_estruturado.info(
            "llm_chamada",
            tenant_id=tenant_id,
            modelo=resultado.modelo,
            tokens_entrada=resultado.tokens_entrada,
            tokens_saida=resultado.tokens_saida,
            latencia_ms=resultado.latencia_ms,
            motivo_parada=resultado.motivo_parada,
            id_requisicao=resultado.id_requisicao,
        )
        return resultado

    def _logar_falha(self, tenant_id, latencia_ms, exc: APIError):
        # Evento de falha: o log do worker nao tem modelo, latencia nem request_id, e
        # o request_id e o que o suporte da Anthropic pede. Sem tokens, sem str(e),
        # sem conteudo. status e id_requisicao so existem em erros com status HTTP.
        campos = {
            "tenant_id": tenant_id,
            "modelo": self._config.modelo,
            "latencia_ms": latencia_ms,
            "erro": type(traduzir_erro(exc)).__name__,
        }
        if isinstance(exc, APIStatusError):
            campos["status"] = exc.status_code
            if exc.request_id:
                campos["id_requisicao"] = exc.request_id
        log_estruturado.warning("llm_chamada_falhou", **campos)


def _normalizar(resposta, latencia_ms: int) -> RespostaLLM:
    textos = []
    chamadas = []
    for bloco in resposta.content:
        if bloco.type == "text":
            textos.append(bloco.text)
        elif bloco.type == "tool_use":
            chamadas.append(
                ChamadaFerramenta(id=bloco.id, nome=bloco.name, entrada=bloco.input)
            )
    return RespostaLLM(
        texto="".join(textos),
        chamadas_ferramenta=tuple(chamadas),
        # stop_reason vai verbatim: valor desconhecido e guardado como veio, sem lookup.
        motivo_parada=resposta.stop_reason,
        tokens_entrada=resposta.usage.input_tokens,
        tokens_saida=resposta.usage.output_tokens,
        latencia_ms=latencia_ms,
        modelo=resposta.model,
        id_requisicao=resposta._request_id,
    )
