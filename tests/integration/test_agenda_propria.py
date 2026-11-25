"""Testes de integracao de AgendaPropria (etapa 5.1).

Exercitam a persistencia primitiva de criar e cancelar contra o banco real, pela
sessao app_clinicas sujeita ao RLS, com app.tenant_id definido na transacao, como
o servico da etapa 5.3 fara. Dados de apoio (clinica, profissional, servico) sao
criados e removidos com a conta de migrations (cnotini), seguindo o padrao dos
testes de isolamento.
"""
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL, MIGRATION_DATABASE_URL
from app.db.database import SessionLocal
from app.agenda.agenda_propria import AgendaPropria
from app.agenda.base import (
    Agendamento,
    AgendamentoNaoEncontrado,
    STATUS_AGENDADO,
    STATUS_CANCELADO,
)

# Conexao de migrations, so para preparar e limpar os dados de apoio
engine_admin = create_engine(MIGRATION_DATABASE_URL)

TELEFONE = "(00) 00000-0000"


def _inserir_profissional(tenant, nome="Prof 5.1"):
    with engine_admin.begin() as conexao:
        return conexao.execute(
            text("INSERT INTO profissionais (tenant_id, nome, ativo) VALUES (:t, :n, true) RETURNING id"),
            {"t": str(tenant), "n": nome},
        ).scalar()


def _criar_cenario():
    """Cria uma clinica com um profissional e um servico."""
    tenant = uuid.uuid4()
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica 5.1', true)"),
            {"t": str(tenant)},
        )
        servico = conexao.execute(
            text("INSERT INTO servicos (tenant_id, nome, ativo) VALUES (:t, 'Serv 5.1', true) RETURNING id"),
            {"t": str(tenant)},
        ).scalar()
    return tenant, _inserir_profissional(tenant), servico


def _remover_cenario(tenant):
    # Limpeza: agendamentos antes das tabelas de apoio por causa das FKs
    with engine_admin.begin() as conexao:
        for tabela in ("agendamentos", "servicos", "profissionais", "clinicas"):
            conexao.execute(
                text(f"DELETE FROM {tabela} WHERE tenant_id = :t"),
                {"t": str(tenant)},
            )


@pytest.fixture
def cenario():
    """Cria uma clinica com um profissional e um servico, e remove tudo ao final."""
    dados = _criar_cenario()
    yield dados
    _remover_cenario(dados[0])


@pytest.fixture
def outro_cenario():
    """Segunda clinica, independente da primeira, para os casos entre clinicas."""
    dados = _criar_cenario()
    yield dados
    _remover_cenario(dados[0])


@contextmanager
def sessao_tenant(tenant):
    """Sessao app_clinicas com app.tenant_id fixado na transacao, commit ao sair."""
    session = SessionLocal()
    try:
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenant)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _janela(horas_a_frente=48, duracao_min=30):
    """Monta um par (inicio, fim) aware em UTC, por padrao 48h a frente, 30 min."""
    inicio = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=horas_a_frente)
    return inicio, inicio + timedelta(minutes=duracao_min)


def test_criar_insere_agendamento_do_tenant_da_sessao(cenario):
    """criar grava um agendamento 'agendado' e devolve a linha, com o tenant da sessao."""
    tenant, profissional, servico = cenario
    inicio, fim = _janela()
    agenda = AgendaPropria()

    with sessao_tenant(tenant) as session:
        criado = agenda.criar(
            session,
            profissional_id=profissional,
            servico_id=servico,
            contato_telefone=TELEFONE,
            inicio=inicio,
            fim=fim,
        )

    assert isinstance(criado, Agendamento)
    assert criado.id is not None
    assert criado.status == STATUS_AGENDADO
    assert criado.tenant_id == str(tenant)
    assert criado.profissional_id == profissional
    assert criado.servico_id == servico
    assert criado.contato_telefone == TELEFONE
    # inicio e fim voltam como aware (timestamptz) e representam o mesmo instante
    assert criado.inicio == inicio
    assert criado.fim == fim

    # A linha existe no banco, visivel sob o tenant da sessao
    with sessao_tenant(tenant) as session:
        total = session.execute(
            text("SELECT COUNT(*) FROM agendamentos WHERE id = :id AND status = 'agendado'"),
            {"id": criado.id},
        ).scalar()
    assert total == 1


