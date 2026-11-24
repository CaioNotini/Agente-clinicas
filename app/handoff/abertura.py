"""Abertura de handoff da tarefa 5.4 (ADR 0009).

Nesta etapa o handoff so e gravado em handoffs. O estado da conversa e o human_mode
nao mudam (docs/etapas.md, tarefa 5.4), e o aviso ao responsavel so e enviado a
partir da etapa 13.

Destino previsto: notificado_para recebe clinicas.telefone_plantao e
notificado_canal recebe o canal do estudo. notificado_em fica nulo ate o envio
real, e e ele que confirma que o aviso saiu.

O texto ao paciente vem so da configuracao da clinica ou do padrao neutro
(app/mensagens/fixas.py), nunca do texto de uma excecao.

Grava na sessao da conversa travada, sob RLS, sem commit. O handoff e confirmado
junto com a conclusao do job (ADR 0008).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from app.agenda.regras import ConfiguracaoInvalida
from app.mensagens.fixas import montar_texto_handoff_paciente

# Motivo do handoff aberto no lugar de ConfiguracaoInvalida (handoffs.motivo)
MOTIVO_CONFIGURACAO_INVALIDA = "configuracao_invalida"

# Canal do aviso no estudo. O WhatsApp entra na etapa 17.
CANAL_ESTUDO = "cli"

# Tamanho de handoffs.motivo
_MOTIVO_MAX = 50

# Filtro explicito de tenant, segunda barreira alem da policy (ADR 0002)
_DO_TENANT = "tenant_id = current_setting('app.tenant_id')::uuid"


@dataclass(frozen=True)
class HandoffAberto:
    id: int
    motivo: str
    texto_paciente: str
    responder_ate: Optional[datetime]


def abrir_handoff(
    travada,
    motivo: str,
    *,
    agora: datetime,
    agendamento_id: Optional[int] = None,
    mensagem_id: Optional[str] = None,
) -> HandoffAberto:
    """Grava o handoff da conversa travada e devolve o que foi informado ao paciente.

    Prazo nulo ou nao positivo conta como nao informado: sem responder_ate e sem a
    frase de prazo no texto, para um cadastro ruim do prazo nao impedir o handoff.
    """
    if agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("agora precisa ter fuso")
    if not motivo or len(motivo) > _MOTIVO_MAX:
        raise ValueError("motivo vazio ou maior que 50 caracteres")

    session = travada.session
    clinica = session.execute(
        text(
            "SELECT telefone_plantao, handoff_texto_paciente, "
            f"handoff_prazo_resposta_minutos FROM clinicas WHERE {_DO_TENANT}"
        )
    ).first()
    if clinica is None:
        raise ConfiguracaoInvalida("clinica da sessao nao encontrada")

    prazo = clinica.handoff_prazo_resposta_minutos
    if prazo is not None and prazo <= 0:
        prazo = None
    texto = montar_texto_handoff_paciente(clinica.handoff_texto_paciente, prazo)
    responder_ate = agora + timedelta(minutes=prazo) if prazo is not None else None
    plantao = clinica.telefone_plantao

    handoff_id = session.execute(
        text(
            "INSERT INTO handoffs (tenant_id, conversa_id, motivo, notificado_para, "
            "notificado_canal, texto_paciente, responder_ate, agendamento_id, "
            "mensagem_id) VALUES (current_setting('app.tenant_id')::uuid, :conversa, "
            ":motivo, :para, :canal, :texto, :ate, :agendamento, :mensagem) "
            "RETURNING id"
        ),
        {
            "conversa": travada.id,
            "motivo": motivo,
            "para": plantao,
            "canal": CANAL_ESTUDO if plantao else None,
            "texto": texto,
            "ate": responder_ate,
            "agendamento": agendamento_id,
            "mensagem": mensagem_id,
        },
    ).scalar()
    return HandoffAberto(handoff_id, motivo, texto, responder_ate)
