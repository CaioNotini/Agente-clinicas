"""Testes do worker de jobs (etapa 3.3).

O worker sob teste conecta como worker_jobs (via WORKER_DATABASE_URL, dentro de
app/jobs/worker.py). Os dados de teste sao criados e removidos com a conta de
administracao (cnotini). Criterios 1 a 8 da especificacao da tarefa 3.3.
"""
import dataclasses
import itertools
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from structlog.testing import capture_logs

from app.agenda.regras import ConfiguracaoInvalida, MisturaDeTenants
from app.config import MIGRATION_DATABASE_URL
from app.jobs.worker import (
    BACKOFF_BASE_SEGUNDOS,
    BACKOFF_TETO_SEGUNDOS,
    atraso_backoff,
    engine_worker,
    finalizar_job,
    processar_um,
    reivindicar_job,
    rodar,
    varrer_orfaos_esgotados,
)

# Conexao de administracao, usada so para preparar e limpar os dados do teste
engine_admin = create_engine(MIGRATION_DATABASE_URL)

WID = "worker-teste"

# Cada job de mensagem ganha uma conversa propria, para a ordem por conversa
# (ADR 0005) nao ligar jobs que estes testes tratam como independentes.
_contatos = itertools.count()


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
    contato = (
        f"(00) 90000-{next(_contatos):04d}" if tipo == "PROCESS_INBOUND_MESSAGE" else None
    )
    with engine_admin.begin() as conexao:
        return conexao.execute(
            text(
                "INSERT INTO jobs (tenant_id, type, status, contato_telefone, attempts, max_attempts, "
                "run_at, locked_at, locked_by) "
                f"VALUES (:t, :tipo, :st, :tel, :att, :mx, now(), {locked_at_sql}, :lb) RETURNING id"
            ),
            {
                "t": tenant_id, "tipo": tipo, "st": status, "tel": contato,
                "att": attempts, "mx": max_attempts, "lb": locked_by,
            },
        ).scalar()


def _estado(job_id):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text("SELECT status, attempts, locked_by, last_error FROM jobs WHERE id = :id"),
            {"id": job_id},
        ).first()


def _run_at(job_id):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text("SELECT run_at FROM jobs WHERE id = :id"), {"id": job_id}
        ).scalar()


def _zerar_run_at(job_id):
    """Volta run_at para now(), simulando o tempo de backoff ja decorrido."""
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("UPDATE jobs SET run_at = now() WHERE id = :id"), {"id": job_id}
        )


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
        # O retry adia run_at (backoff, tarefa 6.4). Zera para simular o tempo
        # decorrido e recapturar na proxima iteracao.
        if status_esperado == "pending":
            _zerar_run_at(job_id)

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


def test_finalizar_job_com_tenant_trocado_nao_altera_o_job(dois_tenants):
    """B23: o filtro tenant_id da UPDATE de finalizar_job e barreira propria.

    worker_jobs tem BYPASSRLS, entao so o filtro explicito impede que um JobCapturado
    com tenant_id errado finalize o job. Id, locked_by e status batem, so o tenant
    difere, e o atraso definido tentaria mexer em run_at.
    """
    tenant_a, tenant_b = dois_tenants
    job_id = _inserir_job(tenant_a)
    job = reivindicar_job(WID)
    assert job is not None and job.id == job_id
    run_at_antes = _run_at(job_id)

    job_trocado = dataclasses.replace(job, tenant_id=tenant_b)
    linhas = finalizar_job(
        job_trocado, WID, "pending", "erro", atraso=timedelta(seconds=60)
    )

    assert linhas == 0
    estado = _estado(job_id)
    assert estado.status == "processing"
    assert estado.locked_by == WID
    assert estado.last_error is None
    assert _run_at(job_id) == run_at_antes


class _EngineQueFalha:
    """Engine que falha nas primeiras chamadas e depois repassa ao engine real.

    Simula o banco fora do ar por um momento, sem derrubar o Postgres do teste.
    """

    def __init__(self, real, falhas):
        self.real = real
        self.falhas = falhas

    def begin(self):
        if self.falhas > 0:
            self.falhas -= 1
            raise OperationalError("SELECT 1", {}, Exception("banco fora do ar (simulado)"))
        return self.real.begin()


def test_rodar_sobrevive_a_erro_de_banco(tenant):
    """Item B4: um erro de banco no laco nao encerra o worker, que segue e processa o job."""
    job_id = _inserir_job(tenant)
    engine = _EngineQueFalha(engine_worker, falhas=2)

    rodar(
        worker_id=WID,
        processamento=lambda conexao, job: None,
        engine=engine,
        intervalo_ocioso=0,
        intervalo_erro=0,
        max_iteracoes=3,
    )

    assert engine.falhas == 0
    assert _estado(job_id).status == "done"


# --- B12: last_error sem dados da mensagem ---

TELEFONE_SENSIVEL = "(11) 98765-4321"