def test_cancelar_marca_como_cancelado(cenario):
    """cancelar troca o status para 'cancelado' e devolve a linha atualizada."""
    tenant, profissional, servico = cenario
    inicio, fim = _janela()
    agenda = AgendaPropria()

    with sessao_tenant(tenant) as session:
        criado = agenda.criar(
            session,
            profissional_id=profissional,
            servico_id=servico,
            contato_telefone=TELEFONE,
            inicio=inicio,
            fim=fim,
        )
        cancelado = agenda.cancelar(session, criado.id)

    assert cancelado.id == criado.id
    assert cancelado.status == STATUS_CANCELADO

    with sessao_tenant(tenant) as session:
        status_no_banco = session.execute(
            text("SELECT status FROM agendamentos WHERE id = :id"),
            {"id": criado.id},
        ).scalar()
    assert status_no_banco == STATUS_CANCELADO


def test_cancelar_id_inexistente_levanta(cenario):
    """cancelar um id que nao existe para o tenant da sessao levanta erro claro."""
    tenant, _profissional, _servico = cenario
    agenda = AgendaPropria()

    with sessao_tenant(tenant) as session:
        with pytest.raises(AgendamentoNaoEncontrado):
            agenda.cancelar(session, 999999999)


def _criar(session, profissional, servico, inicio, fim):
    return AgendaPropria().criar(
        session,
        profissional_id=profissional,
        servico_id=servico,
        contato_telefone=TELEFONE,
        inicio=inicio,
        fim=fim,
    )


def _status_como_admin(agendamento_id):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text("SELECT status FROM agendamentos WHERE id = :id"), {"id": agendamento_id}
        ).scalar()


# --- B5: cancelar so alcanca agendamento ativo do proprio tenant ---


def test_cancelar_duas_vezes_levanta_na_segunda(cenario):
    """Um agendamento ja cancelado nao pode ser cancelado de novo como se fosse sucesso."""
    tenant, profissional, servico = cenario
    inicio, fim = _janela()
    agenda = AgendaPropria()

    with sessao_tenant(tenant) as session:
        criado = _criar(session, profissional, servico, inicio, fim)
        agenda.cancelar(session, criado.id)

    with sessao_tenant(tenant) as session:
        with pytest.raises(AgendamentoNaoEncontrado):
            agenda.cancelar(session, criado.id)


def test_cancelar_agendamento_real_de_outra_clinica_levanta(cenario, outro_cenario):
    """Com app_clinicas, o id real de outra clinica nao e alcancado. O RLS ja protege."""
    tenant_a, _, _ = cenario
    tenant_b, profissional_b, servico_b = outro_cenario
    inicio, fim = _janela()

    with sessao_tenant(tenant_b) as session:
        de_b = _criar(session, profissional_b, servico_b, inicio, fim)

    with sessao_tenant(tenant_a) as session:
        with pytest.raises(AgendamentoNaoEncontrado):
            AgendaPropria().cancelar(session, de_b.id)

    assert _status_como_admin(de_b.id) == STATUS_AGENDADO


def test_cancelar_filtra_o_tenant_mesmo_sem_rls(cenario, outro_cenario):
    """Segunda barreira (ADR 0002): o filtro explicito de tenant vale sem o RLS.

    A sessao usa a conta de administracao, que ignora o RLS, com app.tenant_id de
    A. So o filtro de tenant_id no proprio UPDATE impede cancelar o agendamento
    de B. A sessao termina em rollback, entao B nao e alterado nem se o teste falhar.
    """
    tenant_a, _, _ = cenario
    tenant_b, profissional_b, servico_b = outro_cenario
    inicio, fim = _janela()

    with sessao_tenant(tenant_b) as session:
        de_b = _criar(session, profissional_b, servico_b, inicio, fim)

    session = sessionmaker(bind=engine_admin)()
    try:
        session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_a)})
        with pytest.raises(AgendamentoNaoEncontrado):
            AgendaPropria().cancelar(session, de_b.id)
    finally:
        session.rollback()
        session.close()

    assert _status_como_admin(de_b.id) == STATUS_AGENDADO


