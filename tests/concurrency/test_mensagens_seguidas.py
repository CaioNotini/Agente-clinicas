"""Mensagens seguidas da mesma conversa (etapa 4.3) e processamento via app_clinicas (etapa 4.4).

Etapa 4.3: varios jobs PROCESS_INBOUND_MESSAGE da mesma conversa
(tenant_id, contato_telefone) processados por varios workers nao se sobrepoem
(o lock da conversa serializa) e nenhum e processado duas vezes.

Etapa 4.4: a escrita especifica de clinica feita durante o processamento
(buscar-ou-criar e travar a conversa) passa por sessao app_clinicas com RLS,
ligada ao worker pelo ponto de extensao `processamento=`, sem alterar o worker.
A conversa criada pertence so ao tenant do job (segunda barreira pelo tenant).

O worker (processar_um) conecta como worker_jobs so para a tabela jobs. Os dados
de teste sao criados e removidos com a conta de administracao (cnotini).

Desde a tarefa 7.2 o processamento le a mensagem do job e a classifica. Por isso
cada job tem a sua linha em mensagens, e o LLM e um cliente falso, sem rede.
"""
import functools
import json
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.config import MIGRATION_DATABASE_URL
from app.core.conversas import conversa_travada
from app.core.estados import IDLE
from app.core.processamento import processar_mensagem
from app.jobs.worker import processar_um, reivindicar_job
from tests.concurrency.prazos import ESPERA_LOCK, juntar, limite_pytest
from tests.llm_falso import ClienteFalso, saida_json

# Conexao de administracao, so para preparar e limpar os dados do teste
engine_admin = create_engine(MIGRATION_DATABASE_URL)

CONTATO = "(00) 00000-0001"

# Tempo que cada processamento segura o lock da conversa, para tornar observavel
# a sobreposicao (ou a ausencia dela) entre workers concorrentes.
HOLD = 0.3
N_MENSAGENS = 6

# Prazo (tests/concurrency/prazos.py). Os jobs da mesma conversa rodam em serie
# (ADR 0005), e cada um segura o lock por HOLD ou espera no maximo lock_timeout.
PRAZO_SERIE = N_MENSAGENS * (HOLD + ESPERA_LOCK)

# processar_mensagem com um LLM falso que devolve a lista vazia
processar = functools.partial(processar_mensagem, cliente_llm=ClienteFalso(saida_json()))


def _criar_clinica(tenant_id):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica Seguidas', true)"),
            {"t": tenant_id},
        )


def _limpar(tenant_id):
    with engine_admin.begin() as conexao:
        conexao.execute(text("DELETE FROM jobs WHERE tenant_id = :t"), {"t": tenant_id})
        conexao.execute(text("DELETE FROM mensagens WHERE tenant_id = :t"), {"t": tenant_id})
        conexao.execute(text("DELETE FROM conversas WHERE tenant_id = :t"), {"t": tenant_id})
        conexao.execute(text("DELETE FROM clinicas WHERE tenant_id = :t"), {"t": tenant_id})


def _enfileirar_mensagem(tenant_id, contato_telefone, tenant_no_payload=None):
    """Insere um job PROCESS_INBOUND_MESSAGE pendente para a conversa dada.

    tenant_no_payload, quando dado, grava um campo tenant_id no corpo do payload
    diferente do tenant_id da coluna do job. Serve para provar que o
    processamento usa o tenant da coluna, nao o do payload.
    """
    mensagem_id = uuid.uuid4().hex
    corpo = {"mensagem_id": mensagem_id, "contato_telefone": contato_telefone}
    if tenant_no_payload is not None:
        corpo["tenant_id"] = tenant_no_payload
    payload = json.dumps(corpo)
    with engine_admin.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO mensagens (id, tenant_id, contato_telefone, conteudo, direcao) "
                "VALUES (:id, :t, :tel, 'oi', 'entrada')"
            ),
            {"id": mensagem_id, "t": tenant_id, "tel": contato_telefone},
        )
        return conexao.execute(
            text(
                "INSERT INTO jobs (tenant_id, type, status, payload, contato_telefone, "
                "run_at, attempts, max_attempts) "
                "VALUES (:t, 'PROCESS_INBOUND_MESSAGE', 'pending', CAST(:payload AS JSON), :tel, now(), 0, 3) "
                "RETURNING id"
            ),
            {"t": tenant_id, "payload": payload, "tel": contato_telefone},
        ).scalar()


