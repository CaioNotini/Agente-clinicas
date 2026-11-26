"""Combinacao da regra com o LLM (tarefa 7.2, revisao de 2026-11-26 do ADR 0012).

1. A regra roda sempre primeiro. Com urgencia na regra, o resultado da regra vale e
   o LLM nao e chamado (curto-circuito). A mensagem de urgencia nao espera a rede.
2. Sem urgencia na regra, vale o resultado do LLM inteiro. A urgencia e a uniao das
   duas origens: o LLM pode acrescentar uma urgencia, nunca retirar a da regra,
   porque com a regra disparada ele nem e consultado. As demais categorias nao sao
   unidas.
3. Erro permanente do LLM (401, 400 e afins): vale a regra, na hora. O log e de
   nivel error porque uma chave revogada faria o sistema degradar para so a regra
   sem ninguem perceber (parte do C13 da rodada 5).
4. Saida invalida do LLM: vale a regra (ADR 0012), com log de aviso.
5. Erro transitorio do LLM sobe, e o job tenta de novo com backoff (ADR 0010).

Os logs levam so tenant_id e codigos fixos. Nunca o texto nem o telefone.
"""

import structlog

from app.classification.llm import SaidaInvalida, classificar_por_llm
from app.classification.regra import classificar_por_regra
from app.classification.resultado import URGENCIA, ResultadoClassificacao
from app.llm.erros import ErroLLMPermanente

log_estruturado = structlog.get_logger(__name__)


def classificar(texto: str, *, cliente_llm, tenant_id) -> ResultadoClassificacao:
    """Classifica a mensagem pela regra e, sem urgencia na regra, pelo LLM."""
    regra = classificar_por_regra(texto)
    if any(intencao.categoria == URGENCIA for intencao in regra.intencoes):
        return regra

    try:
        return classificar_por_llm(texto, cliente_llm=cliente_llm, tenant_id=tenant_id)
    except ErroLLMPermanente as erro:
        # causa e a classe do erro do SDK (AuthenticationError, BadRequestError),
        # que separa chave revogada de pedido invalido. So o nome, nunca str(e).
        causa = erro.__cause__
        log_estruturado.error(
            "classificacao_llm_erro_permanente",
            tenant_id=tenant_id,
            erro=type(erro).__name__,
            causa=type(causa).__name__ if causa is not None else None,
        )
        return regra
    except SaidaInvalida as erro:
        log_estruturado.warning(
            "classificacao_saida_invalida",
            tenant_id=tenant_id,
            motivo=erro.motivo,
        )
        return regra