# --- B6: criar valida fuso e intervalo antes de ir ao banco ---


class _SessaoQueNaoPodeSerUsada:
    """Sessao falsa: qualquer acesso ao banco falha o teste."""

    def execute(self, *args, **kwargs):
        raise AssertionError("criar foi ao banco com dados invalidos")


_INICIO_UTC = datetime(2027, 3, 1, 9, 0, tzinfo=timezone.utc)
_SEM_FUSO = datetime(2027, 3, 1, 9, 0)


@pytest.mark.parametrize(
    "inicio, fim",
    [
        pytest.param(_SEM_FUSO, _INICIO_UTC + timedelta(minutes=30), id="inicio_sem_fuso"),
        pytest.param(_INICIO_UTC, _SEM_FUSO + timedelta(minutes=30), id="fim_sem_fuso"),
        pytest.param(_SEM_FUSO, _SEM_FUSO + timedelta(minutes=30), id="ambos_sem_fuso"),
        pytest.param(_INICIO_UTC, _INICIO_UTC, id="fim_igual_inicio"),
        pytest.param(_INICIO_UTC, _INICIO_UTC - timedelta(minutes=30), id="fim_antes_do_inicio"),
    ],
)
def test_criar_rejeita_dados_invalidos_antes_do_banco(inicio, fim):
    with pytest.raises(ValueError):
        AgendaPropria().criar(
            _SessaoQueNaoPodeSerUsada(),
            profissional_id=1,
            servico_id=1,
            contato_telefone=TELEFONE,
            inicio=inicio,
            fim=fim,
        )


def test_controle_criar_aceita_fuso_diferente_de_utc(cenario):
    """Controle: um horario com fuso -03:00 e aceito e gravado como o mesmo instante."""
    tenant, profissional, servico = cenario
    brasilia = timezone(timedelta(hours=-3))
    inicio = datetime(2027, 3, 1, 9, 0, tzinfo=brasilia)
    fim = inicio + timedelta(minutes=30)

    with sessao_tenant(tenant) as session:
        criado = _criar(session, profissional, servico, inicio, fim)

    assert criado.inicio == inicio
    assert criado.inicio == datetime(2027, 3, 1, 12, 0, tzinfo=timezone.utc)


# --- B7: constraint EXCLUDE ex_agendamentos_conflito (ADR 0004) ---


def _horario(hora, minuto=0):
    return datetime(2027, 4, 5, hora, minuto, tzinfo=timezone.utc)


def test_sobreposicao_do_mesmo_profissional_e_rejeitada_com_23p01(cenario):
    tenant, profissional, servico = cenario
    with sessao_tenant(tenant) as session:
        _criar(session, profissional, servico, _horario(10), _horario(10, 30))

    with pytest.raises(IntegrityError) as erro:
        with sessao_tenant(tenant) as session:
            _criar(session, profissional, servico, _horario(10, 15), _horario(10, 45))
    assert erro.value.orig.pgcode == "23P01"  # exclusion_violation


def test_horarios_adjacentes_sao_aceitos(cenario):
    """Intervalo semiaberto: terminar as 10:30 nao conflita com comecar as 10:30."""
    tenant, profissional, servico = cenario
    with sessao_tenant(tenant) as session:
        _criar(session, profissional, servico, _horario(10), _horario(10, 30))
        _criar(session, profissional, servico, _horario(10, 30), _horario(11))
        _criar(session, profissional, servico, _horario(9, 30), _horario(10))


def test_agendamento_cancelado_nao_conflita(cenario):
    tenant, profissional, servico = cenario
    agenda = AgendaPropria()
    with sessao_tenant(tenant) as session:
        primeiro = _criar(session, profissional, servico, _horario(10), _horario(10, 30))
        agenda.cancelar(session, primeiro.id)
        _criar(session, profissional, servico, _horario(10), _horario(10, 30))


def test_mesmo_horario_com_outro_profissional_da_clinica_e_aceito(cenario):
    """Controle: a constraint e por profissional, nao bloqueia a clinica inteira."""
    tenant, profissional, servico = cenario
    outro_profissional = _inserir_profissional(tenant, "Prof 5.1 B")
    with sessao_tenant(tenant) as session:
        _criar(session, profissional, servico, _horario(10), _horario(10, 30))
        _criar(session, outro_profissional, servico, _horario(10), _horario(10, 30))


