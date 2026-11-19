"""Deduplicacao de mensagens na gravacao e no enfileiramento (etapa 3.2).

A mesma mensagem recebida duas vezes grava uma unica linha em mensagens e cria
um unico job. Uma mensagem com id diferente gera um novo job (controle).

A gravacao roda como app_clinicas (dentro de gravar_e_enfileirar). Os dados de
teste sao criados e removidos com a conta de administracao (cnotini).
"""
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.channels.base import MensagemEntrada
from app.config import MIGRATION_DATABASE_URL
from app.jobs.queue import ColisaoIdEntreTenants, TIPO_JOB_MENSAGEM, gravar_e_enfileirar

# Conexao de administracao, usada so para preparar e limpar os dados do teste
engine_admin = create_engine(MIGRATION_DATABASE_URL)

TELEFONE = "(00) 00000-0000"


def _id_unico(prefixo):
    """Id de mensagem com sufixo aleatorio. mensagens.id e PK global, entre todas
    as clinicas, entao um id fixo colidiria com dados deixados por outra execucao."""
    return f"{prefixo}-{uuid.uuid4().hex}"


@pytest.fixture
def tenant():
    """Cria uma clinica e remove tudo o que o teste gravou ao final."""
    tenant_id = uuid.uuid4()
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica Dedupe', true)"),
            {"t": str(tenant_id)},
        )
    yield str(tenant_id)
    with engine_admin.begin() as conexao:
        conexao.execute(text("DELETE FROM jobs WHERE tenant_id = :t"), {"t": str(tenant_id)})
        conexao.execute(text("DELETE FROM mensagens WHERE tenant_id = :t"), {"t": str(tenant_id)})
        conexao.execute(text("DELETE FROM clinicas WHERE tenant_id = :t"), {"t": str(tenant_id)})


@pytest.fixture
def dois_tenants():
    """Cria duas clinicas (A e B) e remove tudo o que o teste gravou ao final."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica A', true)"),
            {"t": str(tenant_a)},
        )
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica B', true)"),
            {"t": str(tenant_b)},
        )
    yield str(tenant_a), str(tenant_b)
    with engine_admin.begin() as conexao:
        for tenant_id in (str(tenant_a), str(tenant_b)):
            conexao.execute(text("DELETE FROM jobs WHERE tenant_id = :t"), {"t": tenant_id})
            conexao.execute(text("DELETE FROM mensagens WHERE tenant_id = :t"), {"t": tenant_id})
            conexao.execute(text("DELETE FROM clinicas WHERE tenant_id = :t"), {"t": tenant_id})


def _contar(tenant_id):
    with engine_admin.connect() as conexao:
        mensagens = conexao.execute(
            text("SELECT COUNT(*) FROM mensagens WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar()
        jobs = conexao.execute(
            text("SELECT COUNT(*) FROM jobs WHERE tenant_id = :t AND type = :tipo"),
            {"t": tenant_id, "tipo": TIPO_JOB_MENSAGEM},
        ).scalar()
        return mensagens, jobs


def test_mensagem_duplicada_nao_gera_segundo_job(tenant):
    msg = MensagemEntrada(id=_id_unico("msg-dedupe"), tenant_id=tenant, contato_telefone=TELEFONE, conteudo="Oi")

    # Primeira vez: grava a mensagem e cria o job
    primeiro = gravar_e_enfileirar(msg)
    assert primeiro.duplicada is False
    assert primeiro.job_id is not None

    # Mesma mensagem de novo: duplicada, sem job novo
    segundo = gravar_e_enfileirar(msg)
    assert segundo.duplicada is True
    assert segundo.job_id is None

    # So uma mensagem e um unico job no banco
    assert _contar(tenant) == (1, 1)


def test_mensagem_com_id_diferente_gera_novo_job(tenant):
    primeira = MensagemEntrada(id=_id_unico("msg-a"), tenant_id=tenant, contato_telefone=TELEFONE, conteudo="primeira")
    segunda = MensagemEntrada(id=_id_unico("msg-b"), tenant_id=tenant, contato_telefone=TELEFONE, conteudo="segunda")

    r1 = gravar_e_enfileirar(primeira)
    r2 = gravar_e_enfileirar(segunda)

    assert r1.duplicada is False and r1.job_id is not None
    assert r2.duplicada is False and r2.job_id is not None
    assert r1.job_id != r2.job_id

    # Duas mensagens distintas, dois jobs
    assert _contar(tenant) == (2, 2)


def test_mesmo_id_em_outro_tenant_levanta_colisao(dois_tenants):
    """Id de mensagem que ja existe em outro tenant nao vira 'duplicada' nem some.

    O tenant B nao enxerga a linha de A (RLS), entao gravar_e_enfileirar levanta
    a colisao explicita, sem gravar mensagem nem criar job para B.
    """
    tenant_a, tenant_b = dois_tenants

    id_compartilhado = _id_unico("colisao")
    de_a = MensagemEntrada(id=id_compartilhado, tenant_id=tenant_a, contato_telefone=TELEFONE, conteudo="de A")
    resultado_a = gravar_e_enfileirar(de_a)
    assert resultado_a.duplicada is False
    assert resultado_a.job_id is not None

    de_b = MensagemEntrada(id=id_compartilhado, tenant_id=tenant_b, contato_telefone=TELEFONE, conteudo="de B")
    with pytest.raises(ColisaoIdEntreTenants):
        gravar_e_enfileirar(de_b)

    # B nao gravou mensagem nem criou job
    assert _contar(tenant_b) == (0, 0)
