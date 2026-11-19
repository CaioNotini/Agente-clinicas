"""Interface AgendaProvider e o contrato de dados dos agendamentos (etapa 5.1).

AgendaProvider e a porta de persistencia da agenda. Nesta etapa expoe apenas as
operacoes mecanicas criar e cancelar. A disponibilidade fica para uma etapa
futura (ver docs/etapas.md, pendencia da etapa 5), por isso nao e declarada aqui.

As operacoes recebem a sessao ja aberta pelo chamador, com app.tenant_id definido
na transacao. Isso permite que o servico de remarcacao (etapa 5.3) use cancelar e
criar na mesma transacao. O provider nao abre nem fecha transacao, nao aplica
regras de negocio (antecedencia, janela, duplicidade, conflito) e nao traduz o
erro 23P01: isso e responsabilidade das regras (etapa 5.2) e do servico (5.3).

Novos agendamentos nascem com status 'agendado'. O proprio insert fixa o
tenant_id a partir de current_setting('app.tenant_id'), entao uma sessao nunca
grava para outra clinica, coerente com a policy de isolamento (ver ADR 0002).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

# Valores de status do agendamento (ver arquitetura secao 7 e ADR 0004)
STATUS_AGENDADO = "agendado"
STATUS_CANCELADO = "cancelado"


@dataclass(frozen=True)
class Agendamento:
    """Agendamento como lido do banco. inicio e fim sao aware, em UTC (timestamptz)."""

    id: int
    tenant_id: str
    profissional_id: int
    servico_id: int
    contato_telefone: str
    inicio: datetime
    fim: datetime
    status: str


class AgendamentoNaoEncontrado(Exception):
    """Operacao sobre um agendamento que nao existe para o tenant da sessao."""


class AgendaProvider(ABC):
    """Porta de persistencia da agenda. Implementacao padrao: AgendaPropria."""

    @abstractmethod
    def criar(
        self,
        session,
        *,
        profissional_id: int,
        servico_id: int,
        contato_telefone: str,
        inicio: datetime,
        fim: datetime,
    ) -> Agendamento:
        """Grava um agendamento 'agendado' na sessao aberta e devolve a linha criada."""

    @abstractmethod
    def cancelar(self, session, agendamento_id: int) -> Agendamento:
        """Marca o agendamento como 'cancelado' na sessao aberta e devolve a linha.

        Levanta AgendamentoNaoEncontrado se nenhum agendamento do tenant da sessao
        tiver esse id.
        """
