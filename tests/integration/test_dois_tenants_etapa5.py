"""Regras da etapa 5 exercitadas nos dois cenarios do publico-alvo (ADR 0009).

Cenario A: clinica com equipe e recepcao, fuso America/Sao_Paulo, politica de
cancelamento 'handoff', duracao pela do servico.
Cenario B: consultorio de um profissional so, sem recepcao, fuso America/Manaus,
politica 'aceitar_e_marcar', duracao por override do profissional.

A mesma regra de duracao (Q-21) e a mesma leitura de configuracao valem nos dois,
com valores diferentes. Usa a conta de administracao (cnotini) para semear.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from app.agenda.regras import calcular_fim, resolver_duracao_minutos
from app.config import MIGRATION_DATABASE_URL

engine_admin = create_engine(MIGRATION_DATABASE_URL)


def _semear_clinica(conexao, *, fuso, politica, duracao_servico, override):
    """Cria uma clinica completa e devolve ids e configuracao lidos do banco."""
    tenant_id = str(uuid.uuid4())
    conexao.execute(
        text(
            "INSERT INTO clinicas (tenant_id, nome, ativo, fuso) VALUES (:t, 'C', true, :f)"
        ),
        {"t": tenant_id, "f": fuso},
    )
    prof = conexao.execute(
        text(
            "INSERT INTO profissionais (tenant_id, nome, ativo) VALUES (:t, 'P', true) RETURNING id"
        ),
        {"t": tenant_id},
    ).scalar()
    serv = conexao.execute(
        text(
            "INSERT INTO servicos (tenant_id, nome, duracao_minutos) VALUES (:t, 'S', :d) RETURNING id"
        ),
        {"t": tenant_id, "d": duracao_servico},
    ).scalar()
    conexao.execute(
        text(
            "INSERT INTO profissional_servicos (tenant_id, profissional_id, servico_id, duracao_minutos) "
            "VALUES (:t, :p, :s, :o)"
        ),
        {"t": tenant_id, "p": prof, "s": serv, "o": override},
    )
    conexao.execute(
        text(
            "INSERT INTO regras_agendamento (tenant_id, politica_cancelamento_fora_janela) "
            "VALUES (:t, :pol)"
        ),
        {"t": tenant_id, "pol": politica},
    )
    return {"tenant": tenant_id, "prof": prof, "serv": serv}


@pytest.fixture
def dois_tenants():
    with engine_admin.begin() as conexao:
        equipe = _semear_clinica(
            conexao,
            fuso="America/Sao_Paulo",
            politica="handoff",
            duracao_servico=30,
            override=None,
        )
        solo = _semear_clinica(
            conexao,
            fuso="America/Manaus",
            politica="aceitar_e_marcar",
            duracao_servico=30,
            override=60,
        )
    yield {"equipe": equipe, "solo": solo}
    with engine_admin.begin() as conexao:
        for cenario in (equipe, solo):
            for tabela in (
                "regras_agendamento",
                "profissional_servicos",
                "servicos",
                "profissionais",
                "clinicas",
            ):
                conexao.execute(
                    text(f"DELETE FROM {tabela} WHERE tenant_id = :t"),
                    {"t": cenario["tenant"]},
                )


def _config(tenant_id):
    with engine_admin.connect() as conexao:
        fuso = conexao.execute(
            text("SELECT fuso FROM clinicas WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar()
        politica = conexao.execute(
            text(
                "SELECT politica_cancelamento_fora_janela FROM regras_agendamento WHERE tenant_id = :t"
            ),
            {"t": tenant_id},
        ).scalar()
        duracoes = conexao.execute(
            text(
                "SELECT s.duracao_minutos AS servico, ps.duracao_minutos AS override "
                "FROM profissional_servicos ps JOIN servicos s "
                "ON s.tenant_id = ps.tenant_id AND s.id = ps.servico_id "
                "WHERE ps.tenant_id = :t"
            ),
            {"t": tenant_id},
        ).first()
    return {
        "fuso": fuso,
        "politica": politica,
        "servico": duracoes.servico,
        "override": duracoes.override,
    }


def test_configuracao_distinta_entre_os_dois_cenarios(dois_tenants):
    equipe = _config(dois_tenants["equipe"]["tenant"])
    solo = _config(dois_tenants["solo"]["tenant"])

    assert equipe["fuso"] == "America/Sao_Paulo"
    assert equipe["politica"] == "handoff"
    assert solo["fuso"] == "America/Manaus"
    assert solo["politica"] == "aceitar_e_marcar"


def test_duracao_resolvida_por_cenario(dois_tenants):
    equipe = _config(dois_tenants["equipe"]["tenant"])
    solo = _config(dois_tenants["solo"]["tenant"])

    # Clinica com equipe: sem override, vale a duracao do servico
    assert resolver_duracao_minutos(equipe["servico"], equipe["override"]) == 30
    # Consultorio solo: override do profissional vence a do servico
    assert resolver_duracao_minutos(solo["servico"], solo["override"]) == 60


def test_fim_do_agendamento_reflete_a_duracao_do_cenario(dois_tenants):
    inicio = datetime(2027, 4, 1, 12, 0, tzinfo=timezone.utc)
    equipe = _config(dois_tenants["equipe"]["tenant"])
    solo = _config(dois_tenants["solo"]["tenant"])

    fim_equipe = calcular_fim(
        inicio, resolver_duracao_minutos(equipe["servico"], equipe["override"])
    )
    fim_solo = calcular_fim(
        inicio, resolver_duracao_minutos(solo["servico"], solo["override"])
    )

    assert fim_equipe == inicio + timedelta(minutes=30)
    assert fim_solo == inicio + timedelta(minutes=60)
