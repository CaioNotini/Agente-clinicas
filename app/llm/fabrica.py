"""Unico ponto de criacao do SDK da Anthropic e do AnthropicClient (ADR 0010).

O cliente e chamado no main() do worker, mas mora aqui, para que o modulo de jobs
nao importe o SDK e a troca de provedor (Bedrock, etapa 16) fique restrita a app/llm/.
A ligacao no main() entrou na tarefa 7.2, com a classificacao.

timeout e max_retries ficam fixos aqui, e nenhum outro lugar de app/ cria o SDK
(tests/unit/test_cliente_llm.py confere):

- max_retries=0: a nova tentativa fica numa camada so, a do job (attempts e backoff).
  O retry do SDK aconteceria dentro do lock da conversa e fora de attempts.
- timeout menor que LIMITE_LOCK_SEGUNDOS (300 s) do worker: uma chamada travada
  termina antes de o job virar orfao. Sem isso, outro worker recapturaria o job e
  pagaria uma segunda chamada. O limite vale por fase do httpx (conexao, envio,
  leitura e espera por conexao), nao no total. connect de 5 s reduz o pior caso
  somado. Na chamada sem streaming, a leitura espera a resposta inteira, entao o
  limite pratico da chamada fica perto dos 60 s.
"""
from anthropic import Anthropic, Timeout

from app.config import ler_config_llm
from app.llm.anthropic_client import AnthropicClient

TIMEOUT_LLM_SEGUNDOS = 60.0
TIMEOUT_CONEXAO_LLM_SEGUNDOS = 5.0


def criar_sdk_anthropic(chave: str) -> Anthropic:
    """Cria o SDK com timeout e max_retries fixos. A chave vai direto como api_key."""
    return Anthropic(
        api_key=chave,
        timeout=Timeout(TIMEOUT_LLM_SEGUNDOS, connect=TIMEOUT_CONEXAO_LLM_SEGUNDOS),
        max_retries=0,
    )


def criar_cliente_llm() -> AnthropicClient:
    """Le LLM_MODEL e ANTHROPIC_API_KEY e devolve o AnthropicClient da aplicacao.

    Sem alguma das variaveis, ler_config_llm levanta RuntimeError antes de criar o
    SDK, o que impede o worker de subir sem configuracao (ADR 0010).
    """
    config, chave = ler_config_llm()
    return AnthropicClient(criar_sdk_anthropic(chave), config)
