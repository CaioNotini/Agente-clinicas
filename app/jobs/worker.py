"""Worker de jobs: consome a fila e executa jobs, sem IA (etapa 3.3).

Fecha a segunda metade do fluxo da secao 8.1 da arquitetura. Receber (3.2) e
processar (3.3) sao etapas separadas, ligadas pela fila no banco (D-06).

Conexao: o worker usa WORKER_DATABASE_URL, a conta worker_jobs (LOGIN e
BYPASSRLS), conforme docs/decisions/0002-contas-de-banco.md. Nunca usa
DATABASE_URL. worker_jobs ignora o RLS, entao a captura cross-tenant da fila
nao depende de app.tenant_id.

Processamento: a funcao de processamento e um ponto de extensao
(`processamento=`). O laco rodar() usa por padrao processar_mensagem
(app/core/processamento.py, etapa 4.4). processar_um mantem processamento_vazio
como padrao, para uso direto e testes.

Escritas especificas de clinica passam por uma sessao app_clinicas, com RLS de
fato, dentro de processar_mensagem. O worker usa worker_jobs apenas para a
tabela jobs. O filtro explicito de tenant_id e a segunda barreira. Na conexao
worker_jobs, app.tenant_id e contrato de contexto, nao barreira.

Pendencia da etapa 6: nao ha backoff. No retry, run_at fica inalterado, entao o
job volta a ficar elegivel imediatamente.
"""
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy import create_engine, text

from app.config import WORKER_DATABASE_URL
from app.core.processamento import processar_mensagem

# Engine do worker, conectado com a conta worker_jobs (BYPASSRLS)
engine_worker = create_engine(WORKER_DATABASE_URL)

# Tempo acima do qual um job preso em processing e considerado orfao
LIMITE_LOCK_SEGUNDOS = 300

# Tipos de job que este worker sabe processar nesta etapa
TIPOS_SUPORTADOS = ("PROCESS_INBOUND_MESSAGE",)


@dataclass(frozen=True)
class JobCapturado:
    id: int
    tenant_id: str
    type: str
    payload: Optional[dict]
    attempts: int
    max_attempts: int


def processamento_vazio(conexao, job: JobCapturado) -> None:
    """Processamento que nao faz nada. Padrao de processar_um."""
    return None


def reivindicar_job(
    worker_id: str,
    limite_segundos: int = LIMITE_LOCK_SEGUNDOS,
    engine=engine_worker,
) -> Optional[JobCapturado]:
    """Captura um job em uma unica transacao e o marca como processing.

    O SELECT ... FOR UPDATE SKIP LOCKED e o UPDATE ficam na mesma transacao,
    sem janela entre eles, entao dois workers nao pegam o mesmo job. attempts
    incrementa aqui, ao pegar o job, e nao na falha. Um job preso em processing
    alem do limite volta a ser candidato.
    """
    with engine.begin() as conexao:
        linha = conexao.execute(
            text(
                "SELECT id, tenant_id, type, payload, attempts, max_attempts "
                "FROM jobs "
                "WHERE run_at <= now() AND attempts < max_attempts "
                "AND (status = 'pending' "
                "     OR (status = 'processing' AND locked_at < now() - make_interval(secs => :lim))) "
                "ORDER BY run_at, id "
                "FOR UPDATE SKIP LOCKED "
                "LIMIT 1"
            ),
            {"lim": limite_segundos},
        ).first()
        if linha is None:
            return None
        conexao.execute(
            text(
                "UPDATE jobs SET status = 'processing', attempts = attempts + 1, "
                "locked_at = now(), locked_by = :w WHERE id = :id"
            ),
            {"w": worker_id, "id": linha.id},
        )
        return JobCapturado(
            id=linha.id,
            tenant_id=str(linha.tenant_id),
            type=linha.type,
            payload=linha.payload,
            attempts=linha.attempts + 1,
            max_attempts=linha.max_attempts,
        )


def finalizar_job(
    job: JobCapturado,
    worker_id: str,
    status: str,
    last_error: Optional[str] = None,
    engine=engine_worker,
) -> int:
    """Grava o status final do job, so se ele ainda pertencer a este worker.

    O filtro por id, tenant_id e locked_by garante que um worker que perdeu o
    lock (job recapturado por outro) nao finaliza o job alheio. Retorna o numero
    de linhas afetadas.
    """
    with engine.begin() as conexao:
        resultado = conexao.execute(
            text(
                "UPDATE jobs SET status = :s, last_error = :e "
                "WHERE id = :id AND tenant_id = :t AND locked_by = :w"
            ),
            {"s": status, "e": last_error, "id": job.id, "t": job.tenant_id, "w": worker_id},
        )
        return resultado.rowcount


def processar_um(
    worker_id: str,
    processamento: Callable[[object, JobCapturado], None] = processamento_vazio,
    limite_segundos: int = LIMITE_LOCK_SEGUNDOS,
    engine=engine_worker,
) -> Optional[JobCapturado]:
    """Captura, processa e finaliza um job. Retorna o job, ou None se nao havia."""
    job = reivindicar_job(worker_id, limite_segundos, engine)
    if job is None:
        return None

    # Tipo que o worker nao sabe tratar vai direto para dead, sem retry
    if job.type not in TIPOS_SUPORTADOS:
        finalizar_job(job, worker_id, "dead", f"tipo nao suportado: {job.type}", engine)
        return job

    try:
        # app.tenant_id definido antes do processamento (contrato de contexto)
        with engine.begin() as conexao:
            conexao.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"),
                {"t": job.tenant_id},
            )
            processamento(conexao, job)
    except Exception as erro:  # noqa: BLE001 - qualquer falha de processamento
        # Falha: volta a pending ate o teto; atingido max_attempts, vai para dead
        status = "dead" if job.attempts >= job.max_attempts else "pending"
        finalizar_job(job, worker_id, status, str(erro)[:500], engine)
        return job

    finalizar_job(job, worker_id, "done", None, engine)
    return job


def varrer_orfaos_esgotados(
    limite_segundos: int = LIMITE_LOCK_SEGUNDOS,
    engine=engine_worker,
) -> int:
    """Marca como dead os jobs presos em processing que ja esgotaram as tentativas.

    Sao jobs cujo worker morreu (locked_at expirado) e que nao sao mais elegiveis
    para recaptura porque attempts >= max_attempts. Sem isso, ficariam presos em
    processing para sempre. Retorna o numero de jobs marcados.
    """
    with engine.begin() as conexao:
        resultado = conexao.execute(
            text(
                "UPDATE jobs SET status = 'dead', last_error = 'expirado apos max_attempts' "
                "WHERE status = 'processing' AND attempts >= max_attempts "
                "AND locked_at < now() - make_interval(secs => :lim)"
            ),
            {"lim": limite_segundos},
        )
        return resultado.rowcount


def rodar(
    worker_id: Optional[str] = None,
    processamento: Callable[[object, JobCapturado], None] = processar_mensagem,
    limite_segundos: int = LIMITE_LOCK_SEGUNDOS,
    intervalo_ocioso: float = 1.0,
    engine=engine_worker,
) -> None:
    """Laco do worker: varre orfaos esgotados e processa jobs ate ser interrompido."""
    worker_id = worker_id or uuid.uuid4().hex
    while True:
        varrer_orfaos_esgotados(limite_segundos, engine)
        job = processar_um(worker_id, processamento, limite_segundos, engine)
        if job is None:
            time.sleep(intervalo_ocioso)


def main() -> None:
    rodar()


if __name__ == "__main__":
    main()
