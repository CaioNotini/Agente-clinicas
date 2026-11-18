"""Ordem de processamento por conversa (etapa 4, ADR 0005).

O worker so captura um job se nao existir outro job pending ou processing,
mais antigo, da mesma conversa (tenant_id, contato_telefone). Jobs sem conversa
ficam fora da regra.

As mensagens entram pelo caminho real (gravar_e_enfileirar, conta app_clinicas).
O worker conecta como worker_jobs. Os dados sao criados e removidos com a conta
de administracao (cnotini).
"""
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.channels.base import MensagemEntrada
from app.config import MIGRATION_DATABASE_URL
from app.core.conversas import conversa_travada
from app.jobs.queue import gravar_e_enfileirar
from app.jobs.worker import finalizar_job, processar_um, reivindicar_job

engine_admin = create_engine(MIGRATION_DATABASE_URL)

CONTATO = "(00) 00000-0101"
OUTRO_CONTATO = "(00) 00000-0102"

# Tempo que o processamento lento segura o lock da conversa
LENTO = 0.4

# Limite de cada teste com threads, abaixo do timeout de 10 s do pytest.ini
PRAZO = 8.0


def _criar_clinica(tenant_id):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica Ordem', true)"),
            {"t": tenant_id},
        )


def _limpar(tenant_id):
    with engine_admin.begin() as conexao:
        for tabela in ("jobs", "mensagens", "conversas", "clinicas"):
            conexao.execute(text(f"DELETE FROM {tabela} WHERE tenant_id = :t"), {"t": tenant_id})


@pytest.fixture
def tenant():
    tenant_id = str(uuid.uuid4())
    _criar_clinica(tenant_id)
    yield tenant_id
    _limpar(tenant_id)


@pytest.fixture
def dois_tenants():
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    _criar_clinica(a)
    _criar_clinica(b)
    yield a, b
    _limpar(a)
    _limpar(b)


def _enfileirar(tenant_id, contato=CONTATO):
    """Grava uma mensagem e cria o job pelo caminho da aplicacao. Devolve o job_id."""
    resultado = gravar_e_enfileirar(
        MensagemEntrada(id=uuid.uuid4().hex, tenant_id=tenant_id, contato_telefone=contato, conteudo="oi")
    )
    return resultado.job_id


