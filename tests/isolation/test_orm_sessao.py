"""Teste de sessão ORM para as tabelas novas de app/db/models.py (D-04).

Prova que o modelo funciona em uso real: a aplicação conecta com app_clinicas,
insere e lê pelo ORM, e uma escrita cruzada entre tenants é bloqueada pelo RLS.
A limpeza usa a conta de administração (cnotini), só para remover os UUIDs
gerados por este teste.
"""
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.config import MIGRATION_DATABASE_URL
from app.db.database import SessionLocal
from app.db.models import Clinica, Conversa, Handoff, PacienteContato, RegraAgendamento

# Conexão de administração, usada só na limpeza desta função
engine_admin = create_engine(MIGRATION_DATABASE_URL)

# Telefone fictício usado nas linhas de contato deste teste
TELEFONE = "(00) 00000-0001"


def test_sessao_orm_cria_le_e_bloqueia_tenant_cruzado():
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    session = SessionLocal()
    try:
        # 1. Inserção pelo ORM, com o tenant A definido na sessão
        session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_a)})

        clinica = Clinica(tenant_id=tenant_a, nome="Clinica ORM Teste", ativo=True)
        session.add(clinica)
        session.flush()

        conversa = Conversa(tenant_id=tenant_a, contato_telefone=TELEFONE, estado_conversa="idle", human_mode=False)
        session.add(conversa)
        session.flush()

        paciente = PacienteContato(tenant_id=tenant_a, contato_telefone=TELEFONE, nome="Paciente ORM Teste")
        session.add(paciente)
        session.flush()

        regra = RegraAgendamento(
            tenant_id=tenant_a,
            antecedencia_minima_horas=2,
            antecedencia_maxima_dias=60,
            janela_cancelamento_horas=48,
        )
        session.add(regra)
        session.flush()

        handoff = Handoff(tenant_id=tenant_a, conversa_id=conversa.id, motivo="urgencia")
        session.add(handoff)
        session.flush()

        # 2. criada_em preenchida pelo banco, via server_default
        assert clinica.criada_em is not None
        assert conversa.criada_em is not None
        assert paciente.criada_em is not None
        assert regra.criada_em is not None
        assert handoff.criada_em is not None

        session.commit()

        # 3. Leitura pela mesma sessão, em uma nova transação
        session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_a)})
        session.expire_all()
        assert session.query(Clinica).filter_by(tenant_id=tenant_a).count() == 1
        assert session.query(Conversa).filter_by(tenant_id=tenant_a).count() == 1
        assert session.query(PacienteContato).filter_by(tenant_id=tenant_a).count() == 1
        assert session.query(RegraAgendamento).filter_by(tenant_id=tenant_a).count() == 1
        assert session.query(Handoff).filter_by(tenant_id=tenant_a).count() == 1

        # 4. Escrita cruzada: tenant A tentando gravar uma linha com tenant_id de B
        paciente_intruso = PacienteContato(tenant_id=tenant_b, contato_telefone=TELEFONE, nome="Paciente Intruso")
        session.add(paciente_intruso)
        with pytest.raises(DBAPIError, match="row-level security"):
            session.flush()
    finally:
        # 5. Limpeza: encerra a transação da sessão e remove só o que este teste criou
        if session.in_transaction():
            session.rollback()
        session.close()
        with engine_admin.begin() as conexao:
            conexao.execute(text("DELETE FROM handoffs WHERE tenant_id = :t"), {"t": str(tenant_a)})
            conexao.execute(text("DELETE FROM pacientes_contatos WHERE tenant_id = :t"), {"t": str(tenant_a)})
            conexao.execute(text("DELETE FROM regras_agendamento WHERE tenant_id = :t"), {"t": str(tenant_a)})
            conexao.execute(text("DELETE FROM conversas WHERE tenant_id = :t"), {"t": str(tenant_a)})
            conexao.execute(text("DELETE FROM clinicas WHERE tenant_id = :t"), {"t": str(tenant_a)})
