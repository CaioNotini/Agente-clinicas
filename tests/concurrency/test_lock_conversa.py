"""Lock por conversa com SELECT ... FOR UPDATE (etapa 4.2).

Evidencia que duas transacoes na mesma conversa (tenant_id, contato_telefone)
sao serializadas: a segunda espera a primeira liberar o lock. Conversas de
contatos ou tenants diferentes nao bloqueiam entre si (controle), e o
buscar-ou-criar nao duplica a linha.

O lock roda em sessao app_clinicas (via conversa_travada -> SessionLocal),
sujeita ao RLS. Os dados de teste sao criados e removidos com a conta de
administracao (cnotini), conforme o padrao do projeto.
"""
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import MIGRATION_DATABASE_URL
from app.core.conversas import conversa_travada
from app.core.estados import IDLE

# Conexao de administracao, so para preparar e limpar os dados do teste
engine_admin = create_engine(MIGRATION_DATABASE_URL)

# Tempo que a primeira transacao segura o lock antes de liberar
HOLD = 0.5

CONTATO = "(00) 00000-0001"
OUTRO_CONTATO = "(00) 00000-0002"

# SQLSTATE do Postgres para lock_not_available (erro de lock_timeout)
LOCK_NOT_AVAILABLE = "55P03"


def _criar_clinica(tenant_id):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica Lock', true)"),
            {"t": tenant_id},
        )


def _limpar(tenant_id):
    with engine_admin.begin() as conexao:
        conexao.execute(text("DELETE FROM conversas WHERE tenant_id = :t"), {"t": tenant_id})
        conexao.execute(text("DELETE FROM clinicas WHERE tenant_id = :t"), {"t": tenant_id})


def _criar_conversa(tenant_id, contato_telefone):
    """Cria a conversa ja commitada, para que o teste isole o efeito do FOR UPDATE.

    Sem isto, duas transacoes concorrentes bloqueariam no INSERT ... ON CONFLICT
    pela chave unica (tenant_id, contato_telefone), serializando mesmo sem o lock
    e mascarando o que o teste quer provar.
    """
    with engine_admin.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO conversas (tenant_id, contato_telefone, estado_conversa) "
                "VALUES (:t, :tel, 'idle')"
            ),
            {"t": tenant_id, "tel": contato_telefone},
        )


