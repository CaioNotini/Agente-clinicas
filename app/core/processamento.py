"""Processamento de mensagem recebida: lock da conversa por sessao app_clinicas (etapa 4.4).

O worker (app/jobs/worker.py) consome a fila como worker_jobs (LOGIN e BYPASSRLS),
conta que o codigo do worker usa so para a tabela jobs e que nao tem INSERT nem
UPDATE em conversas (grants completos em docs/decisions/0002-contas-de-banco.md).
A escrita especifica de clinica desta etapa, buscar-ou-criar e travar a conversa,
NAO pode usar essa conexao: ela roda numa sessao app_clinicas propria, sujeita ao
RLS, com app.tenant_id definido na propria transacao (via conversa_travada). O
filtro por tenant_id dentro do lock e a segunda barreira de isolamento (ADR 0002).

Esta funcao e ligada ao worker pelo ponto de extensao `processamento=` de
processar_um/rodar. O main() do worker a injeta com o cliente LLM (tarefa 7.2).
A conexao worker_jobs recebida nao e usada para a escrita de clinica.

Tarefa 7.2: com a conversa travada, le a mensagem do job e a classifica (regra e
LLM, app/classification/classificador.py). O resultado vai so ao log estruturado,
sem conteudo nem telefone. O estado da conversa nao muda. A transicao dirigida
pela classificacao entra nas tarefas seguintes (ADR 0003).
"""
import json
import time

import structlog
from sqlalchemy import text

from app.classification.classificador import classificar
from app.core.conversas import conversa_travada
from app.core.erros import ErroPermanente
from app.db.database import SessionLocal
from app.jobs.queue import concluir_job

log_estruturado = structlog.get_logger(__name__)


class MensagemNaoEncontrada(ErroPermanente):
    """A mensagem do job nao existe para o tenant e o contato do job."""


def _contato_do_payload(payload):
    """Extrai contato_telefone do payload do job, aceitando dict ou JSON em texto."""
    if payload is None:
        raise ValueError("job sem payload: contato_telefone ausente")
    dados = payload if isinstance(payload, dict) else json.loads(payload)
    contato = dados.get("contato_telefone")
    if not contato:
        raise ValueError("payload sem contato_telefone")
    return contato


def _mensagem_do_payload(payload):
    """Extrai mensagem_id do payload do job, aceitando dict ou JSON em texto."""
    dados = payload if isinstance(payload, dict) else json.loads(payload)
    mensagem_id = dados.get("mensagem_id")
    if not mensagem_id:
        raise ValueError("payload sem mensagem_id")
    return mensagem_id


def _ler_conteudo(session, tenant_id, mensagem_id, contato):
    """Conteudo da mensagem de entrada do job, so do tenant e do contato do job.

    O filtro por tenant_id e a segunda barreira, alem do RLS. O filtro por contato
    garante que o mensagem_id do payload e da mesma conversa: a FK so garantiria a
    mesma clinica.
    """
    conteudo = session.execute(
        text(
            "SELECT conteudo FROM mensagens "
            "WHERE tenant_id = :t AND id = :id AND contato_telefone = :tel "
            "AND direcao = 'entrada'"
        ),
        {"t": tenant_id, "id": mensagem_id, "tel": contato},
    ).scalar()
    if conteudo is None:
        # Sem ids na mensagem: o worker grava o texto em last_error
        raise MensagemNaoEncontrada(
            "mensagem do job nao encontrada no tenant e contato"
        )
    return conteudo


def _intencoes_para_log(resultado):
    return [
        {
            "categoria": intencao.categoria,
            "subtipo": intencao.subtipo,
            "confianca": intencao.confianca,
        }
        for intencao in resultado.intencoes
    ]


def processar_mensagem(conexao, job, *, cliente_llm, session_factory=SessionLocal):
    """Processa um PROCESS_INBOUND_MESSAGE travando a conversa via sessao app_clinicas.

    `conexao` e a conexao worker_jobs (so para a tabela jobs) e nao e usada aqui
    para escrita de clinica. A conversa (tenant_id, contato_telefone) e
    buscada-ou-criada e travada em app_clinicas, com RLS e app.tenant_id do proprio
    job. O filtro por tenant_id dentro de conversa_travada e a segunda barreira.
    """
    contato = _contato_do_payload(job.payload)
    mensagem_id = _mensagem_do_payload(job.payload)
    with conversa_travada(
        job.tenant_id, contato, session_factory=session_factory
    ) as travada:
        conteudo = _ler_conteudo(travada.session, job.tenant_id, mensagem_id, contato)

        # A chamada ao LLM acontece com a conversa travada, na ordem da secao 8.1.
        # Nao ha gravacao de agendamento aqui, entao nenhum lock de agenda fica
        # esperando a rede (ADR 0011).
        inicio = time.perf_counter()
        resultado = classificar(
            conteudo, cliente_llm=cliente_llm, tenant_id=job.tenant_id
        )
        log_estruturado.info(
            "classificacao",
            tenant_id=job.tenant_id,
            job_id=job.id,
            origem=resultado.origem,
            intencoes=_intencoes_para_log(resultado),
            latencia_ms=round((time.perf_counter() - inicio) * 1000),
        )

        # O estado da conversa nao muda na 7.2.
        # Conclusao na mesma transacao dos efeitos, antes do commit (ADR 0008)
        concluir_job(travada.session, job)
