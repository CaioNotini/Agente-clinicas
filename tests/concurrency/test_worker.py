"""Testes do worker de jobs (etapa 3.3).

O worker sob teste conecta como worker_jobs (via WORKER_DATABASE_URL, dentro de
app/jobs/worker.py). Os dados de teste sao criados e removidos com a conta de
administracao (cnotini). Criterios 1 a 8 da especificacao da tarefa 3.3.
"""
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.config import MIGRATION_DATABASE_URL
from app.jobs.worker import (
    engine_worker,
    finalizar_job,
    processar_um,
    reivindicar_job,
    varrer_orfaos_esgotados,
)

# Conexao de administracao, usada so para preparar e limpar os dados do teste
engine_admin = create_engine(MIGRATION_DATABASE_URL)

WID = "worker-teste"


def _criar_clinica(tenant_id):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica Worker', true)"),
            {"t": tenant_id},
        )


def _limpar(tenant_id):
    with engine_admin.begin() as conexao:
        conexao.execute(text("DELETE FROM jobs WHERE tenant_id = :t"), {"t": tenant_id})
        conexao.execute(text("DELETE FROM mensagens WHERE tenant_id = :t"), {"t": tenant_id})
        conexao.execute(text("DELETE FROM clinicas WHERE tenant_id = :t"), {"t": tenant_id})


@pytest.fixture
def tenant():
    tenant_id = str(uuid.uuid4())
    _criar_clinica(tenant_id)
    yield tenant_id
    _limpar(tenant_id)


@pytest.fixture
def dois_tenants():
    a = str(uuid.uuid4())
    b = str(uuid.uuid4())
    _criar_clinica(a)
    _criar_clinica(b)
    yield a, b
    _limpar(a)
    _limpar(b)


def _inserir_job(
    tenant_id,
    tipo="PROCESS_INBOUND_MESSAGE",
    status="pending",
    attempts=0,
    max_attempts=3,
    locked_at_secs_atras=None,
    locked_by=None,
):
    locked_at_sql = (
        "NULL" if locked_at_secs_atras is None
        else f"now() - make_interval(secs => {int(locked_at_secs_atras)})"
    )
    with engine_admin.begin() as conexao:
        return conexao.execute(
            text(
                "INSERT INTO jobs (tenant_id, type, status, attempts, max_attempts, run_at, locked_at, locked_by) "
                f"VALUES (:t, :tipo, :st, :att, :mx, now(), {locked_at_sql}, :lb) RETURNING id"
            ),
            {"t": tenant_id, "tipo": tipo, "st": status, "att": attempts, "mx": max_attempts, "lb": locked_by},
        ).scalar()


def _estado(job_id):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text("SELECT status, attempts, locked_by, last_error FROM jobs WHERE id = :id"),
            {"id": job_id},
        ).first()


def test_dois_workers_so_um_processa(tenant):
    """Criterio 1: com a linha travada por uma conexao, o worker captura vazio."""
    job_id = _inserir_job(tenant)

    # Uma conexao separada segura o lock da linha (sem SKIP)
    conexao_presa = engine_worker.connect()
    transacao = conexao_presa.begin()
    conexao_presa.execute(text("SELECT id FROM jobs WHERE id = :id FOR UPDATE"), {"id": job_id})
    try:
        # O worker tenta capturar e deve pular a linha travada
        assert reivindicar_job(WID) is None
    finally:
        transacao.rollback()
        conexao_presa.close()

    # Liberada a linha, o worker captura
    job = reivindicar_job(WID)
    assert job is not None and job.id == job_id
    estado = _estado(job_id)
    assert estado.status == "processing"
    assert estado.locked_by == WID
    assert estado.attempts == 1


