"""Interface Channel e o tipo de mensagem que entra pelo canal.

O canal recebe e envia mensagens. O restante do codigo depende so desta
interface, nunca da implementacao concreta (CLI no estudo, WhatsApp no MVP).
Ver arquitetura secao 6 (interfaces) e 8.1 (fluxo da mensagem recebida).

send_template (mensagem fora da janela de 24h) e responsabilidade do WhatsApp
e entra na etapa 17. Nao e definido aqui para nao antecipar abstracao.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MensagemEntrada:
    """Uma mensagem recebida pelo canal, pronta para ser gravada.

    O id e a chave primaria de mensagens e a base da deduplicacao: no WhatsApp
    vem da Meta, no CLI e gerado pelo proprio canal.
    """
    id: str
    tenant_id: str
    contato_telefone: str
    conteudo: str


class Channel(ABC):
    """Contrato de um canal de mensagens."""

    @abstractmethod
    def receive(self) -> Optional[MensagemEntrada]:
        """Retorna a proxima mensagem recebida, ou None quando nao ha mais."""

    @abstractmethod
    def send_text(self, contato_telefone: str, texto: str) -> None:
        """Envia uma mensagem de texto para o contato."""
