"""Processamento de mensagem recebida: lock da conversa por sessao app_clinicas (etapa 4.4).

O worker (app/jobs/worker.py) consome a fila como worker_jobs (LOGIN e BYPASSRLS),
conta que so tem acesso a tabela jobs (ver docs/decisions/0002-contas-de-banco.md).
A escrita especifica de clinica desta etapa, buscar-ou-criar e travar a conversa,
NAO pode usar essa conexao: ela roda numa sessao app_clinicas propria, sujeita ao
RLS, com app.tenant_id definido na propria transacao (via conversa_travada). O
filtro por tenant_id dentro do lock e a segunda barreira de isolamento (ADR 0002).

Esta funcao e ligada ao worker pelo ponto de extensao `processamento=` de
processar_um/rodar, sem alterar o worker. A conexao worker_jobs recebida nao e
usada para a escrita de clinica.

Escopo da etapa 4: o processamento so garante a conversa e segura o lock enquanto
o job e processado, serializando mensagens seguidas da mesma conversa. A transicao
de estado dirigida por conteudo (classificacao) entra a partir da etapa 7
(ver docs/decisions/0003-grafo-de-transicoes.md).
"""
import json

from app.core.conversas import conversa_travada
from app.db.database import SessionLocal


def _contato_do_payload(payload):
    """Extrai contato_telefone do payload do job, aceitando dict ou JSON em texto."""
    if payload is None:
        raise ValueError("job sem payload: contato_telefone ausente")
    dados = payload if isinstance(payload, dict) else json.loads(payload)
    contato = dados.get("contato_telefone")
    if not contato:
        raise ValueError("payload sem contato_telefone")
    return contato


def processar_mensagem(conexao, job, session_factory=SessionLocal):
    """Processa um PROCESS_INBOUND_MESSAGE travando a conversa via sessao app_clinicas.

    `conexao` e a conexao worker_jobs (so para a tabela jobs) e nao e usada aqui
    para escrita de clinica. A conversa (tenant_id, contato_telefone) e
    buscada-ou-criada e travada em app_clinicas, com RLS e app.tenant_id do proprio
    job. O filtro por tenant_id dentro de conversa_travada e a segunda barreira.
    """
    contato = _contato_do_payload(job.payload)
    with conversa_travada(job.tenant_id, contato, session_factory=session_factory):
        # Etapa 4: so garante a conversa e segura o lock enquanto o job e processado.
        # A transicao de estado por conteudo entra na etapa 7 (ADR 0003).
        pass
