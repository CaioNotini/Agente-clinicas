"""Conclusao atomica do job com os efeitos do processamento (ADR 0008, item A3).

O efeito de teste e uma linha em log_auditoria, gravada pela sessao app_clinicas
da conversa, a mesma que conclui o job. Os testes provam que o efeito nao se
repete quando o worker cai entre o efeito e a conclusao, quando o job e
recapturado durante o processamento e quando o worker perde o job.

Dados de apoio e contagens usam a conta de administracao (cnotini).
"""
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.channels.base import MensagemEntrada
from app.config import MIGRATION_DATABASE_URL
from app.core.conversas import conversa_travada
from app.db.database import SessionLocal
from app.jobs import worker
from app.jobs.queue import gravar_e_enfileirar

engine_admin = create_engine(MIGRATION_DATABASE_URL)

ACAO = "efeito-teste-conclusao"
CONTATO = "(00) 90000-0801"


@pytest.fixture
def tenant():
    tenant_id = str(uuid.uuid4())
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica Conclusao', true)"),
            {"t": tenant_id},
        )
    yield tenant_id
    with engine_admin.begin() as conexao:
        for tabela in ("log_auditoria", "jobs", "mensagens", "conversas", "clinicas"):
            conexao.execute(text(f"DELETE FROM {tabela} WHERE tenant_id = :t"), {"t": tenant_id})


def _enfileirar(tenant_id):
    mensagem = MensagemEntrada(
        id=uuid.uuid4().hex, tenant_id=tenant_id, contato_telefone=CONTATO, conteudo="oi"
    )
    return gravar_e_enfileirar(mensagem).job_id


def _efeitos(tenant_id):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text("SELECT COUNT(*) FROM log_auditoria WHERE tenant_id = :t AND acao = :a"),
            {"t": tenant_id, "a": ACAO},
        ).scalar()


def _job(job_id):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text("SELECT status, attempts, locked_by, last_error FROM jobs WHERE id = :id"),
            {"id": job_id},
        ).first()


def _esperar_locked_by(job_id, worker_id, prazo=5.0, intervalo=0.02):
    """Espera o job passar a pertencer a worker_id, confirmado no banco.

    Confirma a recaptura sem depender de tempo fixo: faz poll do locked_by ate o
    prazo. Retorna True assim que confirma, False se o prazo esgotar.
    """
    limite = time.monotonic() + prazo
    while time.monotonic() < limite:
        if _job(job_id).locked_by == worker_id:
            return True
        time.sleep(intervalo)
    return False


def _processamento_com_efeito(antes_de_concluir=None, falhar=False):
    """Processamento como o da aplicacao: efeito e conclusao na sessao da conversa."""
    from app.jobs.queue import concluir_job

    def processar(conexao, job):
        with conversa_travada(job.tenant_id, job.payload["contato_telefone"]) as travada:
            travada.session.execute(
                text(
                    "INSERT INTO log_auditoria (tenant_id, acao) "
                    "VALUES (current_setting('app.tenant_id')::uuid, :a)"
                ),
                {"a": ACAO},
            )
            if antes_de_concluir is not None:
                antes_de_concluir(job)
            if falhar:
                raise RuntimeError("falha depois do efeito")
            concluir_job(travada.session, job)

    return processar


def test_controle_caminho_feliz_conclui_com_um_efeito(tenant):
    job_id = _enfileirar(tenant)

    worker.processar_um("worker-a", processamento=_processamento_com_efeito())

    assert _efeitos(tenant) == 1
    estado = _job(job_id)
    assert (estado.status, estado.locked_by, estado.last_error) == ("done", "worker-a", None)


def test_queda_entre_efeito_e_conclusao_pelo_worker_nao_duplica(tenant, monkeypatch):
    """O passo do worker depois do processamento falha, como numa queda."""
    job_id = _enfileirar(tenant)

    def queda(*args, **kwargs):
        raise RuntimeError("queda simulada")

    monkeypatch.setattr(worker, "finalizar_job", queda)
    with pytest.raises(RuntimeError):
        worker.processar_um("worker-a", processamento=_processamento_com_efeito())
    monkeypatch.undo()

    # Recaptura imediata, como apos o limite de orfao
    worker.processar_um("worker-b", processamento=_processamento_com_efeito(), limite_segundos=0)

    assert _efeitos(tenant) == 1
    assert _job(job_id).status == "done"


