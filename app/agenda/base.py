"""Interface AgendaProvider e o contrato de dados dos agendamentos (etapas 5.1 e 5.3).

AgendaProvider e a porta de persistencia da agenda: criar, cancelar, ler, listar os
ativos, o expediente e a disponibilidade (item C3 do plano de 2026-11-18). A disponibilidade
responde so o que uma agenda externa tambem saberia: os inicios livres segundo o
expediente e a ocupacao do profissional.

As operacoes recebem a sessao ja aberta pelo chamador, com app.tenant_id definido
na transacao. Isso permite que o servico de agendamento (app/agenda/servico.py) use
cancelar e criar na mesma transacao. O provider nao abre nem fecha transacao, nao
aplica regras de negocio (antecedencia, janela, duplicidade, conflito) e nao traduz
os erros 23P01 e 40P01 do conflito (ADR 0004): isso e responsabilidade das regras
(app/agenda/regras.py) e do servico.

Novos agendamentos nascem com status 'agendado'. O proprio insert fixa o
tenant_id a partir de current_setting('app.tenant_id'), entao uma sessao nunca
grava para outra clinica, coerente com a policy de isolamento (ver ADR 0002).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # So para a anotacao: regras.py importa este modulo
    from app.agenda.regras import FaixaExpediente

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
        """Grava um agendamento 'agendado' na sessao aberta e devolve a linha criada.

        Levanta ValueError, sem ir ao banco, se inicio ou fim nao tiverem fuso
        horario ou se fim nao for depois de inicio.
        """

    @abstractmethod
    def cancelar(
        self, session, agendamento_id: int, *, fora_da_janela: bool = False
    ) -> Agendamento:
        """Marca o agendamento como 'cancelado' na sessao aberta e devolve a linha.

        fora_da_janela grava a marca de cancelamento tardio (Q-22, ADR 0009).
        Levanta AgendamentoNaoEncontrado se nenhum agendamento ativo ('agendado')
        do tenant da sessao tiver esse id. Um agendamento ja cancelado tambem levanta.
        """

    @abstractmethod
    def obter(self, session, agendamento_id: int) -> Optional[Agendamento]:
        """O agendamento do tenant da sessao com esse id, em qualquer status, ou None."""

    @abstractmethod
    def listar_ativos(
        self,
        session,
        inicio: datetime,
        fim: datetime,
        *,
        profissional_id: Optional[int] = None,
        contato_telefone: Optional[str] = None,
    ) -> list[Agendamento]:
        """Agendamentos ativos do tenant da sessao que se sobrepoem a [inicio, fim).

        Filtra pelo profissional e pelo contato quando informados.
        """

    @abstractmethod
    def expediente(self, session, profissional_id: int) -> list["FaixaExpediente"]:
        """Faixas de expediente do profissional no tenant da sessao, sem filtrar.

        A conferencia do cadastro e a juncao das faixas ficam em app/agenda/regras.py.
        """

    @abstractmethod
    def disponibilidade(
        self,
        session,
        *,
        profissional_id: int,
        dia: date,
        duracao_minutos: int,
        fuso: str,
    ) -> list[datetime]:
        """Inicios livres do profissional no dia local, em UTC e em ordem.

        A grade anda de duracao em duracao a partir do inicio de cada faixa de
        expediente, com as faixas contiguas juntas, e tira o que se sobrepoe a um
        agendamento ativo. Nao aplica antecedencia nem outra regra da clinica.
        Levanta ConfiguracaoInvalida se o profissional nao tiver expediente valido.
        """
