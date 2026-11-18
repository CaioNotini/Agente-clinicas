"""Restricoes de schema em jobs, conversas e mensagens (ADR 0005 e item A5 do plano).

Defaults, NOT NULL e CHECK ficam no banco, para valerem em qualquer caminho de
escrita, inclusive SQL manual. Os testes usam a conta de administracao (cnotini),
porque CHECK e NOT NULL valem para qualquer role e o objetivo aqui nao e o RLS.
"""
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.channels.base import MensagemEntrada
from app.config import MIGRATION_DATABASE_URL
from app.jobs.queue import gravar_e_enfileirar

engine_admin = create_engine(MIGRATION_DATABASE_URL)

TELEFONE = "(00) 00000-0201"


@pytest.fixture
def tenant():
    tenant_id = str(uuid.uuid4())
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica Restricoes', true)"),
            {"t": tenant_id},
        )
    yield tenant_id
    with engine_admin.begin() as conexao:
        for tabela in ("jobs", "mensagens", "conversas", "clinicas"):
            conexao.execute(text(f"DELETE FROM {tabela} WHERE tenant_id = :t"), {"t": tenant_id})


def _executar(sql, parametros):
    with engine_admin.begin() as conexao:
        return conexao.execute(text(sql), parametros)


# --- jobs ---------------------------------------------------------------------

def test_job_omitindo_controle_recebe_defaults(tenant):
    """Sem status, run_at, attempts e max_attempts, o banco preenche os defaults."""
    job_id = _executar(
        "INSERT INTO jobs (tenant_id, type) VALUES (:t, 'SEND_REMINDER') RETURNING id",
        {"t": tenant},
    ).scalar()

    with engine_admin.connect() as conexao:
        linha = conexao.execute(
            text("SELECT status, run_at, attempts, max_attempts FROM jobs WHERE id = :id"),
            {"id": job_id},
        ).first()
    assert linha.status == "pending"
    assert linha.run_at is not None
    assert (linha.attempts, linha.max_attempts) == (0, 3)


@pytest.mark.parametrize("coluna", ["status", "run_at", "attempts", "max_attempts"])
def test_job_rejeita_controle_nulo(tenant, coluna):
    with pytest.raises(IntegrityError):
        _executar(
            f"INSERT INTO jobs (tenant_id, type, {coluna}) VALUES (:t, 'SEND_REMINDER', NULL)",
            {"t": tenant},
        )


def test_job_rejeita_status_desconhecido(tenant):
    with pytest.raises(IntegrityError):
        _executar(
            "INSERT INTO jobs (tenant_id, type, status) VALUES (:t, 'SEND_REMINDER', 'xyz')",
            {"t": tenant},
        )


def test_job_de_mensagem_exige_conversa(tenant):
    """PROCESS_INBOUND_MESSAGE sem contato_telefone escaparia da regra de ordem."""
    with pytest.raises(IntegrityError):
        _executar(
            "INSERT INTO jobs (tenant_id, type) VALUES (:t, 'PROCESS_INBOUND_MESSAGE')",
            {"t": tenant},
        )


def test_enfileirar_preenche_conversa_do_job(tenant):
    """O caminho da aplicacao grava contato_telefone na coluna do job."""
    resultado = gravar_e_enfileirar(
        MensagemEntrada(id=uuid.uuid4().hex, tenant_id=tenant, contato_telefone=TELEFONE, conteudo="oi")
    )
    with engine_admin.connect() as conexao:
        contato = conexao.execute(
            text("SELECT contato_telefone FROM jobs WHERE id = :id"),
            {"id": resultado.job_id},
        ).scalar()
    assert contato == TELEFONE


# --- conversas ----------------------------------------------------------------

def test_conversa_omitindo_estado_recebe_defaults(tenant):
    _executar(
        "INSERT INTO conversas (tenant_id, contato_telefone) VALUES (:t, :tel)",
        {"t": tenant, "tel": TELEFONE},
    )
    with engine_admin.connect() as conexao:
        linha = conexao.execute(
            text("SELECT estado_conversa, human_mode FROM conversas WHERE tenant_id = :t"),
            {"t": tenant},
        ).first()
    assert (linha.estado_conversa, linha.human_mode) == ("idle", False)


def test_conversa_rejeita_estado_desconhecido(tenant):
    with pytest.raises(IntegrityError):
        _executar(
            "INSERT INTO conversas (tenant_id, contato_telefone, estado_conversa) VALUES (:t, :tel, 'xyz')",
            {"t": tenant, "tel": TELEFONE},
        )


@pytest.mark.parametrize("coluna", ["estado_conversa", "human_mode"])
def test_conversa_rejeita_nulo(tenant, coluna):
    with pytest.raises(IntegrityError):
        _executar(
            f"INSERT INTO conversas (tenant_id, contato_telefone, {coluna}) VALUES (:t, :tel, NULL)",
            {"t": tenant, "tel": TELEFONE},
        )


# --- mensagens ----------------------------------------------------------------

@pytest.mark.parametrize("direcao", ["in", "out", "xyz"])
def test_mensagem_rejeita_direcao_desconhecida(tenant, direcao):
    with pytest.raises(IntegrityError):
        _executar(
            "INSERT INTO mensagens (id, tenant_id, contato_telefone, conteudo, direcao) "
            "VALUES (:id, :t, :tel, 'x', :d)",
            {"id": uuid.uuid4().hex, "t": tenant, "tel": TELEFONE, "d": direcao},
        )


@pytest.mark.parametrize("direcao", ["entrada", "saida"])
def test_mensagem_aceita_direcao_conhecida(tenant, direcao):
    _executar(
        "INSERT INTO mensagens (id, tenant_id, contato_telefone, conteudo, direcao) "
        "VALUES (:id, :t, :tel, 'x', :d)",
        {"id": uuid.uuid4().hex, "t": tenant, "tel": TELEFONE, "d": direcao},
    )
