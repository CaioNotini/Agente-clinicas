"""AgendaPropria: implementacao padrao de AgendaProvider sobre o banco (etapa 5.1).

Persistencia primitiva de criar e cancelar, sem regras de negocio. Recebe a sessao
ja aberta, com app.tenant_id definido na transacao, e nao faz commit nem rollback:
o ciclo da transacao e do chamador. O servico de remarcacao (etapa 5.3) usa cancelar
e criar na mesma sessao para a operacao ser atomica.

O insert fixa o tenant_id com current_setting('app.tenant_id'), entao a linha criada
sempre pertence ao tenant da sessao, e a policy de isolamento valida o WITH CHECK.
O cancelamento so alcanca agendamentos ativos do proprio tenant: a policy restringe o
UPDATE, e o filtro explicito de tenant_id e a segunda barreira (ADR 0002).
"""
from datetime import datetime

from sqlalchemy import text

from app.agenda.base import (
    STATUS_AGENDADO,
    STATUS_CANCELADO,
    Agendamento,
    AgendamentoNaoEncontrado,
    AgendaProvider,
)

# Colunas devolvidas pelo RETURNING, na ordem usada para montar o Agendamento
_COLUNAS = (
    "id, tenant_id, profissional_id, servico_id, contato_telefone, inicio, fim, status"
)


def _para_agendamento(linha) -> Agendamento:
    return Agendamento(
        id=linha.id,
        tenant_id=str(linha.tenant_id),
        profissional_id=linha.profissional_id,
        servico_id=linha.servico_id,
        contato_telefone=linha.contato_telefone,
        inicio=linha.inicio,
        fim=linha.fim,
        status=linha.status,
    )


def _validar_intervalo(inicio: datetime, fim: datetime) -> None:
    """Rejeita o intervalo antes de ir ao banco.

    Sem fuso, o timestamptz interpretaria o horario pelo TimeZone da sessao, e o
    mesmo valor viraria instantes diferentes conforme a conexao.
    """
    for nome, valor in (("inicio", inicio), ("fim", fim)):
        if valor.tzinfo is None or valor.utcoffset() is None:
            raise ValueError(f"{nome} precisa ter fuso horario")
    if fim <= inicio:
        raise ValueError("fim precisa ser depois de inicio")


class AgendaPropria(AgendaProvider):
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
        _validar_intervalo(inicio, fim)
        # tenant_id vem do proprio setting da sessao, nunca de um parametro do cliente
        linha = session.execute(
            text(
                "INSERT INTO agendamentos "
                "(tenant_id, profissional_id, servico_id, contato_telefone, inicio, fim, status) "
                "VALUES (current_setting('app.tenant_id')::uuid, :prof, :serv, :tel, :ini, :fim, 'agendado') "
                f"RETURNING {_COLUNAS}"
            ),
            {
                "prof": profissional_id,
                "serv": servico_id,
                "tel": contato_telefone,
                "ini": inicio,
                "fim": fim,
            },
        ).first()
        return _para_agendamento(linha)

    def cancelar(self, session, agendamento_id: int) -> Agendamento:
        # So cancela agendamento ativo: cancelar de novo nao e sucesso. O filtro de
        # tenant_id e a segunda barreira (ADR 0002). A policy ja restringe o UPDATE ao
        # tenant da sessao, mas o filtro vale tambem numa conexao sem RLS.
        linha = session.execute(
            text(
                "UPDATE agendamentos SET status = :cancelado "
                "WHERE id = :id AND status = :agendado "
                "AND tenant_id = current_setting('app.tenant_id')::uuid "
                f"RETURNING {_COLUNAS}"
            ),
            {
                "cancelado": STATUS_CANCELADO,
                "agendado": STATUS_AGENDADO,
                "id": agendamento_id,
            },
        ).first()
        if linha is None:
            raise AgendamentoNaoEncontrado(
                f"agendamento {agendamento_id} nao encontrado para o tenant da sessao"
            )
        return _para_agendamento(linha)
