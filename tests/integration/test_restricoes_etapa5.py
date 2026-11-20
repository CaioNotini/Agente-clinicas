"""Restricoes de schema das colunas novas da etapa 5 (ADR 0009).

Defaults e CHECK ficam no banco, para valerem em qualquer caminho de escrita.
Usam a conta de administracao (cnotini): o objetivo aqui e o schema, nao o RLS.
"""
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.config import MIGRATION_DATABASE_URL

engine_admin = create_engine(MIGRATION_DATABASE_URL)

TELEFONE = "(00) 00000-0501"


@pytest.fixture
def cenario():
    """Clinica com um profissional, um servico e uma conversa, para as FKs."""
    tenant_id = str(uuid.uuid4())
    with engine_admin.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica Etapa5', true)"
            ),
            {"t": tenant_id},
        )
        prof = conexao.execute(
            text(
                "INSERT INTO profissionais (tenant_id, nome, ativo) VALUES (:t, 'Prof', true) RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar()
        serv = conexao.execute(
            text(
                "INSERT INTO servicos (tenant_id, nome, duracao_minutos) VALUES (:t, 'Serv', 30) RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar()
        conversa = conexao.execute(
            text(
                "INSERT INTO conversas (tenant_id, contato_telefone) VALUES (:t, :tel) RETURNING id"
            ),
            {"t": tenant_id, "tel": TELEFONE},
        ).scalar()
    yield {"tenant": tenant_id, "prof": prof, "serv": serv, "conversa": conversa}
    with engine_admin.begin() as conexao:
        for tabela in (
            "handoffs",
            "agendamentos",
            "regras_agendamento",
            "profissional_servicos",
            "conversas",
            "servicos",
            "profissionais",
            "clinicas",
        ):
            conexao.execute(
                text(f"DELETE FROM {tabela} WHERE tenant_id = :t"), {"t": tenant_id}
            )


# --- clinicas.fuso ------------------------------------------------------------


def test_clinica_omitindo_fuso_recebe_sao_paulo(cenario):
    with engine_admin.connect() as conexao:
        fuso = conexao.execute(
            text("SELECT fuso FROM clinicas WHERE tenant_id = :t"),
            {"t": cenario["tenant"]},
        ).scalar()
    assert fuso == "America/Sao_Paulo"


# --- regras_agendamento.politica_cancelamento_fora_janela ---------------------


def test_regras_omitindo_politica_recebe_handoff(cenario):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("INSERT INTO regras_agendamento (tenant_id) VALUES (:t)"),
            {"t": cenario["tenant"]},
        )
    with engine_admin.connect() as conexao:
        politica = conexao.execute(
            text(
                "SELECT politica_cancelamento_fora_janela FROM regras_agendamento WHERE tenant_id = :t"
            ),
            {"t": cenario["tenant"]},
        ).scalar()
    assert politica == "handoff"


@pytest.mark.parametrize("valor", ["aceitar_e_marcar", "handoff"])
def test_regras_aceita_politica_conhecida(cenario, valor):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO regras_agendamento (tenant_id, politica_cancelamento_fora_janela) "
                "VALUES (:t, :p)"
            ),
            {"t": cenario["tenant"], "p": valor},
        )


def test_regras_rejeita_politica_desconhecida(cenario):
    with pytest.raises(IntegrityError):
        with engine_admin.begin() as conexao:
            conexao.execute(
                text(
                    "INSERT INTO regras_agendamento (tenant_id, politica_cancelamento_fora_janela) "
                    "VALUES (:t, 'rejeitar')"
                ),
                {"t": cenario["tenant"]},
            )


# --- agendamentos.cancelado_fora_da_janela ------------------------------------


def test_agendamento_nasce_sem_marca_de_cancelamento_tardio(cenario):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO agendamentos "
                "(tenant_id, profissional_id, servico_id, contato_telefone, inicio, fim) "
                "VALUES (:t, :p, :s, :tel, '2027-05-01 13:00:00+00', '2027-05-01 13:30:00+00')"
            ),
            {
                "t": cenario["tenant"],
                "p": cenario["prof"],
                "s": cenario["serv"],
                "tel": TELEFONE,
            },
        )
    with engine_admin.connect() as conexao:
        marca = conexao.execute(
            text(
                "SELECT cancelado_fora_da_janela FROM agendamentos WHERE tenant_id = :t"
            ),
            {"t": cenario["tenant"]},
        ).scalar()
    assert marca is False


# --- handoffs.notificado_canal ------------------------------------------------


@pytest.mark.parametrize("canal", ["cli", "whatsapp"])
def test_handoff_aceita_canal_conhecido(cenario, canal):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO handoffs (tenant_id, conversa_id, motivo, notificado_para, notificado_canal) "
                "VALUES (:t, :c, 'urgencia', '(00) 0000-0003', :canal)"
            ),
            {"t": cenario["tenant"], "c": cenario["conversa"], "canal": canal},
        )


def test_handoff_aceita_canal_nulo(cenario):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO handoffs (tenant_id, conversa_id, motivo) VALUES (:t, :c, 'urgencia')"
            ),
            {"t": cenario["tenant"], "c": cenario["conversa"]},
        )


def test_handoff_rejeita_canal_desconhecido(cenario):
    with pytest.raises(IntegrityError):
        with engine_admin.begin() as conexao:
            conexao.execute(
                text(
                    "INSERT INTO handoffs (tenant_id, conversa_id, motivo, notificado_canal) "
                    "VALUES (:t, :c, 'urgencia', 'sms')"
                ),
                {"t": cenario["tenant"], "c": cenario["conversa"]},
            )
