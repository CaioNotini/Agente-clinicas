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

Ordem por conversa (docs/decisions/0005-ordem-por-conversa.md): um job so e
capturado se nao houver outro job pending ou processing, mais antigo, da mesma
conversa (tenant_id, contato_telefone). Jobs sem conversa ficam fora da regra.

Backoff no retry (tarefa 6.4): uma falha transitoria devolve o job a pending com
run_at adiado por atraso_backoff, exponencial com teto (formula e valores no
ADR 0010). Sem isso, o retry seria imediato e, com a chamada de IA no
processamento (etapa 7), geraria rajada de custo. O erro permanente (dead) e o sucesso (done) nao mexem em run_at. A
conversa inteira espera durante o backoff, pela ordem por conversa
(docs/decisions/0005-ordem-por-conversa.md).

Erro permanente (app/core/erros.py, tarefa 5.4): o job vai para dead na primeira
falha, sem gastar as outras tentativas, e gera log de erro com tenant_id, job_id e
o tipo do erro. Outra tentativa falharia igual e so atrasaria a conversa.
"""
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import WORKER_DATABASE_URL
from app.core.erros import ErroPermanente
from app.core.processamento import processar_mensagem
from app.db.database import CONNECT_TIMEOUT_SEGUNDOS
from app.jobs.queue import JobPerdido

# Engine do worker, conectado com a conta worker_jobs (BYPASSRLS). Mesmo limite de
# conexao da aplicacao: um banco inacessivel nao prende o laco do worker.
engine_worker = create_engine(
    WORKER_DATABASE_URL,
    connect_args={"connect_timeout": CONNECT_TIMEOUT_SEGUNDOS},
)

# Tempo acima do qual um job preso em processing e considerado orfao
LIMITE_LOCK_SEGUNDOS = 300

# Tipos de job que este worker sabe processar nesta etapa
TIPOS_SUPORTADOS = ("PROCESS_INBOUND_MESSAGE",)

# Espera depois de um erro de banco no laco, antes de tentar de novo
INTERVALO_ERRO_SEGUNDOS = 5.0

# Backoff do retry transitorio (tarefa 6.4). O atraso dobra a cada tentativa, ate
# o teto. Retry imediato, com a chamada de IA no processamento, geraria rajada de
# custo. Com max_attempts=3, so ha atraso na 1a falha (base) e na 2a (2 * base).
BACKOFF_BASE_SEGUNDOS = 60
BACKOFF_TETO_SEGUNDOS = 1800

logger = logging.getLogger(__name__)
# Log estruturado do erro permanente: e problema nosso, e alguem precisa ser avisado
log_estruturado = structlog.get_logger(__name__)


@dataclass(frozen=True)
class JobCapturado:
    id: int
    tenant_id: str
    type: str
    payload: Optional[dict]
    attempts: int
    max_attempts: int
    # Worker que capturou o job. A conclusao so vale para ele (ADR 0008).
    worker_id: str = ""


def processamento_vazio(conexao, job: JobCapturado) -> None:
    """Processamento que nao faz nada. Padrao de processar_um."""
    return None


def atraso_backoff(tentativas: int) -> timedelta:
    """Atraso ate a proxima tentativa: exponencial com teto.

    min(base * 2**(tentativas-1), teto). tentativas e o numero de tentativas ja
    gastas (job.attempts), entao a 1a falha usa 2**0 = base.
    """
    segundos = min(BACKOFF_BASE_SEGUNDOS * 2 ** (tentativas - 1), BACKOFF_TETO_SEGUNDOS)
    return timedelta(seconds=segundos)


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

    A transacao e confirmada ao sair do bloco with, antes de o job ser devolvido.
    Isso e obrigatorio (ADR 0008): aberta, ela seguraria o FOR UPDATE na linha do
    job, e a conclusao pela sessao app_clinicas esperaria por ela, travando o
    proprio worker. Nao processar dentro deste bloco.

    Ordem por conversa: o NOT EXISTS so le, sem travar. Uma linha travada por
    outro worker e pulada pelo SKIP LOCKED, mas o NOT EXISTS ainda a enxerga
    como pending, entao o job seguinte da conversa continua bloqueado. Com
    contato_telefone NULL a comparacao nunca e verdadeira, entao jobs sem
    conversa nao bloqueiam nem sao bloqueados.
    """
    with engine.begin() as conexao:
        linha = conexao.execute(
            text(
                "SELECT j.id, j.tenant_id, j.type, j.payload, j.attempts, j.max_attempts "
                "FROM jobs j "
                "WHERE j.run_at <= now() AND j.attempts < j.max_attempts "
                "AND (j.status = 'pending' "
                "     OR (j.status = 'processing' AND j.locked_at < now() - make_interval(secs => :lim))) "
                "AND NOT EXISTS ("
                "    SELECT 1 FROM jobs anterior "
                "    WHERE anterior.tenant_id = j.tenant_id "
                "    AND anterior.contato_telefone = j.contato_telefone "
                "    AND anterior.id < j.id "
                "    AND anterior.status IN ('pending', 'processing')) "
                "ORDER BY j.run_at, j.id "
                "FOR UPDATE OF j SKIP LOCKED "
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
            worker_id=worker_id,
        )


def finalizar_job(
    job: JobCapturado,
    worker_id: str,
    status: str,
    last_error: Optional[str] = None,
    engine=engine_worker,
    atraso: Optional[timedelta] = None,
) -> int:
    """Grava o status final do job, so se ele ainda pertencer a este worker.

    O filtro por id, tenant_id e locked_by garante que um worker que perdeu o
    lock (job recapturado por outro) nao finaliza o job alheio. Retorna o numero
    de linhas afetadas.

    Com atraso (retry transitorio, tarefa 6.4), a UPDATE adia run_at para
    now() + atraso, espacando a proxima captura. Sem atraso, run_at fica
    inalterado, entao dead e done nao mexem no instante de execucao.
    """
    set_run_at = ", run_at = now() + make_interval(secs => :secs)" if atraso else ""
    parametros = {
        "s": status,
        "e": last_error,
        "id": job.id,
        "t": job.tenant_id,
        "w": worker_id,
    }
    if atraso:
        parametros["secs"] = atraso.total_seconds()
    with engine.begin() as conexao:
        resultado = conexao.execute(
            text(
                f"UPDATE jobs SET status = :s, last_error = :e{set_run_at} "
                "WHERE id = :id AND tenant_id = :t AND locked_by = :w "
                "AND status = 'processing'"
            ),
            parametros,
        )
        return resultado.rowcount


def _resumo_erro(erro: Exception) -> str:
    """Texto curto para last_error, sem dados da mensagem.

    O str() de um erro do SQLAlchemy traz o SQL e os parametros, que podem conter
    telefone e conteudo. Para esses erros fica so o tipo e o SQLSTATE.
    """
    if isinstance(erro, SQLAlchemyError):
        codigo = getattr(getattr(erro, "orig", None), "pgcode", None)
        return (
            f"{type(erro).__name__} (SQLSTATE {codigo})"
            if codigo
            else type(erro).__name__
        )
    return f"{type(erro).__name__}: {str(erro)[:200]}"


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
    except JobPerdido:
        # Outro worker e o dono do job agora. A transacao do processamento ja foi
        # desfeita, e o job nao e tocado aqui (ADR 0008).
        return job
    except ErroPermanente as erro:
        # Sem nova tentativa. So o tipo vai ao log: o texto pode repetir ids.
        log_estruturado.error(
            "job_erro_permanente",
            tenant_id=job.tenant_id,
            job_id=job.id,
            erro=type(erro).__name__,
        )
        finalizar_job(job, worker_id, "dead", _resumo_erro(erro), engine)
        return job
    except Exception as erro:  # noqa: BLE001 - qualquer falha de processamento
        # Falha: volta a pending ate o teto; atingido max_attempts, vai para dead.
        # So o retry (pending) adia run_at com backoff; dead nao mexe no instante.
        status = "dead" if job.attempts >= job.max_attempts else "pending"
        atraso = atraso_backoff(job.attempts) if status == "pending" else None
        finalizar_job(job, worker_id, status, _resumo_erro(erro), engine, atraso=atraso)
        return job

    # So altera o job se ele ainda estiver em processing com este worker. Um
    # processamento que concluiu o job na propria transacao ja o deixou done.
    # Este passo serve aos processamentos sem efeito de clinica (ADR 0008).
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
    intervalo_erro: float = INTERVALO_ERRO_SEGUNDOS,
    max_iteracoes: Optional[int] = None,
) -> None:
    """Laco do worker: varre orfaos esgotados e processa jobs ate ser interrompido.

    Um erro de banco no laco (conexao caida, por exemplo) nao encerra o worker:
    o erro e registrado e o laco tenta de novo depois de intervalo_erro. Um job
    que ficar em processing por causa do erro e recapturado apos o limite de
    orfao. max_iteracoes limita o laco, para testes. None roda sem fim.
    """
    worker_id = worker_id or uuid.uuid4().hex
    iteracao = 0
    while max_iteracoes is None or iteracao < max_iteracoes:
        iteracao += 1
        try:
            varrer_orfaos_esgotados(limite_segundos, engine)
            job = processar_um(worker_id, processamento, limite_segundos, engine)
        except SQLAlchemyError as erro:
            # So o tipo do erro: a mensagem do SQLAlchemy inclui os parametros do SQL
            logger.warning("erro de banco no laco do worker: %s", type(erro).__name__)
            time.sleep(intervalo_erro)
            continue
        if job is None:
            time.sleep(intervalo_ocioso)


def main() -> None:
    rodar()


if __name__ == "__main__":
    main()