def _contar_conversas(tenant_id, contato_telefone):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text(
                "SELECT COUNT(*) FROM conversas "
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


def _executar(func, erros):
    """Roda func numa thread, guardando qualquer excecao em erros."""
    try:
        func()
    except Exception as e:  # noqa: BLE001 - re-levantada na main depois do join
        erros.append(e)


def test_segunda_transacao_espera_a_primeira(tenant):
    """A segunda transacao na mesma conversa so prossegue depois que a primeira libera."""
    # Conversa ja existe e commitada: o lock do FOR UPDATE e a unica serializacao
    # possivel aqui (o INSERT ON CONFLICT nao pega lock sobre linha ja existente).
    _criar_conversa(tenant, CONTATO)
    eventos = {}
    erros = []
    a_dentro = threading.Event()

    def primeira():
        with conversa_travada(tenant, CONTATO):
            eventos["a_lock"] = time.perf_counter()
            a_dentro.set()
            time.sleep(HOLD)
            eventos["a_unlock"] = time.perf_counter()
        # commit (liberacao do lock) acontece ao sair do bloco

    def segunda():
        # So tenta travar depois que a primeira ja esta dentro, segurando o lock
        assert a_dentro.wait(timeout=5)
        with conversa_travada(tenant, CONTATO):
            eventos["b_lock"] = time.perf_counter()

    ta = threading.Thread(target=_executar, args=(primeira, erros))
    tb = threading.Thread(target=_executar, args=(segunda, erros))
    ta.start()
    tb.start()
    ta.join(timeout=10)
    tb.join(timeout=10)

    assert not erros, f"erro nas threads: {erros}"
    assert not ta.is_alive() and not tb.is_alive(), "thread travou (possivel deadlock)"

    # B so obteve o lock depois de A liberar, e esperou perto do tempo de posse de A
    assert eventos["b_lock"] >= eventos["a_unlock"]
    assert (eventos["b_lock"] - eventos["a_lock"]) >= HOLD * 0.8


def test_contatos_diferentes_nao_bloqueiam(tenant):
    """Conversas de contatos diferentes nao serializam entre si."""
    eventos = {}
    erros = []
    a_dentro = threading.Event()

    def primeira():
        with conversa_travada(tenant, CONTATO):
            eventos["a_lock"] = time.perf_counter()
            a_dentro.set()
            time.sleep(HOLD)
            eventos["a_unlock"] = time.perf_counter()

    def segunda():
        assert a_dentro.wait(timeout=5)
        with conversa_travada(tenant, OUTRO_CONTATO):
            eventos["b_lock"] = time.perf_counter()

    ta = threading.Thread(target=_executar, args=(primeira, erros))
    tb = threading.Thread(target=_executar, args=(segunda, erros))
    ta.start()
    tb.start()
    ta.join(timeout=10)
    tb.join(timeout=10)

    assert not erros, f"erro nas threads: {erros}"
    # B travou o outro contato enquanto A ainda segurava o seu: nao esperou
    assert eventos["b_lock"] < eventos["a_unlock"]


def test_tenants_diferentes_nao_bloqueiam(dois_tenants):
    """Conversas de tenants diferentes nao serializam entre si (mesmo contato)."""
    tenant_a, tenant_b = dois_tenants
    eventos = {}
    erros = []
    a_dentro = threading.Event()

    def primeira():
        with conversa_travada(tenant_a, CONTATO):
            eventos["a_lock"] = time.perf_counter()
            a_dentro.set()
            time.sleep(HOLD)
            eventos["a_unlock"] = time.perf_counter()

    def segunda():
        assert a_dentro.wait(timeout=5)
        with conversa_travada(tenant_b, CONTATO):
            eventos["b_lock"] = time.perf_counter()

    ta = threading.Thread(target=_executar, args=(primeira, erros))
    tb = threading.Thread(target=_executar, args=(segunda, erros))
    ta.start()
    tb.start()
    ta.join(timeout=10)
    tb.join(timeout=10)

    assert not erros, f"erro nas threads: {erros}"
    assert eventos["b_lock"] < eventos["a_unlock"]


def test_criacao_concorrente_nao_duplica(tenant):
    """Duas transacoes criando a mesma conversa ao mesmo tempo geram uma linha so.

    Aqui a conversa NAO e pre-criada: as duas threads disputam o buscar-ou-criar.
    O ON CONFLICT (tenant_id, contato_telefone) DO NOTHING garante que a segunda
    nao insere duplicata nem levanta erro de chave unica. Controle: removendo o
    ON CONFLICT do INSERT em app/core/conversas.py, a segunda transacao falha por
    violacao de chave unica e este teste acusa (erro na thread).
    """
    erros = []
    # Barreira para as duas criacoes partirem juntas e de fato se sobreporem
    barreira = threading.Barrier(2)

    def criar():
        barreira.wait(timeout=5)
        with conversa_travada(tenant, CONTATO) as c:
            _ = c.id
            # segura um instante dentro do bloco para a segunda transacao chegar
            # ao INSERT enquanto a primeira ainda nao commitou
            time.sleep(0.05)

    t1 = threading.Thread(target=_executar, args=(criar, erros))
    t2 = threading.Thread(target=_executar, args=(criar, erros))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not t1.is_alive() and not t2.is_alive(), "thread travou (possivel deadlock)"
    assert not erros, f"erro nas threads: {erros}"
    assert _contar_conversas(tenant, CONTATO) == 1


def test_lock_timeout_devolve_erro_sem_prender(tenant):
    """Com o lock ocupado alem do lock_timeout, a segunda transacao erra e nao prende.

    A primeira segura o lock por um tempo longo. A segunda entra com lock_timeout
    curto: deve receber erro de lock_timeout e sair bem antes de a primeira liberar,
    em vez de ficar presa esperando. Conversa pre-criada para isolar o FOR UPDATE.
    """
    _criar_conversa(tenant, CONTATO)
    a_dentro = threading.Event()
    resultado = {}
    HOLD_LONGO = 2.0
    TIMEOUT_CURTO_MS = 300

    def primeira():
        with conversa_travada(tenant, CONTATO):
            a_dentro.set()
            time.sleep(HOLD_LONGO)

    def segunda():
        assert a_dentro.wait(timeout=5)
        inicio = time.perf_counter()
        try:
            with conversa_travada(tenant, CONTATO, lock_timeout_ms=TIMEOUT_CURTO_MS):
                resultado["travou"] = True
        except OperationalError as erro:
            resultado["erro"] = erro
            resultado["espera"] = time.perf_counter() - inicio

    ta = threading.Thread(target=primeira)
    tb = threading.Thread(target=segunda)
    ta.start()
    tb.start()
    ta.join(timeout=10)
    tb.join(timeout=10)

    assert not ta.is_alive() and not tb.is_alive(), "thread travou (possivel deadlock)"
    assert "travou" not in resultado, "a segunda nao deveria ter obtido o lock"
    assert "erro" in resultado, "esperado erro de lock_timeout na segunda transacao"
    # Distingue lock timeout de outro OperationalError (ex.: statement_timeout,
    # queda de conexao): exige o SQLSTATE 55P03 (lock_not_available) ou, como
    # alternativa, a mensagem de lock timeout do Postgres.
    erro = resultado["erro"]
    pgcode = getattr(getattr(erro, "orig", None), "pgcode", None)
    assert pgcode == LOCK_NOT_AVAILABLE or "lock timeout" in str(erro).lower(), (
        f"esperado lock timeout (SQLSTATE {LOCK_NOT_AVAILABLE}), "
        f"veio pgcode={pgcode!r}: {erro}"
    )
    # A segunda errou perto do lock_timeout, nao ficou presa ate a primeira liberar
    assert resultado["espera"] < HOLD_LONGO * 0.8


def test_busca_ou_cria_idempotente(tenant):
    """A conversa e criada uma vez, no estado inicial, e reencontrada depois."""
    with conversa_travada(tenant, CONTATO) as c1:
        id1 = c1.id
        assert c1.estado_conversa == IDLE
        assert c1.tenant_id == tenant
        assert c1.contato_telefone == CONTATO

    with conversa_travada(tenant, CONTATO) as c2:
        id2 = c2.id

    assert id1 == id2
    assert _contar_conversas(tenant, CONTATO) == 1
