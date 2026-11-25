"""Hierarquia de erros do cliente LLM (etapa 6.2, ADR 0010).

O AnthropicClient traduz os erros do SDK para estas classes. O worker so conhece
a diferenca entre transitorio e permanente:

- ErroLLMTransitorio: conexao, timeout, 408, 409, 429 e 5xx (inclui 529). Adianta
  tentar de novo. Cai no except Exception do worker, o job volta para pending com o
  backoff da tarefa 6.4.
- ErroLLMPermanente: 400, 401, 403, 404, 422 e demais erros de contrato. Nao muda
  entre tentativas. Herda de ErroPermanente para cair no except ErroPermanente do
  worker, que manda o job direto para dead (tarefa 5.4).

A lista de transitorios espelha o _should_retry do SDK anthropic 2.14.0 (408, 409,
429 e >= 500): com max_retries=0, o job e a unica camada de nova tentativa.
"""
from app.core.erros import ErroPermanente


class ErroLLM(Exception):
    """Raiz dos erros do LLM. Nunca e levantada sozinha, so as subclasses."""


class ErroLLMTransitorio(ErroLLM):
    """Falha que pode passar numa nova tentativa do job (conexao, timeout, 5xx)."""


class ErroLLMPermanente(ErroLLM, ErroPermanente):
    """Falha que se repetiria igual: contrato, autenticacao ou pedido invalido."""
