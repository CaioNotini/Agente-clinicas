"""AgendaPropria: implementacao padrao de AgendaProvider sobre o banco (etapas 5.1 e 5.3).

Persistencia sem regras de negocio. Recebe a sessao ja aberta, com app.tenant_id
definido na transacao, e nao faz commit nem rollback: o ciclo da transacao e do
chamador. O servico de agendamento usa cancelar e criar na mesma sessao para a
remarcacao ser atomica.

O insert fixa o tenant_id com current_setting('app.tenant_id'), entao a linha criada
sempre pertence ao tenant da sessao, e a policy de isolamento valida o WITH CHECK.
Leituras e o cancelamento so alcancam linhas do proprio tenant: a policy restringe,
e o filtro explicito de tenant_id e a segunda barreira (ADR 0002).

Antes do insert, criar pega o lock da agenda do profissional (ADR 0011). Ele
serializa as gravacoes do mesmo profissional e evita o deadlock entre insercoes
concorrentes na constraint de exclusao, que continua sendo a barreira do conflito.
"""
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import text

from app.agenda.base import (
    STATUS_AGENDADO,
    STATUS_CANCELADO,
    Agendamento,
    AgendamentoNaoEncontrado,
    AgendaProvider,
)
from app.agenda.regras import FaixaExpediente, faixas_do_dia, intervalos_conflitam
from app.core.fuso import instante_local

# Colunas devolvidas pelo RETURNING, na ordem usada para montar o Agendamento
_COLUNAS = (
    "id, tenant_id, profissional_id, servico_id, contato_telefone, inicio, fim, status"
)

# Filtro explicito de tenant, segunda barreira alem da policy (ADR 0002)
_DO_TENANT = "tenant_id = current_setting('app.tenant_id')::uuid"


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


def _travar_agenda(session, profissional_id: int) -> None:
    """Lock de transacao da agenda do profissional, ate o commit (ADR 0011).

    Chave: hash do tenant da sessao e o id do profissional. O ::uuid faz a chamada
    falhar sem tenant na sessao, inclusive quando o setting ficou vazio de uma
    transacao anterior na mesma conexao. Dentro de um SAVEPOINT desfeito o lock e
    solto junto com a linha. Depois deste ponto, nenhuma chamada lenta (como o LLM)
    pode acontecer antes do commit, porque a agenda do profissional fica parada.
    """
    session.execute(
        text(
            "SELECT pg_advisory_xact_lock("
            "hashtext(current_setting('app.tenant_id')::uuid::text), :prof)"
        ),
        {"prof": profissional_id},
    )


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
        _travar_agenda(session, profissional_id)
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

    def cancelar(
        self, session, agendamento_id: int, *, fora_da_janela: bool = False
    ) -> Agendamento:
        # So cancela agendamento ativo: cancelar de novo nao e sucesso. O filtro de
        # tenant_id vale tambem numa conexao sem RLS.
        linha = session.execute(
            text(
                "UPDATE agendamentos SET status = :cancelado, "
                "cancelado_fora_da_janela = :tardio "
                f"WHERE id = :id AND status = :agendado AND {_DO_TENANT} "
                f"RETURNING {_COLUNAS}"
            ),
            {
                "cancelado": STATUS_CANCELADO,
                "agendado": STATUS_AGENDADO,
                "tardio": fora_da_janela,
                "id": agendamento_id,
            },
        ).first()
        if linha is None:
            raise AgendamentoNaoEncontrado(
                f"agendamento {agendamento_id} nao encontrado para o tenant da sessao"
            )
        return _para_agendamento(linha)

    def obter(self, session, agendamento_id: int) -> Optional[Agendamento]:
        linha = session.execute(
            text(
                f"SELECT {_COLUNAS} FROM agendamentos WHERE id = :id AND {_DO_TENANT}"
            ),
            {"id": agendamento_id},
        ).first()
        return None if linha is None else _para_agendamento(linha)

    def listar_ativos(
        self,
        session,
        inicio: datetime,
        fim: datetime,
        *,
        profissional_id: Optional[int] = None,
        contato_telefone: Optional[str] = None,
    ) -> list[Agendamento]:
        _validar_intervalo(inicio, fim)
        # Sobreposicao semiaberta, a mesma da constraint EXCLUDE (ADR 0004)
        sql = (
            f"SELECT {_COLUNAS} FROM agendamentos "
            f"WHERE status = :agendado AND {_DO_TENANT} "
            "AND inicio < :fim AND fim > :ini"
        )
        params = {"agendado": STATUS_AGENDADO, "ini": inicio, "fim": fim}
        if profissional_id is not None:
            sql += " AND profissional_id = :prof"
            params["prof"] = profissional_id
        if contato_telefone is not None:
            sql += " AND contato_telefone = :tel"
            params["tel"] = contato_telefone
        linhas = session.execute(text(sql + " ORDER BY inicio, id"), params)
        return [_para_agendamento(linha) for linha in linhas]

    def expediente(self, session, profissional_id: int) -> list[FaixaExpediente]:
        linhas = session.execute(
            text(
                "SELECT dia_semana, hora_inicio, hora_fim, ativo "
                f"FROM horarios_trabalho WHERE profissional_id = :prof AND {_DO_TENANT}"
            ),
            {"prof": profissional_id},
        )
        # ativo nulo conta como ativo, como o default da coluna
        return [
            FaixaExpediente(
                dia_semana=linha.dia_semana,
                hora_inicio=linha.hora_inicio,
                hora_fim=linha.hora_fim,
                ativo=linha.ativo is not False,
            )
            for linha in linhas
        ]

    def disponibilidade(
        self,
        session,
        *,
        profissional_id: int,
        dia: date,
        duracao_minutos: int,
        fuso: str,
    ) -> list[datetime]:
        if duracao_minutos <= 0:
            raise ValueError("duracao precisa ser positiva")
        trechos = faixas_do_dia(
            self.expediente(session, profissional_id), dia.weekday()
        )
        ocupados = self.listar_ativos(
            session,
            instante_local(dia, time(0), fuso),
            instante_local(dia + timedelta(days=1), time(0), fuso),
            profissional_id=profissional_id,
        )
        duracao = timedelta(minutes=duracao_minutos)
        livres = []
        for ini, fim in trechos:
            atual, limite = instante_local(dia, ini, fuso), instante_local(
                dia, fim, fuso
            )
            while atual + duracao <= limite:
                if not any(
                    intervalos_conflitam(atual, atual + duracao, o.inicio, o.fim)
                    for o in ocupados
                ):
                    livres.append(atual)
                atual += duracao
        return livres