def _contar_conversas(tenant_id, contato_telefone):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text(
                "SELECT COUNT(*) FROM conversas "
                "WHERE tenant_id = :t AND contato_telefone = :tel"
            ),
            {"t": tenant_id, "tel": contato_telefone},
        ).scalar()


def _id_conversa(tenant_id, contato_telefone):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text(
                "SELECT id FROM conversas "
                "WHERE tenant_id = :t AND contato_telefone = :tel"
            ),
            {"t": tenant_id, "tel": contato_telefone},
        ).scalar()


def _estado_conversa(tenant_id, contato_telefone):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text(
                "SELECT estado_conversa FROM conversas "
                "WHERE tenant_id = :t AND contato_telefone = :tel"
            ),
            {"t": tenant_id, "tel": contato_telefone},
        ).scalar()


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


# ---------------------------------------------------------------------------
# Etapa 4.3: mensagens seguidas da mesma conversa
# ---------------------------------------------------------------------------

@pytest.mark.timeout(limite_pytest(PRAZO_SERIE))
def test_mensagens_seguidas_serializam_sem_duplicar(tenant):
    """Varios jobs da mesma conversa, com varios workers, nao se sobrepoem nem duplicam.

    Cada worker captura um job distinto (SKIP LOCKED na tabela jobs), mas todos
    disputam o mesmo lock da conversa: o processamento fica serializado. Ao final
    cada job foi processado exatamente uma vez e as janelas de lock nao se
    sobrepoem.
    """
    n_mensagens = N_MENSAGENS
    n_workers = 3
    ids_jobs = [_enfileirar_mensagem(tenant, CONTATO) for _ in range(n_mensagens)]

    intervalos = []  # (job_id, inicio, fim) de cada processamento, dentro do lock
    registro_lock = threading.Lock()

    def processamento_observado(conexao, job):
        contato = job.payload["contato_telefone"]
        with conversa_travada(job.tenant_id, contato):
            inicio = time.perf_counter()
            time.sleep(HOLD)
            fim = time.perf_counter()
        with registro_lock:
            intervalos.append((job.id, inicio, fim))

    def worker_loop():
        wid = uuid.uuid4().hex
        while True:
            job = processar_um(wid, processamento=processamento_observado)
            if job is None:
                return

    threads = [threading.Thread(target=worker_loop) for _ in range(n_workers)]
    for t in threads:
        t.start()
    vivas = juntar(threads, PRAZO_SERIE)

    assert not vivas, ("worker travou (possivel deadlock)", vivas, intervalos)

    # Exatamente uma vez: cada job processado, nenhum repetido
    processados = [job_id for (job_id, _, _) in intervalos]
    assert sorted(processados) == sorted(ids_jobs)
    assert len(processados) == len(set(processados)), "job processado mais de uma vez"

    # Serializacao: nenhuma janela de lock se sobrepoe a outra
    janelas = [(inicio, fim) for (_, inicio, fim) in intervalos]
    janelas.sort()
    for (_, fim_anterior), (inicio_seguinte, _) in zip(janelas, janelas[1:]):
        assert inicio_seguinte >= fim_anterior, "processamentos da mesma conversa se sobrepuseram"

    # Uma unica conversa, no estado inicial
    assert _contar_conversas(tenant, CONTATO) == 1


# ---------------------------------------------------------------------------
# Etapa 4.4: processamento escreve a conversa por sessao app_clinicas, so do tenant
# ---------------------------------------------------------------------------

