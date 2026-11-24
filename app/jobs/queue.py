"""Gravacao da mensagem recebida e criacao do job de processamento.

Recebe e processa sao etapas separadas, ligadas pela fila no banco (D-06).
Esta parte (etapa 3.2) faz a primeira metade: grava a mensagem e enfileira um
job PROCESS_INBOUND_MESSAGE. O worker (etapa 3.3) consome o job depois.

Roda como a conta da aplicacao (app_clinicas), sujeita ao RLS: o tenant da
mensagem e definido na transacao antes de qualquer escrita.

Deduplicacao: mensagens.id e a chave primaria. A gravacao usa
ON CONFLICT (id) DO NOTHING, e o job so e criado quando a mensagem e nova.
Assim uma mensagem repetida nao gera um segundo processamento.

mensagens.id e PK global (uma unicidade sobre id, compartilhada entre tenants),
e o conflito do indice unico e checado fora do RLS. Por isso, quando o insert
nao acontece, e preciso distinguir dois casos sob o RLS do tenant atual:
a linha existe e e visivel para o tenant (duplicata de verdade), ou a linha
existe mas pertence a outro tenant (colisao de id). No segundo caso a funcao
levanta ColisaoIdEntreTenants em vez de descartar a mensagem em silencio.

Pendencia para a etapa 17 (WhatsAppClient), sem implementar agora: avaliar
deduplicacao por (tenant_id, id). Em producao, o id vem da Meta e e globalmente
unico, entao a PK global basta; a unicidade por tenant so seria necessaria se
esse pressuposto mudar.
"""
import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text

from app.channels.base import MensagemEntrada
from app.db.database import SessionLocal

# Tipo de job que representa uma mensagem recebida a processar (arquitetura secao 7)
TIPO_JOB_MENSAGEM = "PROCESS_INBOUND_MESSAGE"


class ColisaoIdEntreTenants(Exception):
    """A id da mensagem ja existe, mas pertence a outro tenant.

    Nao e uma duplicata do tenant atual: a mensagem nao pode ser gravada com
    esse id e nao deve ser descartada em silencio.
    """


class JobPerdido(Exception):
    """O job nao pertence mais a este worker: foi recapturado por outro (ADR 0008)."""


def concluir_job(session, job) -> None:
    """Marca o job como done na sessao app_clinicas que gravou os efeitos (ADR 0008).

    Roda antes do commit da sessao, para efeito e conclusao serem confirmados
    juntos. So conclui se o job ainda estiver em processing com este worker. Se
    outro worker o recapturou, levanta JobPerdido, e o chamador desfaz a transacao
    inteira, efeitos incluidos. O filtro de tenant_id e a segunda barreira da policy.
    """
    resultado = session.execute(
        text(
            "UPDATE jobs SET status = 'done', last_error = NULL "
            "WHERE id = :id AND tenant_id = current_setting('app.tenant_id')::uuid "
            "AND locked_by = :w AND status = 'processing'"
        ),
        {"id": job.id, "w": job.worker_id},
    )
    if resultado.rowcount != 1:
        raise JobPerdido(f"job {job.id} nao pertence mais ao worker {job.worker_id}")


@dataclass(frozen=True)
class ResultadoEnfileiramento:
    """Resultado de gravar e enfileirar uma mensagem.

    duplicada=True quando a mensagem ja existia, caso em que nenhum job novo e
    criado e job_id fica None.
    """

    duplicada: bool
    job_id: Optional[int]


def gravar_e_enfileirar(mensagem: MensagemEntrada) -> ResultadoEnfileiramento:
    session = SessionLocal()
    try:
        # Define o tenant so para esta transacao, como o codigo da aplicacao faria
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": mensagem.tenant_id},
        )

        # Grava a mensagem; se o id ja existe, nao faz nada (deduplicacao pela PK)
        inserida = session.execute(
            text(
                "INSERT INTO mensagens (id, tenant_id, contato_telefone, conteudo, direcao) "
                "VALUES (:id, :t, :tel, :conteudo, 'entrada') "
                "ON CONFLICT (id) DO NOTHING "
                "RETURNING id"
            ),
            {
                "id": mensagem.id,
                "t": mensagem.tenant_id,
                "tel": mensagem.contato_telefone,
                "conteudo": mensagem.conteudo,
            },
        ).first()

        if inserida is None:
            # Nao inseriu. So enxergamos a linha se ela for deste tenant: a policy
            # restringe, e o filtro explicito e a segunda barreira (ADR 0002). Sem o
            # filtro, numa conexao sem RLS a colisao viraria duplicata e sumiria.
            visivel = session.execute(
                text(
                    "SELECT 1 FROM mensagens WHERE id = :id "
                    "AND tenant_id = current_setting('app.tenant_id')::uuid"
                ),
                {"id": mensagem.id},
            ).first()
            if visivel is None:
                # Existe no indice, mas nao e visivel: pertence a outro tenant
                raise ColisaoIdEntreTenants(
                    f"id de mensagem '{mensagem.id}' ja existe em outro tenant"
                )
            # Duplicata do proprio tenant: nada gravado, nenhum job criado
            session.commit()
            return ResultadoEnfileiramento(duplicada=True, job_id=None)

        # Mensagem nova: cria o job de processamento, no mesmo tenant. A coluna
        # contato_telefone identifica a conversa para a ordem de captura (ADR 0005).
        payload = json.dumps(
            {"mensagem_id": mensagem.id, "contato_telefone": mensagem.contato_telefone}
        )
        job_id = session.execute(
            text(
                "INSERT INTO jobs (tenant_id, type, status, payload, contato_telefone, "
                "run_at, attempts, max_attempts) "
                "VALUES (:t, :tipo, 'pending', CAST(:payload AS JSON), :tel, now(), 0, 3) "
                "RETURNING id"
            ),
            {
                "t": mensagem.tenant_id,
                "tipo": TIPO_JOB_MENSAGEM,
                "payload": payload,
                "tel": mensagem.contato_telefone,
            },
        ).scalar()

        session.commit()
        return ResultadoEnfileiramento(duplicada=False, job_id=job_id)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
