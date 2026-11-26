"""Processamento com classificacao (tarefa 7.2): leitura da mensagem, LLM e job.

Roda o caminho real do worker (processar_um) com processar_mensagem e um LLM
falso, sem rede. A leitura da mensagem e a escrita da conversa passam pela conta
app_clinicas, com RLS, e a verificacao do isolamento tambem (regra 19). Os dados
sao criados e removidos com a conta de administracao.

Isolamento: um job so le a mensagem do proprio tenant e do proprio contato. Um
mensagem_id de outra clinica, de outro contato ou de saida leva o job a dead sem
chamar o LLM, entao o conteudo de outra clinica nunca chega ao modelo.
"""
import functools
import json
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from structlog.testing import capture_logs

from app.classification.resultado import ADMINISTRATIVO, ORIGEM_LLM, ORIGEM_REGRA
from app.config import MIGRATION_DATABASE_URL
from app.core.estados import IDLE
from app.core.processamento import MensagemNaoEncontrada, processar_mensagem
from app.jobs import worker
from app.jobs.worker import JobCapturado, processar_um
from app.llm.erros import ErroLLMPermanente, ErroLLMTransitorio
from tests.llm_falso import ClienteFalso, saida_json

engine_admin = create_engine(MIGRATION_DATABASE_URL)

CONTATO = "(00) 00000-0002"
OUTRO_CONTATO = "(00) 00000-0003"
CONTEUDO = "Quanto custa a consulta particular?"
URGENTE = "estou com dor no peito agora"


def _criar_clinica(tenant_id):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica 7.2', true)"),
            {"t": tenant_id},
        )


def _limpar(tenant_id):
    with engine_admin.begin() as conexao:
        for tabela in ("jobs", "mensagens", "conversas", "clinicas"):
            conexao.execute(text(f"DELETE FROM {tabela} WHERE tenant_id = :t"), {"t": tenant_id})


def _gravar_mensagem(tenant_id, contato, conteudo, direcao="entrada"):
    mensagem_id = uuid.uuid4().hex
    with engine_admin.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO mensagens (id, tenant_id, contato_telefone, conteudo, direcao) "
                "VALUES (:id, :t, :tel, :c, :d)"
            ),
            {"id": mensagem_id, "t": tenant_id, "tel": contato, "c": conteudo, "d": direcao},
        )
    return mensagem_id


def _enfileirar(tenant_id, contato, mensagem_id):
    payload = json.dumps({"mensagem_id": mensagem_id, "contato_telefone": contato})
    with engine_admin.begin() as conexao:
        return conexao.execute(
            text(
                "INSERT INTO jobs (tenant_id, type, status, payload, contato_telefone, "
                "run_at, attempts, max_attempts) "
                "VALUES (:t, 'PROCESS_INBOUND_MESSAGE', 'pending', CAST(:p AS JSON), :tel, "
                "now(), 0, 3) RETURNING id"
            ),
            {"t": tenant_id, "p": payload, "tel": contato},
        ).scalar()


def _job(job_id):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text(
                "SELECT status, attempts, last_error, run_at > now() AS adiado "
                "FROM jobs WHERE id = :id"
            ),
            {"id": job_id},
        ).first()


def _estado_conversa(tenant_id, contato):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text(
                "SELECT estado_conversa FROM conversas "
                "WHERE tenant_id = :t AND contato_telefone = :tel"
            ),
            {"t": tenant_id, "tel": contato},
        ).scalar()


def _processar(cliente):
    processamento = functools.partial(processar_mensagem, cliente_llm=cliente)
    return processar_um(uuid.uuid4().hex, processamento=processamento)


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


def _item(categoria, confianca, subtipo=None):
    return {"categoria": categoria, "subtipo": subtipo, "confianca": confianca}


# --- caminho feliz ---------------------------------------------------------


def test_classifica_a_mensagem_do_job_e_conclui_sem_mudar_o_estado(tenant):
    job_id = _enfileirar(tenant, CONTATO, _gravar_mensagem(tenant, CONTATO, CONTEUDO))
    cliente = ClienteFalso(saida_json(_item(ADMINISTRATIVO, 0.9)))

    with capture_logs() as logs:
        job = _processar(cliente)

    assert job.id == job_id
    assert _job(job_id).status == "done"
    assert _estado_conversa(tenant, CONTATO) == IDLE

    # O LLM recebeu o conteudo da mensagem do job, e so ele
    assert len(cliente.chamadas) == 1
    assert cliente.chamadas[0]["mensagens"] == [{"role": "user", "content": CONTEUDO}]
    assert cliente.chamadas[0]["tenant_id"] == tenant

    eventos = [log for log in logs if log["event"] == "classificacao"]
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento["log_level"] == "info"
    assert evento["tenant_id"] == tenant
    assert evento["job_id"] == job_id
    assert evento["origem"] == ORIGEM_LLM
    assert evento["intencoes"] == [
        {"categoria": ADMINISTRATIVO, "subtipo": None, "confianca": 0.9}
    ]
    assert isinstance(evento["latencia_ms"], int)
    # Sem conteudo nem telefone no log
    assert CONTEUDO not in repr(logs)
    assert CONTATO not in repr(logs)


def test_urgencia_da_regra_conclui_sem_chamar_o_llm(tenant):
    job_id = _enfileirar(tenant, CONTATO, _gravar_mensagem(tenant, CONTATO, URGENTE))
    cliente = ClienteFalso(erro=ErroLLMTransitorio("nao deveria ser chamado"))

    with capture_logs() as logs:
        _processar(cliente)

    assert cliente.chamadas == []
    assert _job(job_id).status == "done"
    evento = next(log for log in logs if log["event"] == "classificacao")
    assert evento["origem"] == ORIGEM_REGRA
    assert {"categoria": "urgencia", "subtipo": None, "confianca": None} in evento["intencoes"]
    assert URGENTE not in repr(logs)