def test_processar_mensagem_garante_conversa_no_tenant(tenant):
    """O processamento cria-ou-encontra a conversa do job, no estado inicial."""
    job_id = _enfileirar_mensagem(tenant, CONTATO)

    job = processar_um(uuid.uuid4().hex, processamento=processar)

    assert job is not None and job.id == job_id
    assert _contar_conversas(tenant, CONTATO) == 1
    assert _estado_conversa(tenant, CONTATO) == IDLE


def test_processar_mensagem_escreve_so_no_tenant_do_job(dois_tenants):
    """A conversa criada pelo processamento pertence so ao tenant do job (2a barreira)."""
    tenant_a, tenant_b = dois_tenants
    _enfileirar_mensagem(tenant_a, CONTATO)

    job = processar_um(uuid.uuid4().hex, processamento=processar)
    assert job is not None and job.tenant_id == tenant_a

    # So o tenant do job ganhou a conversa; o outro tenant nao foi tocado
    assert _contar_conversas(tenant_a, CONTATO) == 1
    assert _contar_conversas(tenant_b, CONTATO) == 0


def test_processar_mensagem_usa_tenant_da_coluna_nao_do_payload(dois_tenants):
    """O tenant vem da coluna do job; um tenant diferente no payload e ignorado.

    O job tem tenant_id de coluna = tenant_a, mas o payload traz tenant_id =
    tenant_b. A conversa deve nascer em tenant_a (coluna), nunca em tenant_b.
    Controle: fazendo processar_mensagem ler o tenant do payload, a conversa iria
    para tenant_b e este teste acusaria (tenant_a com 0, tenant_b com 1).
    """
    tenant_a, tenant_b = dois_tenants
    _enfileirar_mensagem(tenant_a, CONTATO, tenant_no_payload=tenant_b)

    job = processar_um(uuid.uuid4().hex, processamento=processar)
    assert job is not None and job.tenant_id == tenant_a

    assert _contar_conversas(tenant_a, CONTATO) == 1
    assert _contar_conversas(tenant_b, CONTATO) == 0


def test_reprocessar_mesmo_job_nao_duplica_conversa(tenant):
    """Reprocessar o mesmo job (mesma conversa) nao cria uma segunda linha.

    Controle: removendo o ON CONFLICT do INSERT em app/core/conversas.py, o segundo
    processamento falha por violacao de chave unica e este teste acusa.

    O job e real e capturado, porque o processamento conclui o job na propria
    transacao (ADR 0008). A recaptura e simulada devolvendo o job a processing.
    """
    _enfileirar_mensagem(tenant, CONTATO)
    job = reivindicar_job(uuid.uuid4().hex)

    processar(None, job)
    with engine_admin.begin() as conexao:
        conexao.execute(text("UPDATE jobs SET status = 'processing' WHERE id = :id"), {"id": job.id})
    processar(None, job)  # mesmo job de novo

    assert _contar_conversas(tenant, CONTATO) == 1


def test_mesmo_contato_em_duas_clinicas_gera_duas_conversas(dois_tenants):
    """O mesmo contato em duas clinicas gera duas conversas separadas, uma por tenant.

    Controle: enfileirando os dois jobs para o mesmo tenant, uma das clinicas
    ficaria sem conversa e este teste acusaria.
    """
    tenant_a, tenant_b = dois_tenants
    _enfileirar_mensagem(tenant_a, CONTATO)
    _enfileirar_mensagem(tenant_b, CONTATO)

    wid = uuid.uuid4().hex
    vistos = []
    for _ in range(2):
        job = processar_um(wid, processamento=processar)
        assert job is not None
        vistos.append(job.tenant_id)

    # Cada clinica tem a sua conversa
    assert _contar_conversas(tenant_a, CONTATO) == 1
    assert _contar_conversas(tenant_b, CONTATO) == 1
    # Os dois jobs processados foram de tenants distintos
    assert set(vistos) == {tenant_a, tenant_b}
    # E sao linhas diferentes
    assert _id_conversa(tenant_a, CONTATO) != _id_conversa(tenant_b, CONTATO)
