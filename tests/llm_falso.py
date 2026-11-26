"""LLMClient falso para os testes da classificacao (tarefa 7.2). Sem rede nem custo."""
import json

from app.llm.base import LLMClient, RespostaLLM


class ClienteFalso(LLMClient):
    """Devolve o texto dado e guarda os argumentos de cada chamada."""

    def __init__(self, texto="", motivo_parada="end_turn", erro=None):
        self.texto = texto
        self.motivo_parada = motivo_parada
        self.erro = erro
        self.chamadas = []

    def completar(self, *, tenant_id, system, mensagens, ferramentas=None, esquema_saida=None):
        self.chamadas.append(
            {
                "tenant_id": tenant_id,
                "system": system,
                "mensagens": mensagens,
                "ferramentas": ferramentas,
                "esquema_saida": esquema_saida,
            }
        )
        if self.erro is not None:
            raise self.erro
        return RespostaLLM(
            texto=self.texto,
            chamadas_ferramenta=(),
            motivo_parada=self.motivo_parada,
            tokens_entrada=10,
            tokens_saida=5,
            latencia_ms=1,
            modelo="modelo-teste",
            id_requisicao="req_teste",
        )


def saida_json(*itens):
    """Texto de saida estruturada com as intencoes dadas, como o modelo devolveria."""
    return json.dumps({"intencoes": list(itens)})