def _inserir_job_sem_conversa(tenant_id):
    """Job sem conversa (como um lembrete futuro), com os valores de controle explicitos."""
    with engine_admin.begin() as conexao:
        return conexao.execute(
            text(
                "INSERT INTO jobs (tenant_id, type, status, run_at, attempts, max_attempts) "
                "VALUES (:t, 'SEND_REMINDER', 'pending', now(), 0, 3) RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar()


def _estados(ids):
    with engine_admin.connect() as conexao:
        linhas = conexao.execute(
            text("SELECT id, status, attempts FROM jobs WHERE id = ANY(:ids)"),
            {"ids": list(ids)},
        ).all()
    return {linha.id: (linha.status, linha.attempts) for linha in linhas}


def _em_processing(tenant_id, contato):
    """Quantos jobs da conversa estao em processing agora (lido fora do worker)."""
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text(
                "SELECT count(*) FROM jobs WHERE tenant_id = :t AND status = 'processing' "
                "AND payload->>'contato_telefone' = :tel"
            ),
            {"t": tenant_id, "tel": contato},
        ).scalar()


def _rodar_workers(n_workers, processamento, ids):
    """Roda n workers ate todos os jobs dados terminarem em done ou dead, ou o prazo vencer.

    Um worker que nao acha job elegivel espera e tenta de novo, porque um job
    bloqueado pela ordem pode ficar elegivel depois.
    """
    fim = time.monotonic() + PRAZO

    def terminados():
        return all(st in ("done", "dead") for st, _ in _estados(ids).values())

    def laco():
        wid = uuid.uuid4().hex
        while time.monotonic() < fim:
            if processar_um(wid, processamento=processamento) is None:
                if terminados():
                    return
                time.sleep(0.05)

    threads = [threading.Thread(target=laco) for _ in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=PRAZO + 1)
    assert all(not t.is_alive() for t in threads), "worker nao terminou no prazo"
    assert terminados(), f"jobs nao terminaram: {_estados(ids)}"


def test_job_seguinte_nao_e_capturado_enquanto_anterior_processa(tenant):
    """Com a mensagem 1 em processing, a 2 da mesma conversa nao e capturada."""
    j1 = _enfileirar(tenant)
    j2 = _enfileirar(tenant)

    capturado_a = reivindicar_job("worker-a")
    assert capturado_a is not None and capturado_a.id == j1

    assert reivindicar_job("worker-b") is None
    assert _estados([j2])[j2] == ("pending", 0), "job bloqueado nao pode gastar tentativa"

    # Terminada a 1, a 2 fica elegivel
    finalizar_job(capturado_a, "worker-a", "done")
    capturado_b = reivindicar_job("worker-b")
    assert capturado_b is not None and capturado_b.id == j2


def test_dois_workers_processamento_lento_respeita_ordem(tenant):
    """Dois workers, mesma conversa, processamento lento: um job por vez, na ordem."""
    ids = [_enfileirar(tenant) for _ in range(3)]
    ordem = []
    simultaneos = []
    registro = threading.Lock()

    def lento(conexao, job):
        with conversa_travada(job.tenant_id, job.payload["contato_telefone"]):
            simultaneos.append(_em_processing(tenant, CONTATO))
            time.sleep(LENTO)
            with registro:
                ordem.append(job.id)

    _rodar_workers(2, lento, ids)

    assert ordem == ids
    assert max(simultaneos) == 1, "dois jobs da mesma conversa em processing ao mesmo tempo"
    assert all(estado == ("done", 1) for estado in _estados(ids).values())


def test_falha_da_mensagem_1_nao_deixa_a_2_e_a_3_passarem(tenant):
    """A 1 falha na primeira tentativa: a 2 e a 3 so rodam depois que a 1 conclui."""
    j1, j2, j3 = ids = [_enfileirar(tenant) for _ in range(3)]
    sucessos = []
    tentativas_j1 = []
    registro = threading.Lock()

    def falha_uma_vez(conexao, job):
        with conversa_travada(job.tenant_id, job.payload["contato_telefone"]):
            if job.id == j1 and job.attempts == 1:
                tentativas_j1.append(job.attempts)
                time.sleep(LENTO)
                raise RuntimeError("falha de proposito na primeira tentativa")
            with registro:
                sucessos.append(job.id)

    _rodar_workers(2, falha_uma_vez, ids)

    assert sucessos == [j1, j2, j3]
    assert _estados(ids) == {j1: ("done", 2), j2: ("done", 1), j3: ("done", 1)}


def test_mensagem_que_esgota_tentativas_vai_para_dead_e_libera_as_seguintes(tenant):
    """A 1 falha sempre: vai para dead apos max_attempts, e so entao a 2 e a 3 rodam, em ordem."""
    j1, j2, j3 = ids = [_enfileirar(tenant) for _ in range(3)]
    eventos = []
    registro = threading.Lock()

    def falha_sempre_na_1(conexao, job):
        with conversa_travada(job.tenant_id, job.payload["contato_telefone"]):
            with registro:
                eventos.append(job.id)
            if job.id == j1:
                time.sleep(0.1)
                raise RuntimeError("falha permanente de proposito")

    _rodar_workers(2, falha_sempre_na_1, ids)

    assert eventos == [j1, j1, j1, j2, j3]
    assert _estados(ids) == {j1: ("dead", 3), j2: ("done", 1), j3: ("done", 1)}


def test_conversa_bloqueada_nao_bloqueia_outras(dois_tenants):
    """Outra conversa da mesma clinica e o mesmo contato em outra clinica seguem livres."""
    tenant_a, tenant_b = dois_tenants
    j1 = _enfileirar(tenant_a, CONTATO)
    j2 = _enfileirar(tenant_a, CONTATO)
    outro_contato = _enfileirar(tenant_a, OUTRO_CONTATO)
    outra_clinica = _enfileirar(tenant_b, CONTATO)

    capturados = [reivindicar_job("w1"), reivindicar_job("w2"), reivindicar_job("w3")]
    assert [c.id for c in capturados if c] == [j1, outro_contato, outra_clinica]

    # A 2 continua bloqueada pela 1, que segue em processing
    assert reivindicar_job("w4") is None
    assert _estados([j2])[j2] == ("pending", 0)


def test_jobs_sem_conversa_nao_bloqueiam_nem_sao_bloqueados(tenant):
    """Um job sem conversa nao segura jobs de conversa, e um job de conversa nao o segura."""
    sem_conversa_1 = _inserir_job_sem_conversa(tenant)
    c1 = _enfileirar(tenant)
    c2 = _enfileirar(tenant)
    sem_conversa_2 = _inserir_job_sem_conversa(tenant)

    # O job sem conversa em processing nao bloqueia c1
    assert reivindicar_job("w1").id == sem_conversa_1
    assert reivindicar_job("w2").id == c1
    # c1 em processing bloqueia c2, mas nao o segundo job sem conversa
    assert reivindicar_job("w3").id == sem_conversa_2
    assert reivindicar_job("w4") is None
    assert _estados([c2])[c2] == ("pending", 0)