# --- erros do LLM ----------------------------------------------------------


def test_erro_transitorio_devolve_o_job_a_pending_com_backoff(tenant):
    job_id = _enfileirar(tenant, CONTATO, _gravar_mensagem(tenant, CONTATO, CONTEUDO))

    _processar(ClienteFalso(erro=ErroLLMTransitorio("503")))

    linha = _job(job_id)
    assert linha.status == "pending"
    assert linha.attempts == 1
    assert linha.adiado


def test_erro_permanente_usa_a_regra_e_o_job_conclui(tenant):
    """Parte do C13: a chave revogada nao leva mais cada mensagem a dead."""
    job_id = _enfileirar(tenant, CONTATO, _gravar_mensagem(tenant, CONTATO, CONTEUDO))

    with capture_logs() as logs:
        _processar(ClienteFalso(erro=ErroLLMPermanente("401")))

    assert _job(job_id).status == "done"
    assert [log for log in logs if log["event"] == "classificacao_llm_erro_permanente"]
    evento = next(log for log in logs if log["event"] == "classificacao")
    assert evento["origem"] == ORIGEM_REGRA
    assert evento["intencoes"] == [
        {"categoria": ADMINISTRATIVO, "subtipo": None, "confianca": None}
    ]


# --- isolamento e mensagem do proprio contato ------------------------------


def test_mensagem_de_outra_clinica_nao_e_lida(dois_tenants):
    """Job da clinica A com o mensagem_id de uma mensagem da clinica B."""
    tenant_a, tenant_b = dois_tenants
    id_de_b = _gravar_mensagem(tenant_b, CONTATO, "conteudo da clinica B")
    job_id = _enfileirar(tenant_a, CONTATO, id_de_b)
    cliente = ClienteFalso(saida_json())

    _processar(cliente)

    linha = _job(job_id)
    assert linha.status == "dead"
    assert "MensagemNaoEncontrada" in linha.last_error
    assert id_de_b not in linha.last_error
    assert cliente.chamadas == []
    # A transacao foi desfeita: nem a conversa ficou criada em A
    assert _estado_conversa(tenant_a, CONTATO) is None


def test_sem_rls_o_filtro_de_tenant_impede_a_leitura(dois_tenants):
    """Segunda barreira (ADR 0002): o filtro explicito de tenant_id na leitura.

    Com o RLS ativo, a policy ja esconde a mensagem de B e o filtro nao muda o
    resultado. So uma sessao sem RLS mostra se o filtro existe, por isso a sessao da
    conversa aqui e da conta de administracao, que ignora o RLS. Este teste verifica
    o filtro, nao o RLS. O isolamento pelo RLS e verificado com app_clinicas em
    test_mensagem_de_outra_clinica_nao_e_lida (regra 19).
    """
    tenant_a, tenant_b = dois_tenants
    id_de_b = _gravar_mensagem(tenant_b, CONTATO, "conteudo da clinica B")
    job = JobCapturado(
        id=0,
        tenant_id=tenant_a,
        type="PROCESS_INBOUND_MESSAGE",
        payload={"mensagem_id": id_de_b, "contato_telefone": CONTATO},
        attempts=1,
        max_attempts=3,
    )
    cliente = ClienteFalso(saida_json())

    with pytest.raises(MensagemNaoEncontrada):
        processar_mensagem(
            None,
            job,
            cliente_llm=cliente,
            session_factory=sessionmaker(bind=engine_admin),
        )
    assert cliente.chamadas == []


def test_mensagem_de_outro_contato_da_mesma_clinica_nao_e_lida(tenant):
    id_outro = _gravar_mensagem(tenant, OUTRO_CONTATO, "conteudo de outro contato")
    job_id = _enfileirar(tenant, CONTATO, id_outro)
    cliente = ClienteFalso(saida_json())

    _processar(cliente)

    assert _job(job_id).status == "dead"
    assert cliente.chamadas == []


def test_mensagem_de_saida_nao_e_classificada(tenant):
    id_saida = _gravar_mensagem(tenant, CONTATO, "resposta do agente", direcao="saida")
    job_id = _enfileirar(tenant, CONTATO, id_saida)
    cliente = ClienteFalso(saida_json())

    _processar(cliente)

    assert _job(job_id).status == "dead"
    assert cliente.chamadas == []


def test_mensagem_inexistente_vai_para_dead_na_primeira_falha(tenant):
    job_id = _enfileirar(tenant, CONTATO, uuid.uuid4().hex)

    _processar(ClienteFalso(saida_json()))

    linha = _job(job_id)
    assert linha.status == "dead"
    assert linha.attempts == 1


# --- ligacao no main() do worker -------------------------------------------


def test_main_cria_o_cliente_pela_fabrica_e_o_injeta_no_processamento(monkeypatch):
    cliente = ClienteFalso(saida_json())
    recebido = {}
    monkeypatch.setattr(worker, "criar_cliente_llm", lambda: cliente)
    monkeypatch.setattr(worker, "rodar", lambda processamento: recebido.update(p=processamento))

    worker.main()

    processamento = recebido["p"]
    assert processamento.func is processar_mensagem
    assert processamento.keywords == {"cliente_llm": cliente}


def test_main_sem_configuracao_do_llm_nao_roda_o_laco(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rodou = []
    monkeypatch.setattr(worker, "rodar", lambda processamento: rodou.append(True))

    with pytest.raises(RuntimeError):
        worker.main()
    assert rodou == []