def test_falha_volta_a_pending_e_depois_dead(tenant):
    """Criterio 2: falha volta a pending ate max_attempts, depois dead."""
    job_id = _inserir_job(tenant, max_attempts=3)

    def falha(conexao, job):
        raise RuntimeError("falhou de proposito")

    for attempts_esperado, status_esperado in [(1, "pending"), (2, "pending"), (3, "dead")]:
        job = processar_um(WID, processamento=falha)
        assert job is not None and job.id == job_id
        estado = _estado(job_id)
        assert estado.attempts == attempts_esperado
        assert estado.status == status_esperado
        assert estado.last_error is not None

    # Esgotado: nao e mais capturado
    assert processar_um(WID, processamento=falha) is None


def test_job_preso_em_processing_e_liberado(tenant):
    """Criterio 3: job preso em processing alem do limite e repego."""
    job_id = _inserir_job(
        tenant, status="processing", attempts=0, max_attempts=3,
        locked_at_secs_atras=600, locked_by="worker-velho",
    )

    job = reivindicar_job(WID, limite_segundos=300)
    assert job is not None and job.id == job_id
    estado = _estado(job_id)
    assert estado.status == "processing"
    assert estado.locked_by == WID
    assert estado.attempts == 1


def test_define_tenant_antes_de_processar(tenant):
    """Criterio 4: app.tenant_id do job e definido antes do processamento."""
    job_id = _inserir_job(tenant)
    visto = {}

    def espiao(conexao, job):
        visto["tenant"] = conexao.execute(
            text("SELECT current_setting('app.tenant_id', true)")
        ).scalar()

    job = processar_um(WID, processamento=espiao)
    assert job is not None and job.id == job_id
    assert visto["tenant"] == tenant
    assert _estado(job_id).status == "done"


def test_sem_contexto_de_tenant_cruzado(dois_tenants):
    """Criterio 5: cada job e processado com o proprio tenant, sem vazar o anterior."""
    tenant_a, tenant_b = dois_tenants
    job_a = _inserir_job(tenant_a)
    job_b = _inserir_job(tenant_b)
    visto = {}

    def espiao(conexao, job):
        visto[job.id] = conexao.execute(
            text("SELECT current_setting('app.tenant_id', true)")
        ).scalar()

    for _ in range(10):
        if job_a in visto and job_b in visto:
            break
        processar_um(WID, processamento=espiao)

    assert visto.get(job_a) == tenant_a
    assert visto.get(job_b) == tenant_b


def test_processing_esgotado_vai_para_dead(tenant):
    """Criterio 6: job preso em processing com tentativas esgotadas vai para dead."""
    job_id = _inserir_job(
        tenant, status="processing", attempts=3, max_attempts=3,
        locked_at_secs_atras=600, locked_by="worker-velho",
    )

    marcados = varrer_orfaos_esgotados(limite_segundos=300)
    assert marcados >= 1
    estado = _estado(job_id)
    assert estado.status == "dead"
    assert estado.last_error == "expirado apos max_attempts"


def test_tipo_desconhecido_vai_para_dead(tenant):
    """Criterio 7: tipo de job desconhecido vai para dead, sem retry."""
    job_id = _inserir_job(tenant, tipo="SEND_REMINDER")

    job = processar_um(WID)
    assert job is not None and job.id == job_id
    estado = _estado(job_id)
    assert estado.status == "dead"
    assert "tipo nao suportado" in estado.last_error

    # Sem retry: nao volta a pending nem e recapturado
    assert processar_um(WID) is None


def test_worker_com_locked_by_diferente_nao_finaliza(tenant):
    """Criterio 8: worker que perdeu o lock nao finaliza o job de outro."""
    job_id = _inserir_job(tenant)
    job = reivindicar_job(WID)
    assert job is not None and job.id == job_id

    # Outro worker assume o job (simula recaptura)
    with engine_admin.begin() as conexao:
        conexao.execute(text("UPDATE jobs SET locked_by = 'outro-worker' WHERE id = :id"), {"id": job_id})

    # WID tenta finalizar como done, mas nao e mais o dono
    linhas = finalizar_job(job, WID, "done")
    assert linhas == 0
    estado = _estado(job_id)
    assert estado.status == "processing"
    assert estado.locked_by == "outro-worker"