def test_recaptura_durante_processamento_lento_confirma_um_efeito(tenant):
    """B recaptura o job enquanto A ainda processa. So o dono atual confirma.

    Sincronizacao deterministica por threading.Event, sem sleep de tempo fixo. A
    grava o efeito e para num Event; o teste confirma a recaptura por B no banco e
    so entao libera A. A tenta concluir, nao e mais o dono e desfaz os efeitos; B
    conclui. B tambem roda numa thread: ao processar, ele espera o lock da conversa
    que A segura, entao chama-lo na thread principal travaria o teste antes de
    liberar A (deadlock).
    """
    job_id = _enfileirar(tenant)

    # A inseriu o efeito e chegou ao ponto de espera
    a_gravou_efeito = threading.Event()
    # O teste autoriza A a tentar concluir
    liberar_a = threading.Event()

    def segurar(job):
        a_gravou_efeito.set()
        # Timeout de seguranca: se o teste falhar antes de liberar, A nao fica presa.
        liberar_a.wait(timeout=10)

    def rodar_a():
        worker.processar_um(
            "worker-a",
            processamento=_processamento_com_efeito(antes_de_concluir=segurar),
        )

    def rodar_b():
        worker.processar_um(
            "worker-b", processamento=_processamento_com_efeito(), limite_segundos=0
        )

    thread_a = threading.Thread(target=rodar_a)
    thread_b = threading.Thread(target=rodar_b)

    thread_a.start()
    try:
        assert a_gravou_efeito.wait(timeout=5), "A nao chegou ao ponto de espera"
        # B recaptura o job (reivindicar_job grava locked_by antes de esperar o lock
        # da conversa). So liberamos A depois de confirmar a recaptura no banco.
        thread_b.start()
        assert _esperar_locked_by(job_id, "worker-b"), "B nao recapturou o job a tempo"
    finally:
        # Libera A mesmo se a confirmacao acima falhar, para nao vazar threads.
        liberar_a.set()

    thread_a.join(timeout=10)
    thread_b.join(timeout=10)
    assert not thread_a.is_alive() and not thread_b.is_alive(), "worker nao terminou"

    assert _efeitos(tenant) == 1
    estado = _job(job_id)
    assert (estado.status, estado.locked_by) == ("done", "worker-b")


def test_worker_que_perdeu_o_job_desfaz_os_efeitos(tenant):
    job_id = _enfileirar(tenant)

    def outro_worker_assume(job):
        with engine_admin.begin() as conexao:
            conexao.execute(
                text("UPDATE jobs SET locked_by = 'worker-outro' WHERE id = :id"), {"id": job.id}
            )

    worker.processar_um(
        "worker-a", processamento=_processamento_com_efeito(antes_de_concluir=outro_worker_assume)
    )

    assert _efeitos(tenant) == 0
    estado = _job(job_id)
    assert (estado.status, estado.locked_by, estado.attempts) == ("processing", "worker-outro", 1)


def test_controle_falha_depois_do_efeito_desfaz_e_segue_o_retry(tenant):
    job_id = _enfileirar(tenant)
    falha = _processamento_com_efeito(falhar=True)

    worker.processar_um("worker-a", processamento=falha)
    assert _efeitos(tenant) == 0
    assert (_job(job_id).status, _job(job_id).attempts) == ("pending", 1)

    worker.processar_um("worker-a", processamento=falha)
    worker.processar_um("worker-a", processamento=falha)
    assert _efeitos(tenant) == 0
    assert _job(job_id).status == "dead"


def test_captura_esta_confirmada_quando_o_processamento_comeca(tenant):
    """Se a captura seguisse aberta, o NOWAIT falharia com 55P03 (ADR 0008)."""
    job_id = _enfileirar(tenant)
    visto = {}

    def travar_por_fora(job):
        with engine_admin.connect() as conexao:
            transacao = conexao.begin()
            try:
                visto["status"] = conexao.execute(
                    text("SELECT status FROM jobs WHERE id = :id FOR UPDATE NOWAIT"),
                    {"id": job.id},
                ).scalar()
            finally:
                transacao.rollback()

    worker.processar_um(
        "worker-a", processamento=_processamento_com_efeito(antes_de_concluir=travar_por_fora)
    )

    assert visto["status"] == "processing"
    assert _job(job_id).status == "done"


def test_controle_captura_aberta_trava_a_conclusao(tenant):
    """O travamento que o ADR 0008 evita: a captura aberta segura a linha do job."""
    from app.jobs.queue import concluir_job

    _enfileirar(tenant)
    job = worker.reivindicar_job("worker-a")

    with worker.engine_worker.connect() as captura:
        transacao_captura = captura.begin()
        captura.execute(text("SELECT 1 FROM jobs WHERE id = :id FOR UPDATE"), {"id": job.id})

        session = SessionLocal()
        try:
            session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": job.tenant_id})
            session.execute(text("SELECT set_config('lock_timeout', '1000', true)"))
            with pytest.raises(OperationalError) as erro:
                concluir_job(session, job)
            assert erro.value.orig.pgcode == "55P03"  # lock_not_available
        finally:
            session.rollback()
            session.close()
            transacao_captura.rollback()