def test_mesmo_horario_em_clinicas_diferentes_e_aceito(cenario, outro_cenario):
    tenant_a, profissional_a, servico_a = cenario
    tenant_b, profissional_b, servico_b = outro_cenario
    with sessao_tenant(tenant_a) as session:
        _criar(session, profissional_a, servico_a, _horario(10), _horario(10, 30))
    with sessao_tenant(tenant_b) as session:
        _criar(session, profissional_b, servico_b, _horario(10), _horario(10, 30))


# --- lock da agenda do profissional (ADR 0011) -------------------------------------

_INICIO_LOCK = datetime(2030, 1, 7, 13, tzinfo=timezone.utc)


def _locks_da_agenda(profissional_id, tenant=None):
    """Advisory locks de dois inteiros concedidos para o profissional, vistos por fora.

    Com tenant, conta so os locks cuja primeira chave e o hash desse tenant. O
    classid e oid, sem sinal, entao o hash entra como os 32 bits sem sinal.
    """
    filtro_tenant = (
        " AND classid::bigint = (hashtext(:t)::bigint & 4294967295)" if tenant else ""
    )
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                "AND objsubid = 2 AND objid = :prof AND granted" + filtro_tenant
            ),
            {"prof": profissional_id, "t": str(tenant) if tenant else None},
        ).scalar()


def _agendamentos_do_profissional(profissional_id):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text("SELECT count(*) FROM agendamentos WHERE profissional_id = :p"),
            {"p": profissional_id},
        ).scalar()


def _criar_em(session, profissional, servico):
    return AgendaPropria().criar(
        session,
        profissional_id=profissional,
        servico_id=servico,
        contato_telefone=TELEFONE,
        inicio=_INICIO_LOCK,
        fim=_INICIO_LOCK + timedelta(minutes=30),
    )


def test_criar_segura_o_lock_da_agenda_ate_o_commit(cenario):
    tenant, profissional, servico = cenario
    assert _locks_da_agenda(profissional) == 0

    with sessao_tenant(tenant) as session:
        _criar_em(session, profissional, servico)
        assert _locks_da_agenda(profissional) == 1
        # A chave do lock leva o tenant da sessao, e nao uma constante (ADR 0011)
        assert _locks_da_agenda(profissional, tenant=tenant) == 1

    assert _locks_da_agenda(profissional) == 0


def test_sem_tenant_em_conexao_nova_nao_pega_o_lock_nem_grava(cenario):
    # Conexao app_clinicas que nunca definiu app.tenant_id: o setting nao existe.
    _, profissional, servico = cenario
    engine_novo = create_engine(DATABASE_URL, poolclass=NullPool)
    try:
        with engine_novo.connect() as conexao:
            with pytest.raises(DBAPIError, match="app.tenant_id"):
                _criar_em(conexao, profissional, servico)
    finally:
        engine_novo.dispose()
    assert _locks_da_agenda(profissional) == 0
    assert _agendamentos_do_profissional(profissional) == 0


def test_sem_tenant_depois_de_transacao_com_tenant_nao_pega_o_lock_nem_grava(cenario):
    # Na mesma conexao, o set_config local de uma transacao anterior deixa o setting
    # vazio, e nao ausente. O ::uuid da chave faz a chamada falhar mesmo assim.
    tenant, profissional, servico = cenario
    engine_novo = create_engine(DATABASE_URL, poolclass=NullPool)
    try:
        with engine_novo.connect() as conexao:
            with conexao.begin():
                conexao.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"),
                    {"t": str(tenant)},
                )
            vazio = conexao.execute(
                text("SELECT current_setting('app.tenant_id')")
            ).scalar()
            assert vazio == ""
            conexao.rollback()
            with pytest.raises(DBAPIError, match="uuid"):
                _criar_em(conexao, profissional, servico)
    finally:
        engine_novo.dispose()
    assert _locks_da_agenda(profissional) == 0
    assert _agendamentos_do_profissional(profissional) == 0

