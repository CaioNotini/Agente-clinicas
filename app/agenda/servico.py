"""Servico de agendamento: criar, remarcar, cancelar e disponibilidade (5.3 e 5.4).

Aplica as regras de app/agenda/regras.py sobre a configuracao da clinica lida do
banco e grava pelo AgendaProvider. Cada operacao recebe a ConversaTravada:
- roda sob o lock da conversa, que serializa os pedidos do mesmo contato e torna a
  duplicidade segura sem constraint (ADR 0005, secao 7 da arquitetura);
- usa a sessao app_clinicas da conversa, sob RLS, com app.tenant_id definido;
- o contato sai da conversa travada, nunca de um parametro, entao o paciente so age
  em nome do proprio telefone.

O servico nao faz commit. O efeito e a conclusao do job rodam na mesma sessao e sao
confirmados juntos (ADR 0008).

Insercao (ADR 0004): roda num SAVEPOINT. 23P01 relê a agenda e devolve o existente
no pedido repetido, ou levanta HorarioIndisponivel. Na remarcacao o pedido repetido
vira AgendamentoDuplicado, na verificacao previa e no 23P01. 40P01 e deadlock, nao
indisponibilidade: volta ao SAVEPOINT e tenta de novo, ate TENTATIVAS_DEADLOCK. Com o
lock da agenda do profissional (ADR 0011) o deadlock nao deve mais acontecer. Um
40P01 que sobrar, ou um 55P03 na espera do lock, vira ConcorrenciaNaAgenda, entao
nenhum erro cru do banco chega ao chamador. Em todos os erros tratados a transacao
externa continua utilizavel.

Handoff (5.4): o pedido fora da janela com a politica handoff grava o handoff com o
agendamento do contato. ConfiguracaoInvalida nao sobe: a operacao roda num
SAVEPOINT, o erro o desfaz, o handoff configuracao_invalida e gravado e a situacao e
AGUARDA_HANDOFF. O erro e nosso (cadastro), entao gera log de erro, sem dados do
paciente nem o texto da excecao. RegraViolada, AgendamentoNaoEncontrado e
MisturaDeTenants continuam subindo, sem handoff.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.agenda.agenda_propria import AgendaPropria
from app.agenda.base import (
    STATUS_AGENDADO,
    Agendamento,
    AgendamentoNaoEncontrado,
    AgendaProvider,
)
from app.agenda.regras import (
    ABRIR_HANDOFF,
    CANCELAR_TARDIO,
    MOTIVO_CANCELAMENTO_FORA_DA_JANELA,
    AgendamentoDuplicado,
    ConcorrenciaNaAgenda,
    ConfiguracaoInvalida,
    HorarioIndisponivel,
    RegrasClinica,
    RegraViolada,
    ServicoNaoOferecido,
    calcular_fim,
    classificar_cancelamento,
    pedido_repetido,
    regras_da_clinica,
    resolver_duracao_minutos,
    validar_antecedencia,
    validar_expediente,
    verificar_conflito,
    verificar_duplicidade,
)
from app.handoff.abertura import (
    MOTIVO_CONFIGURACAO_INVALIDA,
    HandoffAberto,
    abrir_handoff,
)

# Tentativas da insercao quando o banco aborta por deadlock (40P01)
TENTATIVAS_DEADLOCK = 3
_EXCLUSAO = "23P01"
_DEADLOCK = "40P01"
_LOCK_TIMEOUT = "55P03"

# Situacoes devolvidas pelas operacoes
CRIADO = "criado"
DISPONIVEL = "disponivel"
CANCELADO = "cancelado"
CANCELADO_TARDIO = "cancelado_tardio"
AGUARDA_HANDOFF = "aguarda_handoff"
REMARCADO = "remarcado"
INALTERADO = "inalterado"

# Filtro explicito de tenant, segunda barreira alem da policy (ADR 0002)
_DO_TENANT = "tenant_id = current_setting('app.tenant_id')::uuid"

logger = structlog.get_logger(__name__)


# Em AGUARDA_HANDOFF, handoff traz o que foi gravado e o texto ao paciente. Nada foi
# alterado na agenda. Por configuracao invalida, os agendamentos ficam None.


@dataclass(frozen=True)
class ResultadoCriacao:
    """situacao: CRIADO (novo ou pedido repetido) ou AGUARDA_HANDOFF."""

    situacao: str
    agendamento: Optional[Agendamento]
    handoff: Optional[HandoffAberto] = None


@dataclass(frozen=True)
class ResultadoDisponibilidade:
    """situacao: DISPONIVEL ou AGUARDA_HANDOFF (horarios vazio)."""

    situacao: str
    horarios: list[datetime] = field(default_factory=list)
    handoff: Optional[HandoffAberto] = None


@dataclass(frozen=True)
class ResultadoCancelamento:
    """situacao: CANCELADO, CANCELADO_TARDIO ou AGUARDA_HANDOFF (nada foi cancelado)."""

    situacao: str
    agendamento: Optional[Agendamento]
    handoff: Optional[HandoffAberto] = None


@dataclass(frozen=True)
class ResultadoRemarcacao:
    """situacao: REMARCADO, INALTERADO ou AGUARDA_HANDOFF (novo e None, nada mudou)."""

    situacao: str
    antigo: Optional[Agendamento]
    novo: Optional[Agendamento]
    handoff: Optional[HandoffAberto] = None


def _handoff_se_configuracao_invalida(
    travada,
    operacao: Callable[[], object],
    em_handoff: Callable[[HandoffAberto], object],
    *,
    agora: datetime,
    mensagem_id: Optional[str],
):
    """Roda a operacao num SAVEPOINT. ConfiguracaoInvalida vira handoff.

    O SAVEPOINT desfaz o que a operacao gravou antes do erro, como o cancelamento do
    antigo numa remarcacao. Os demais erros desfazem o SAVEPOINT e sobem, com a
    transacao externa utilizavel. O agendamento pedido nao entra no handoff: o id
    pode nao ser do contato, e a falha pode ter vindo antes dessa verificacao.
    """
    session = travada.session
    savepoint = session.begin_nested()
    try:
        resultado = operacao()
    except ConfiguracaoInvalida as erro:
        savepoint.rollback()
        aberto = abrir_handoff(
            travada, MOTIVO_CONFIGURACAO_INVALIDA, agora=agora, mensagem_id=mensagem_id
        )
        # So o tipo do erro: o texto da excecao repete ids e nao precisa ir ao log
        logger.error(
            "configuracao_invalida_em_handoff",
            tenant_id=travada.tenant_id,
            erro=type(erro).__name__,
            handoff_id=aberto.id,
        )
        return em_handoff(aberto)
    except Exception:
        savepoint.rollback()
        raise
    savepoint.commit()
    return resultado


# --- configuracao lida do banco ---------------------------------------------------


def _regras(session) -> RegrasClinica:
    fuso = session.execute(
        text(f"SELECT fuso FROM clinicas WHERE {_DO_TENANT}")
    ).scalar()
    if fuso is None:
        raise ConfiguracaoInvalida("clinica da sessao nao encontrada")
    linha = session.execute(
        text(
            "SELECT antecedencia_minima_horas, antecedencia_maxima_dias, "
            "janela_cancelamento_horas, politica_cancelamento_fora_janela "
            f"FROM regras_agendamento WHERE {_DO_TENANT}"
        )
    ).first()
    return regras_da_clinica(fuso, linha)


def _duracao(session, profissional_id: int, servico_id: int) -> int:
    """Duracao do servico com o profissional. Sem vinculo ativo: ServicoNaoOferecido."""
    linha = session.execute(
        text(
            "SELECT s.duracao_minutos AS servico, ps.duracao_minutos AS override "
            "FROM profissional_servicos ps "
            "JOIN profissionais p ON p.tenant_id = ps.tenant_id AND p.id = ps.profissional_id "
            "JOIN servicos s ON s.tenant_id = ps.tenant_id AND s.id = ps.servico_id "
            "WHERE ps.profissional_id = :prof AND ps.servico_id = :serv "
            "AND ps.tenant_id = current_setting('app.tenant_id')::uuid "
            "AND p.ativo IS NOT FALSE AND s.ativo IS NOT FALSE"
        ),
        {"prof": profissional_id, "serv": servico_id},
    ).first()
    if linha is None:
        raise ServicoNaoOferecido("o profissional nao oferece esse servico")
    duracao = resolver_duracao_minutos(linha.servico, linha.override)
    if duracao is None or duracao <= 0:
        raise ConfiguracaoInvalida("servico sem duracao positiva")
    return duracao


def _ativo_do_contato(
    session, agenda, agendamento_id: int, contato: str
) -> Agendamento:
    """O agendamento ativo do proprio contato. A mesma resposta para inexistente,
    cancelado ou de outro contato, para nao revelar o que nao e dele."""
    agendamento = agenda.obter(session, agendamento_id)
    if (
        agendamento is None
        or agendamento.status != STATUS_AGENDADO
        or agendamento.contato_telefone != contato
    ):
        raise AgendamentoNaoEncontrado(
            f"agendamento {agendamento_id} nao encontrado para este contato"
        )
    return agendamento


# --- insercao (ADR 0004) ----------------------------------------------------------


def _inserir_com_savepoint(session, agenda, campos: dict) -> Optional[Agendamento]:
    """Grava num SAVEPOINT. Devolve None no 23P01, para o chamador reler a agenda.

    40P01 volta ao SAVEPOINT e tenta de novo. O Postgres solta os locks do trecho
    desfeito. O 40P01 esgotado e o 55P03 viram ConcorrenciaNaAgenda (ADR 0011).
    Outro erro sobe como veio.
    """
    for tentativa in range(1, TENTATIVAS_DEADLOCK + 1):
        savepoint = session.begin_nested()
        try:
            novo = agenda.criar(session, **campos)
        except DBAPIError as erro:
            savepoint.rollback()
            codigo = getattr(erro.orig, "pgcode", None)
            if codigo == _EXCLUSAO:
                return None
            if codigo == _DEADLOCK and tentativa < TENTATIVAS_DEADLOCK:
                continue
            if codigo in (_DEADLOCK, _LOCK_TIMEOUT):
                # Sem o texto do erro do banco, que repete os parametros do SQL
                raise ConcorrenciaNaAgenda(
                    f"agenda do profissional ocupada (SQLSTATE {codigo})"
                ) from erro
            raise
        savepoint.commit()
        return novo
    raise AssertionError("inalcancavel: a ultima tentativa devolve ou levanta")


def _criar_na_sessao(
    session,
    regras: RegrasClinica,
    agenda: AgendaProvider,
    *,
    contato: str,
    profissional_id: int,
    servico_id: int,
    inicio: datetime,
    agora: datetime,
    aceitar_repetido: bool = True,
) -> Agendamento:
    """Valida e grava. aceitar_repetido=False (remarcacao) recusa o pedido repetido
    com AgendamentoDuplicado, na verificacao previa e no 23P01, em vez de devolver o
    agendamento existente (secao 7 da arquitetura)."""
    duracao = _duracao(session, profissional_id, servico_id)
    fim = calcular_fim(inicio, duracao)

    do_contato = agenda.listar_ativos(session, inicio, fim, contato_telefone=contato)
    if aceitar_repetido:
        existente = pedido_repetido(inicio, profissional_id, contato, do_contato)
        if existente is not None:
            return existente

    # Ordem da secao 7 da arquitetura. A duplicidade vem antes do conflito para o
    # contato que pede um horario sobreposto ao dele, mesmo com o mesmo profissional,
    # receber AgendamentoDuplicado, e nao HorarioIndisponivel.
    validar_antecedencia(agora, inicio, regras)
    validar_expediente(
        inicio, fim, agenda.expediente(session, profissional_id), regras.fuso
    )
    # Sem profissional_id, o agendamento com o mesmo profissional e inicio tambem
    # conta como duplicidade
    verificar_duplicidade(
        inicio,
        fim,
        contato,
        do_contato,
        profissional_id=profissional_id if aceitar_repetido else None,
    )
    do_profissional = agenda.listar_ativos(
        session, inicio, fim, profissional_id=profissional_id
    )
    verificar_conflito(inicio, fim, profissional_id, do_profissional)

    novo = _inserir_com_savepoint(
        session,
        agenda,
        {
            "profissional_id": profissional_id,
            "servico_id": servico_id,
            "contato_telefone": contato,
            "inicio": inicio,
            "fim": fim,
        },
    )
    if novo is not None:
        return novo

    # 23P01: outra transacao confirmou um agendamento sobreposto depois da leitura
    ocupados = agenda.listar_ativos(
        session, inicio, fim, profissional_id=profissional_id
    )
    existente = pedido_repetido(inicio, profissional_id, contato, ocupados)
    if existente is not None:
        if not aceitar_repetido:
            raise AgendamentoDuplicado("o contato ja tem agendamento nesse horario")
        return existente
    raise HorarioIndisponivel("profissional ocupado nesse horario")


# --- operacoes --------------------------------------------------------------------


def criar(
    travada,
    *,
    profissional_id: int,
    servico_id: int,
    inicio: datetime,
    agora: datetime,
    mensagem_id: Optional[str] = None,
    agenda: Optional[AgendaProvider] = None,
) -> ResultadoCriacao:
    """Cria o agendamento do contato da conversa, ou devolve o pedido repetido."""
    agenda = agenda or AgendaPropria()
    session = travada.session

    def operacao():
        novo = _criar_na_sessao(
            session,
            _regras(session),
            agenda,
            contato=travada.contato_telefone,
            profissional_id=profissional_id,
            servico_id=servico_id,
            inicio=inicio,
            agora=agora,
        )
        return ResultadoCriacao(CRIADO, novo)

    return _handoff_se_configuracao_invalida(
        travada,
        operacao,
        lambda aberto: ResultadoCriacao(AGUARDA_HANDOFF, None, aberto),
        agora=agora,
        mensagem_id=mensagem_id,
    )


def cancelar(
    travada,
    agendamento_id: int,
    *,
    agora: datetime,
    mensagem_id: Optional[str] = None,
    agenda: Optional[AgendaProvider] = None,
) -> ResultadoCancelamento:
    """Cancela conforme a janela e a politica da clinica (Q-22, ADR 0009).

    Com a politica handoff fora da janela, nada e cancelado: o handoff
    cancelamento_fora_da_janela e gravado com o agendamento e a situacao e
    AGUARDA_HANDOFF.
    """
    agenda = agenda or AgendaPropria()
    session = travada.session

    def operacao():
        regras = _regras(session)
        agendamento = _ativo_do_contato(
            session, agenda, agendamento_id, travada.contato_telefone
        )
        decisao = classificar_cancelamento(
            agora,
            agendamento.inicio,
            regras.janela_cancelamento_horas,
            regras.politica_cancelamento_fora_janela,
        )
        if decisao == ABRIR_HANDOFF:
            aberto = _handoff_fora_da_janela(travada, agendamento, agora, mensagem_id)
            return ResultadoCancelamento(AGUARDA_HANDOFF, agendamento, aberto)
        tardio = decisao == CANCELAR_TARDIO
        cancelado = agenda.cancelar(session, agendamento.id, fora_da_janela=tardio)
        return ResultadoCancelamento(
            CANCELADO_TARDIO if tardio else CANCELADO, cancelado
        )

    return _handoff_se_configuracao_invalida(
        travada,
        operacao,
        lambda aberto: ResultadoCancelamento(AGUARDA_HANDOFF, None, aberto),
        agora=agora,
        mensagem_id=mensagem_id,
    )


def remarcar(
    travada,
    agendamento_id: int,
    *,
    novo_inicio: datetime,
    agora: datetime,
    mensagem_id: Optional[str] = None,
    agenda: Optional[AgendaProvider] = None,
) -> ResultadoRemarcacao:
    """Troca o horario, com o mesmo profissional e servico.

    O antigo segue a regra de cancelamento. Fora da janela com a politica handoff,
    nada muda e o handoff e gravado com o antigo. Cancelar o antigo e criar o novo
    rodam num SAVEPOINT: se o novo for recusado, o antigo continua agendado e a
    transacao segue utilizavel.

    O pedido repetido nao vale aqui: um novo inicio que coincide com outro
    agendamento ativo do contato levanta AgendamentoDuplicado, e o antigo continua
    agendado (secao 7 da arquitetura).
    """
    agenda = agenda or AgendaPropria()
    session = travada.session
    contato = travada.contato_telefone

    def operacao():
        regras = _regras(session)
        antigo = _ativo_do_contato(session, agenda, agendamento_id, contato)
        if novo_inicio == antigo.inicio:
            return ResultadoRemarcacao(INALTERADO, antigo, antigo)

        decisao = classificar_cancelamento(
            agora,
            antigo.inicio,
            regras.janela_cancelamento_horas,
            regras.politica_cancelamento_fora_janela,
        )
        if decisao == ABRIR_HANDOFF:
            aberto = _handoff_fora_da_janela(travada, antigo, agora, mensagem_id)
            return ResultadoRemarcacao(AGUARDA_HANDOFF, antigo, None, aberto)

        savepoint = session.begin_nested()
        try:
            agenda.cancelar(
                session, antigo.id, fora_da_janela=decisao == CANCELAR_TARDIO
            )
            novo = _criar_na_sessao(
                session,
                regras,
                agenda,
                contato=contato,
                profissional_id=antigo.profissional_id,
                servico_id=antigo.servico_id,
                inicio=novo_inicio,
                agora=agora,
                aceitar_repetido=False,
            )
        except Exception:
            savepoint.rollback()
            raise
        savepoint.commit()
        return ResultadoRemarcacao(REMARCADO, antigo, novo)

    return _handoff_se_configuracao_invalida(
        travada,
        operacao,
        lambda aberto: ResultadoRemarcacao(AGUARDA_HANDOFF, None, None, aberto),
        agora=agora,
        mensagem_id=mensagem_id,
    )


def disponibilidade(
    travada,
    *,
    profissional_id: int,
    servico_id: int,
    dia: date,
    agora: datetime,
    mensagem_id: Optional[str] = None,
    agenda: Optional[AgendaProvider] = None,
) -> ResultadoDisponibilidade:
    """Inicios livres do dia local que tambem passam nas regras da clinica.

    O provider responde expediente e ocupacao. A antecedencia minima e maxima e
    aplicada aqui, por cima.
    """
    agenda = agenda or AgendaPropria()
    session = travada.session

    def operacao():
        regras = _regras(session)
        duracao = _duracao(session, profissional_id, servico_id)
        livres = []
        for inicio in agenda.disponibilidade(
            session,
            profissional_id=profissional_id,
            dia=dia,
            duracao_minutos=duracao,
            fuso=regras.fuso,
        ):
            try:
                validar_antecedencia(agora, inicio, regras)
            except RegraViolada:
                continue
            livres.append(inicio)
        return ResultadoDisponibilidade(DISPONIVEL, livres)

    return _handoff_se_configuracao_invalida(
        travada,
        operacao,
        lambda aberto: ResultadoDisponibilidade(AGUARDA_HANDOFF, [], aberto),
        agora=agora,
        mensagem_id=mensagem_id,
    )


def _handoff_fora_da_janela(
    travada, agendamento: Agendamento, agora: datetime, mensagem_id: Optional[str]
) -> HandoffAberto:
    """Handoff do cancelamento fora da janela, com o agendamento do proprio contato."""
    return abrir_handoff(
        travada,
        MOTIVO_CANCELAMENTO_FORA_DA_JANELA,
        agora=agora,
        agendamento_id=agendamento.id,
        mensagem_id=mensagem_id,
    )
