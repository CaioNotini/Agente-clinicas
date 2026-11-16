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


@pytest.fixture
def cenario():
    """Cria uma clinica com um profissional e um servico, e remove tudo ao final."""
    tenant = uuid.uuid4()
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica 5.1', true)"),
            {"t": str(tenant)},
        )
        profissional = conexao.execute(
            text("INSERT INTO profissionais (tenant_id, nome, ativo) VALUES (:t, 'Prof 5.1', true) RETURNING id"),
            {"t": str(tenant)},
        ).scalar()
        servico = conexao.execute(
            text("INSERT INTO servicos (tenant_id, nome, ativo) VALUES (:t, 'Serv 5.1', true) RETURNING id"),
            {"t": str(tenant)},
        ).scalar()
    yield tenant, profissional, servico
    # Limpeza: agendamentos antes das tabelas de apoio por causa das FKs
    with engine_admin.begin() as conexao:
        for tabela in ("agendamentos", "servicos", "profissionais", "clinicas"):
            conexao.execute(
                text(f"DELETE FROM {tabela} WHERE tenant_id = :t"),
                {"t": str(tenant)},
            )


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
