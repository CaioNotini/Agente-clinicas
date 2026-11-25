"""Contrato do cliente LLM: interface e formas de dados (etapa 6.1, ADR 0010).

A interface fica separada da implementacao (AnthropicClient, etapa 6.2) para que o
BedrockClient da etapa 16 cumpra o mesmo contrato. O suporte a ferramentas e a saida
estruturada ja entra na assinatura, porque a arquitetura preve, mas o primeiro uso
real fica para as etapas 7 e 9.

A chave da API nunca entra na ConfigLLM nem nas formas de dados: ela vai direto ao
SDK como api_key (ADR 0010). temperature, top_p e top_k tambem ficam de fora, porque
a versao 2026-10-21 da API os recusa.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChamadaFerramenta:
    """Pedido de ferramenta feito pelo modelo (function calling, etapas 7 e 9)."""

    id: str
    nome: str
    entrada: dict


@dataclass(frozen=True)
class RespostaLLM:
    """Resposta normalizada de uma chamada ao modelo, igual para qualquer provedor.

    tokens_entrada, tokens_saida e latencia_ms sao a telemetria que a tarefa 6.3 leva
    ao log estruturado. latencia_ms e medida pelo proprio cliente.
    """

    texto: str
    chamadas_ferramenta: tuple[ChamadaFerramenta, ...]
    motivo_parada: Optional[str]
    tokens_entrada: int
    tokens_saida: int
    latencia_ms: int
    modelo: str
    id_requisicao: Optional[str]


@dataclass(frozen=True)
class ConfigLLM:
    """Parametros do modelo, sem a chave da API.

    esforco guarda o esforco de raciocinio para enviar a API. Fica None por padrao,
    o que nao desliga nada: o claude-haiku-5-5 tem raciocinio adaptativo sempre
    ligado, com esforco padrao medium, e os tokens de raciocinio contam como saida,
    dentro de max_tokens. None so significa que o cliente nao sobrescreve esse
    padrao. Enviar o esforco a API ou remover o campo fica para a etapa 7 (ADR 0010).
    """

    modelo: str
    max_tokens: int
    esforco: Optional[str] = None


class LLMClient(ABC):
    """Interface unica de chamada ao modelo (ADR 0010). Implementacao: AnthropicClient."""

    @abstractmethod
    def completar(
        self,
        *,
        tenant_id,
        system: str,
        mensagens: list,
        ferramentas: Optional[list] = None,
        esquema_saida: Optional[dict] = None,
    ) -> RespostaLLM:
        """Faz uma chamada ao modelo e devolve a resposta normalizada.

        Os argumentos sao keyword-only para nenhum call site trocar a ordem sem
        perceber. tenant_id serve so ao log estruturado (etapa 6.3) e nunca vai a
        API. system e o prompt de sistema. mensagens e a lista de mensagens no
        formato do projeto, cada uma com papel e conteudo. ferramentas e
        esquema_saida sao opcionais e so entram em uso nas etapas 7 e 9.
        """
