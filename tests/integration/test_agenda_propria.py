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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import MIGRATION_DATABASE_URL
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