def test_last_error_de_erro_de_banco_nao_grava_parametros_do_sql(tenant):
    """O str() de um erro do SQLAlchemy inclui o SQL e os parametros, como o telefone."""
    job_id = _inserir_job(tenant)

    def falha_de_banco(conexao, job):
        conexao.execute(
            text("INSERT INTO tabela_que_nao_existe (telefone) VALUES (:tel)"),
            {"tel": TELEFONE_SENSIVEL},
        )

    processar_um(WID, processamento=falha_de_banco)

    last_error = _estado(job_id).last_error
    vazou = TELEFONE_SENSIVEL in last_error or "tabela_que_nao_existe" in last_error
    assert not vazou, "last_error gravou o SQL ou os parametros"
    assert last_error.startswith("ProgrammingError")


def test_last_error_de_outro_erro_guarda_tipo_e_mensagem_curta(tenant):
    job_id = _inserir_job(tenant)

    def falha_simples(conexao, job):
        raise ValueError("motivo curto")

    processar_um(WID, processamento=falha_simples)

    assert _estado(job_id).last_error == "ValueError: motivo curto"


# --- 5.4: erro permanente nao gasta as tentativas do job ---


def _inserir_mensagem_da_conversa(tenant_id, contato):
    with engine_admin.begin() as conexao:
        return conexao.execute(
            text(
                "INSERT INTO jobs (tenant_id, type, status, contato_telefone, attempts, "
                "max_attempts, run_at) VALUES (:t, 'PROCESS_INBOUND_MESSAGE', 'pending', "
                ":tel, 0, 3, now()) RETURNING id"
            ),
            {"t": tenant_id, "tel": contato},
        ).scalar()


@pytest.mark.parametrize("erro", [ConfiguracaoInvalida, MisturaDeTenants])
def test_erro_permanente_vai_para_dead_na_primeira_captura(tenant, erro):
    contato = "(00) 90000-9901"
    job_id = _inserir_mensagem_da_conversa(tenant, contato)
    seguinte = _inserir_mensagem_da_conversa(tenant, contato)

    def falha(conexao, job):
        raise erro("cadastro quebrado (00) 90000-9901")

    with capture_logs() as logs:
        assert processar_um(WID, processamento=falha).id == job_id

    estado = _estado(job_id)
    assert (estado.status, estado.attempts) == ("dead", 1)
    assert estado.last_error.startswith(erro.__name__)

    erros = [log for log in logs if log["log_level"] == "error"]
    assert len(erros) == 1
    assert (erros[0]["tenant_id"], erros[0]["job_id"], erros[0]["erro"]) == (
        tenant,
        job_id,
        erro.__name__,
    )
    assert contato not in repr(erros[0])

    # A mensagem seguinte da conversa fica livre na hora (ADR 0005)
    assert reivindicar_job(WID).id == seguinte


def test_controle_erro_comum_continua_voltando_a_pending(tenant):
    job_id = _inserir_job(tenant)

    def falha(conexao, job):
        raise RuntimeError("transitorio")

    with capture_logs() as logs:
        processar_um(WID, processamento=falha)
    assert (_estado(job_id).status, _estado(job_id).attempts) == ("pending", 1)
    assert [log for log in logs if log["log_level"] == "error"] == []


# --- 6.4: backoff no retry transitorio ---


def test_atraso_backoff_dobra_e_respeita_o_teto():
    """Funcao pura: base na 1a falha, dobro na 2a, teto quando estoura."""
    assert atraso_backoff(1) == timedelta(seconds=BACKOFF_BASE_SEGUNDOS)
    assert atraso_backoff(2) == timedelta(seconds=2 * BACKOFF_BASE_SEGUNDOS)
    # Tentativa alta: o valor exponencial passaria do teto e e cortado nele
    assert atraso_backoff(20) == timedelta(seconds=BACKOFF_TETO_SEGUNDOS)


def _run_at_no_futuro(job_id):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text("SELECT run_at > now() FROM jobs WHERE id = :id"), {"id": job_id}
        ).scalar()


def test_retry_transitorio_adia_run_at_e_job_nao_e_reelegivel(tenant):
    """Falha transitoria volta a pending com run_at no futuro, entao nao recaptura."""
    job_id = _inserir_job(tenant)

    def falha(conexao, job):
        raise RuntimeError("transitorio")

    processar_um(WID, processamento=falha)

    estado = _estado(job_id)
    assert (estado.status, estado.attempts) == ("pending", 1)
    assert _run_at_no_futuro(job_id) is True
    # run_at no futuro: o job nao e reelegivel na hora
    assert reivindicar_job(WID) is None


def test_erro_permanente_vai_para_dead_sem_adiar_run_at(tenant):
    """O caminho de dead nao mexe em run_at."""
    job_id = _inserir_job(tenant)
    run_at_antes = _run_at(job_id)

    def falha(conexao, job):
        raise ConfiguracaoInvalida("cadastro quebrado")

    processar_um(WID, processamento=falha)

    assert _estado(job_id).status == "dead"
    assert _run_at(job_id) == run_at_antes


def test_sucesso_nao_adia_run_at(tenant):
    """Done nao mexe em run_at."""
    job_id = _inserir_job(tenant)
    run_at_antes = _run_at(job_id)

    job = processar_um(WID, processamento=lambda conexao, job: None)

    assert job is not None and _estado(job_id).status == "done"
    assert _run_at(job_id) == run_at_antes
