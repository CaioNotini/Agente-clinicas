"""Regras deterministicas de agendamento da etapa 5 (tarefa 5.2 e ADR 0009).

Funcoes puras, sem banco, aplicadas pelo servico de agendamento (5.3) antes de
gravar. A semantica de cada regra esta na secao 7 de docs/arquitetura.md.

Cada violacao levanta um erro da familia RegraViolada, que vira resposta ao
paciente. ConfiguracaoInvalida fica fora dessa familia de proposito: e erro de
cadastro da clinica e deve gerar alerta ou handoff, nunca "horario indisponivel".

A antecedencia minima e a janela de cancelamento sao diferencas entre instantes e
independem do fuso. A antecedencia maxima e o expediente sao regras de calendario e
usam o fuso da clinica, pela conversao unica de app/core/fuso.py.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Iterable, Optional

from app.agenda.base import STATUS_AGENDADO, Agendamento
from app.core.erros import ErroPermanente
from app.core.fuso import para_fuso_clinica, validar_fuso

# Politicas de cancelamento fora da janela (coluna regras_agendamento)
POLITICA_HANDOFF = "handoff"
POLITICA_ACEITAR_E_MARCAR = "aceitar_e_marcar"
_POLITICAS = (POLITICA_HANDOFF, POLITICA_ACEITAR_E_MARCAR)

# Resultado de classificar_cancelamento
DENTRO_JANELA = "dentro_janela"
ABRIR_HANDOFF = "abrir_handoff"
CANCELAR_TARDIO = "cancelar_tardio"

# Motivo de handoff aberto por cancelamento fora da janela (handoffs.motivo)
MOTIVO_CANCELAMENTO_FORA_DA_JANELA = "cancelamento_fora_da_janela"


# --- erros --------------------------------------------------------------------


class RegraViolada(Exception):
    """O pedido do paciente viola uma regra de agendamento da clinica."""


class HorarioNoPassado(RegraViolada):
    """O inicio pedido e igual ou anterior ao momento do pedido."""


class AntecedenciaInsuficiente(RegraViolada):
    """Falta menos que a antecedencia minima ate o inicio."""


class AntecedenciaExcedida(RegraViolada):
    """A data do inicio passa da antecedencia maxima, no fuso da clinica."""


class ForaDoExpediente(RegraViolada):
    """O intervalo nao cabe inteiro numa faixa de expediente do profissional."""


class HorarioIndisponivel(RegraViolada):
    """O profissional ja tem agendamento ativo que se sobrepoe ao intervalo.

    Na 5.3, so o 23P01 da constraint vira este erro. O 40P01 leva a nova tentativa
    (ADR 0004).
    """


class ConcorrenciaNaAgenda(Exception):
    """A gravacao nao conseguiu a vez na agenda do profissional (ADR 0011).

    Um 40P01 que sobrou depois das tentativas, ou um 55P03 na espera do lock da
    agenda. O horario pode estar livre, entao nao e HorarioIndisponivel. E
    transitorio: nao herda de ErroPermanente, e o job tenta de novo com backoff.
    """


class AgendamentoDuplicado(RegraViolada):
    """O contato ja tem outro agendamento ativo que se sobrepoe ao intervalo.

    O pedido repetido (mesmo profissional e mesmo inicio) nao e duplicidade: o servico
    devolve o agendamento existente (ver pedido_repetido).
    """


class ServicoNaoOferecido(RegraViolada):
    """O profissional nao faz o servico, ou um dos dois esta inativo ou nao existe
    para a clinica da sessao."""


class ConfiguracaoInvalida(ErroPermanente):
    """Cadastro da clinica incompleto ou invalido. Nao e uma RegraViolada.

    O servico de agendamento a converte em handoff (tarefa 5.4). Se escapar dele, o
    job vai direto para dead.
    """


class MisturaDeTenants(ErroPermanente):
    """A lista de agendamentos recebida tem mais de uma clinica.

    Segunda barreira de isolamento: a lista deveria vir de uma sessao app_clinicas,
    sob RLS. Indica bug na carga e nunca vira resposta ao paciente, por isso fica
    fora de RegraViolada e de ConfiguracaoInvalida.
    """


# --- configuracao ---------------------------------------------------------------


@dataclass(frozen=True)
class RegrasClinica:
    """Regras de agendamento de uma clinica. None em uma regra a desliga."""

    fuso: str
    antecedencia_minima_horas: Optional[int]
    antecedencia_maxima_dias: Optional[int]
    janela_cancelamento_horas: Optional[int]
    politica_cancelamento_fora_janela: str


@dataclass(frozen=True)
class FaixaExpediente:
    """Uma linha de horarios_trabalho. Horario de parede no fuso da clinica."""

    dia_semana: Optional[int]  # 0 = segunda, 6 = domingo
    hora_inicio: Optional[time]
    hora_fim: Optional[time]
    ativo: bool = True


def regras_da_clinica(fuso: str, linha) -> RegrasClinica:
    """Monta as regras a partir de clinicas.fuso e da linha de regras_agendamento.

    linha None (clinica sem regras cadastradas), valor negativo, politica
    desconhecida ou fuso invalido levantam ConfiguracaoInvalida.
    """
    if linha is None:
        raise ConfiguracaoInvalida("clinica sem regras_agendamento")
    try:
        validar_fuso(fuso)
    except ValueError as erro:
        raise ConfiguracaoInvalida(str(erro)) from erro
    regras = RegrasClinica(
        fuso=fuso,
        antecedencia_minima_horas=linha.antecedencia_minima_horas,
        antecedencia_maxima_dias=linha.antecedencia_maxima_dias,
        janela_cancelamento_horas=linha.janela_cancelamento_horas,
        politica_cancelamento_fora_janela=linha.politica_cancelamento_fora_janela,
    )
    for nome in (
        "antecedencia_minima_horas",
        "antecedencia_maxima_dias",
        "janela_cancelamento_horas",
    ):
        valor = getattr(regras, nome)
        if valor is not None and valor < 0:
            raise ConfiguracaoInvalida(f"{nome} negativo")
    if regras.politica_cancelamento_fora_janela not in _POLITICAS:
        raise ConfiguracaoInvalida("politica de cancelamento desconhecida")
    return regras


# --- duracao (Q-21) -------------------------------------------------------------


def resolver_duracao_minutos(duracao_servico: int, override: Optional[int]) -> int:
    """Duracao que vale no agendamento: o override do profissional, se houver.

    override None usa a duracao do servico. override 0 e um valor explicito e vence,
    porque e diferente de ausente.
    """
    return duracao_servico if override is None else override


def calcular_fim(inicio: datetime, duracao_minutos: int) -> datetime:
    """Fim do agendamento a partir do inicio e da duracao em minutos."""
    return inicio + timedelta(minutes=duracao_minutos)


# --- antecedencia -----------------------------------------------------------------


def _exigir_fuso(**instantes: datetime) -> None:
    """Sem fuso, a comparacao dependeria do fuso local do processo."""
    for nome, valor in instantes.items():
        if valor.tzinfo is None or valor.utcoffset() is None:
            raise ValueError(f"{nome} precisa ter fuso horario")


def validar_antecedencia(
    agora: datetime, inicio: datetime, regras: RegrasClinica
) -> None:
    """Recusa inicio no passado, abaixo da minima ou alem da maxima.

    A minima compara instantes. A maxima compara a data local do inicio com a data
    local de agora somada aos dias, no fuso da clinica, entao o ultimo dia vale
    inteiro.
    """
    _exigir_fuso(agora=agora, inicio=inicio)
    if inicio <= agora:
        raise HorarioNoPassado("o horario pedido ja passou")
    minima = regras.antecedencia_minima_horas
    if minima is not None and inicio - agora < timedelta(hours=minima):
        raise AntecedenciaInsuficiente(f"antecedencia minima de {minima} h")
    maxima = regras.antecedencia_maxima_dias
    if maxima is not None:
        hoje = para_fuso_clinica(agora, regras.fuso).date()
        dia = para_fuso_clinica(inicio, regras.fuso).date()
        if dia > hoje + timedelta(days=maxima):
            raise AntecedenciaExcedida(f"antecedencia maxima de {maxima} dias")


# --- expediente -----------------------------------------------------------------


def _faixas_validas(faixas: Iterable[FaixaExpediente]) -> list[FaixaExpediente]:
    """Faixas ativas, com o cadastro conferido. Faixas inativas sao ignoradas."""
    ativas = [faixa for faixa in faixas if faixa.ativo]
    if not ativas:
        raise ConfiguracaoInvalida("profissional sem faixa ativa de expediente")
    for faixa in ativas:
        if faixa.dia_semana not in range(7):
            raise ConfiguracaoInvalida(f"dia_semana invalido: {faixa.dia_semana!r}")
        if faixa.hora_inicio is None or faixa.hora_fim is None:
            raise ConfiguracaoInvalida("faixa de expediente sem hora de inicio ou fim")
        if faixa.hora_fim <= faixa.hora_inicio:
            raise ConfiguracaoInvalida("faixa de expediente com fim antes do inicio")
    return ativas


def faixas_do_dia(
    faixas: Iterable[FaixaExpediente], dia_semana: int
) -> list[tuple[time, time]]:
    """Trechos de expediente do dia, com as faixas contiguas ou sobrepostas juntas.

    Confere o cadastro de todas as faixas ativas antes (ConfiguracaoInvalida).
    Usada pela validacao do expediente e pela disponibilidade do provider.
    """
    ativas = _faixas_validas(faixas)
    trechos = sorted(
        (f.hora_inicio, f.hora_fim) for f in ativas if f.dia_semana == dia_semana
    )
    juntos: list[tuple[time, time]] = []
    for ini, fim in trechos:
        if juntos and ini <= juntos[-1][1]:
            juntos[-1] = (juntos[-1][0], max(juntos[-1][1], fim))
        else:
            juntos.append((ini, fim))
    return juntos


def validar_expediente(
    inicio: datetime, fim: datetime, faixas: Iterable[FaixaExpediente], fuso: str
) -> None:
    """Recusa o intervalo que nao cabe inteiro numa faixa do dia, no fuso da clinica.

    O dia da semana sai da data local. Um intervalo que atravessa a meia-noite local
    e recusado, porque nenhuma faixa (tipo time) passa da meia-noite.
    """
    _exigir_fuso(inicio=inicio, fim=fim)
    faixas = list(faixas)
    _faixas_validas(faixas)
    ini_local = para_fuso_clinica(inicio, fuso)
    fim_local = para_fuso_clinica(fim, fuso)
    if ini_local.date() != fim_local.date():
        raise ForaDoExpediente("o intervalo atravessa a meia-noite")
    for faixa_ini, faixa_fim in faixas_do_dia(faixas, ini_local.weekday()):
        if faixa_ini <= ini_local.time() and fim_local.time() <= faixa_fim:
            return
    raise ForaDoExpediente("fora do expediente do profissional")


# --- conflito e duplicidade -------------------------------------------------------


def intervalos_conflitam(
    inicio_a: datetime, fim_a: datetime, inicio_b: datetime, fim_b: datetime
) -> bool:
    """Sobreposicao de intervalos semiabertos [inicio, fim), como a EXCLUDE (ADR 0004).

    Intervalos adjacentes, em que um termina quando o outro comeca, nao conflitam.
    """
    return inicio_a < fim_b and inicio_b < fim_a


def _de_um_tenant_so(agendamentos: Iterable[Agendamento]) -> list[Agendamento]:
    """Materializa a lista e recusa mistura de clinicas antes de qualquer regra.

    A checagem vem antes das regras para um agendamento de outra clinica nunca
    virar HorarioIndisponivel ou AgendamentoDuplicado, o que revelaria que ele existe.
    """
    lista = list(agendamentos)
    if len({existente.tenant_id for existente in lista}) > 1:
        raise MisturaDeTenants("lista de agendamentos com mais de uma clinica")
    return lista


def verificar_conflito(
    inicio: datetime,
    fim: datetime,
    profissional_id: int,
    agendamentos: Iterable[Agendamento],
) -> None:
    """Recusa se o profissional ja tem agendamento ativo sobreposto ao intervalo.

    Serve a decisao e aos testes sem banco. Sob concorrencia, a barreira e a
    constraint EXCLUDE.
    """
    for existente in _de_um_tenant_so(agendamentos):
        if (
            existente.status == STATUS_AGENDADO
            and existente.profissional_id == profissional_id
            and intervalos_conflitam(inicio, fim, existente.inicio, existente.fim)
        ):
            raise HorarioIndisponivel("profissional ocupado nesse horario")


def verificar_duplicidade(
    inicio: datetime,
    fim: datetime,
    contato_telefone: str,
    agendamentos: Iterable[Agendamento],
    profissional_id: Optional[int] = None,
) -> None:
    """Recusa se o contato ja tem agendamento ativo sobreposto, com qualquer profissional.

    Com profissional_id, o pedido repetido (mesmo profissional e mesmo inicio) e
    ignorado, porque o servico devolve o existente em vez de recusar.

    Nao ha constraint no banco: a ordem por conversa (ADR 0005) serializa os pedidos
    do mesmo contato que chegam pela fila. Ver a ressalva na secao 7 da arquitetura.
    """
    for existente in _de_um_tenant_so(agendamentos):
        repetido = (
            existente.profissional_id == profissional_id and existente.inicio == inicio
        )
        if (
            existente.status == STATUS_AGENDADO
            and existente.contato_telefone == contato_telefone
            and not repetido
            and intervalos_conflitam(inicio, fim, existente.inicio, existente.fim)
        ):
            raise AgendamentoDuplicado("o contato ja tem agendamento nesse horario")


def pedido_repetido(
    inicio: datetime,
    profissional_id: int,
    contato_telefone: str,
    agendamentos: Iterable[Agendamento],
) -> Optional[Agendamento]:
    """O agendamento ativo do contato com o mesmo profissional e inicio, se houver.

    O pedido repetido devolve o existente, tanto na verificacao previa quanto na
    corrida que chega como 23P01 (ADR 0004).
    """
    for existente in _de_um_tenant_so(agendamentos):
        if (
            existente.status == STATUS_AGENDADO
            and existente.contato_telefone == contato_telefone
            and existente.profissional_id == profissional_id
            and existente.inicio == inicio
        ):
            return existente
    return None


# --- cancelamento (Q-22) ----------------------------------------------------------


def classificar_cancelamento(
    agora: datetime, inicio: datetime, janela_horas: Optional[int], politica: str
) -> str:
    """Classifica um pedido de cancelamento conforme a antecedencia e a politica.

    Horario que ja passou levanta HorarioNoPassado. Janela None desliga a regra.
    Dentro da janela (antecedencia maior ou igual a janela): cancelamento normal.
    Fora da janela: handoff abre handoff e so cancela apos decisao humana, e
    aceitar_e_marcar cancela na hora e marca como tardio.
    """
    _exigir_fuso(agora=agora, inicio=inicio)
    if inicio <= agora:
        raise HorarioNoPassado("o agendamento ja comecou ou passou")
    if janela_horas is None or inicio - agora >= timedelta(hours=janela_horas):
        return DENTRO_JANELA
    if politica == POLITICA_HANDOFF:
        return ABRIR_HANDOFF
    if politica == POLITICA_ACEITAR_E_MARCAR:
        return CANCELAR_TARDIO
    raise ValueError(f"politica desconhecida: {politica!r}")
