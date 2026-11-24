"""Relacionamentos entre clinicas: uma linha de A nao pode apontar para registro de B (A1).

A verificacao de FK do Postgres ignora o RLS. Com FK simples sobre id, uma sessao
app_clinicas do tenant A consegue gravar um agendamento com o profissional de B,
porque o id existe na tabela pai, mesmo invisivel para A. A FK composta
(tenant_id, id) faz o banco recusar.

A verificacao usa app_clinicas, com app.tenant_id de A, como a aplicacao. Os dados
de apoio sao criados e removidos com a conta de administracao (cnotini). Toda
escrita de teste termina em rollback.
"""
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.config import DATABASE_URL, MIGRATION_DATABASE_URL

engine_app = create_engine(DATABASE_URL)
engine_admin = create_engine(MIGRATION_DATABASE_URL)

TELEFONE = "(00) 00000-0301"

_SQL_AGENDAMENTO = (
    "INSERT INTO agendamentos (tenant_id, profissional_id, servico_id, contato_telefone, "
    "inicio, fim, status) VALUES (:t, :prof, :serv, :tel, "
    "'2027-02-01 10:00+00', '2027-02-01 10:30+00', 'agendado') RETURNING id"
)
_SQL_HORARIO = (
    "INSERT INTO horarios_trabalho (tenant_id, profissional_id, dia_semana, ativo) "
    "VALUES (:t, :prof, 1, true) RETURNING id"
)
_SQL_PROF_SERV = (
    "INSERT INTO profissional_servicos (tenant_id, profissional_id, servico_id) "
    "VALUES (:t, :prof, :serv) RETURNING id"
)
_SQL_HANDOFF = (
    "INSERT INTO handoffs (tenant_id, conversa_id, motivo, agendamento_id, mensagem_id) "
    "VALUES (:t, :conv, 'urgencia', :ag, :msg) RETURNING id"
)

# (tabela, coluna, chave do parametro que aponta para o registro pai, SQL de insercao)
CASOS = [
    pytest.param("agendamentos", "profissional_id", "prof", _SQL_AGENDAMENTO, id="agendamentos.profissional_id"),
    pytest.param("agendamentos", "servico_id", "serv", _SQL_AGENDAMENTO, id="agendamentos.servico_id"),
    pytest.param("horarios_trabalho", "profissional_id", "prof", _SQL_HORARIO, id="horarios_trabalho.profissional_id"),
    pytest.param("profissional_servicos", "profissional_id", "prof", _SQL_PROF_SERV, id="profissional_servicos.profissional_id"),
    pytest.param("profissional_servicos", "servico_id", "serv", _SQL_PROF_SERV, id="profissional_servicos.servico_id"),
    pytest.param("handoffs", "conversa_id", "conv", _SQL_HANDOFF, id="handoffs.conversa_id"),
    pytest.param("handoffs", "agendamento_id", "ag", _SQL_HANDOFF, id="handoffs.agendamento_id"),
    pytest.param("handoffs", "mensagem_id", "msg", _SQL_HANDOFF, id="handoffs.mensagem_id"),
]

_TABELAS_LIMPEZA = (
    "handoffs", "agendamentos", "mensagens", "horarios_trabalho", "profissional_servicos",
    "conversas", "servicos", "profissionais", "clinicas",
)


def _semear(conexao, tenant):
    """Cria clinica, profissional, servico, conversa, agendamento e mensagem.

    Devolve os ids pai."""
    conexao.execute(
        text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica FK', true)"),
        {"t": tenant},
    )
    prof = conexao.execute(
        text("INSERT INTO profissionais (tenant_id, nome, ativo) VALUES (:t, 'Prof FK', true) RETURNING id"),
        {"t": tenant},
    ).scalar()
    serv = conexao.execute(
        text("INSERT INTO servicos (tenant_id, nome, ativo) VALUES (:t, 'Serv FK', true) RETURNING id"),
        {"t": tenant},
    ).scalar()
    conv = conexao.execute(
        text("INSERT INTO conversas (tenant_id, contato_telefone) VALUES (:t, :tel) RETURNING id"),
        {"t": tenant, "tel": TELEFONE},
    ).scalar()
    # Outro horario que o de _SQL_AGENDAMENTO, para os casos de agendamentos nao
    # conflitarem com este pela constraint EXCLUDE
    ag = conexao.execute(
        text(
            "INSERT INTO agendamentos (tenant_id, profissional_id, servico_id, "
            "contato_telefone, inicio, fim, status) VALUES (:t, :prof, :serv, :tel, "
            "'2027-02-02 10:00+00', '2027-02-02 10:30+00', 'agendado') RETURNING id"
        ),
        {"t": tenant, "prof": prof, "serv": serv, "tel": TELEFONE},
    ).scalar()
    msg = uuid.uuid4().hex
    conexao.execute(
        text(
            "INSERT INTO mensagens (id, tenant_id, contato_telefone, conteudo, direcao) "
            "VALUES (:id, :t, :tel, 'oi', 'entrada')"
        ),
        {"id": msg, "t": tenant, "tel": TELEFONE},
    )
    return {"prof": prof, "serv": serv, "conv": conv, "ag": ag, "msg": msg}


@pytest.fixture(scope="module")
def clinicas():
    """Duas clinicas, A e B, cada uma com profissional, servico e conversa."""
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    with engine_admin.begin() as conexao:
        pais_a = _semear(conexao, tenant_a)
        pais_b = _semear(conexao, tenant_b)
    yield {"a": (tenant_a, pais_a), "b": (tenant_b, pais_b)}
    with engine_admin.begin() as conexao:
        for tabela in _TABELAS_LIMPEZA:
            conexao.execute(
                text(f"DELETE FROM {tabela} WHERE tenant_id IN (:a, :b)"),
                {"a": tenant_a, "b": tenant_b},
            )


def _parametros(tenant, pais):
    return {"t": tenant, "tel": TELEFONE, **pais}


@pytest.mark.parametrize("tabela, coluna, chave, sql_insercao", CASOS)
def test_insercao_com_registro_pai_de_outra_clinica_e_rejeitada(clinicas, tabela, coluna, chave, sql_insercao):
    """Prova do problema: A grava uma linha que aponta para o registro de B."""
    tenant_a, pais_a = clinicas["a"]
    _, pais_b = clinicas["b"]
    parametros = _parametros(tenant_a, {**pais_a, chave: pais_b[chave]})

    with engine_app.connect() as conexao:
        transacao = conexao.begin()
        try:
            conexao.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_a})
            with pytest.raises(IntegrityError) as erro:
                conexao.execute(text(sql_insercao), parametros)
            assert erro.value.orig.pgcode == "23503"  # foreign_key_violation
        finally:
            transacao.rollback()


@pytest.mark.parametrize("tabela, coluna, chave, sql_insercao", CASOS)
def test_alteracao_para_registro_pai_de_outra_clinica_e_rejeitada(clinicas, tabela, coluna, chave, sql_insercao):
    """Uma linha valida de A nao pode passar a apontar para o registro de B."""
    tenant_a, pais_a = clinicas["a"]
    _, pais_b = clinicas["b"]

    with engine_app.connect() as conexao:
        transacao = conexao.begin()
        try:
            conexao.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_a})
            linha_id = conexao.execute(text(sql_insercao), _parametros(tenant_a, pais_a)).scalar()
            with pytest.raises(IntegrityError) as erro:
                conexao.execute(
                    text(f"UPDATE {tabela} SET {coluna} = :alheio WHERE id = :id"),
                    {"alheio": pais_b[chave], "id": linha_id},
                )
            assert erro.value.orig.pgcode == "23503"  # foreign_key_violation
        finally:
            transacao.rollback()


@pytest.mark.parametrize("tabela, coluna, chave, sql_insercao", CASOS)
def test_controle_insercao_com_registro_pai_da_propria_clinica_e_aceita(clinicas, tabela, coluna, chave, sql_insercao):
    """Controle: o mesmo SQL com os registros da propria clinica grava normalmente.

    Garante que a rejeicao do teste acima vem do registro de outra clinica, e nao
    de outro erro no SQL de insercao.
    """
    tenant_a, pais_a = clinicas["a"]

    with engine_app.connect() as conexao:
        transacao = conexao.begin()
        try:
            conexao.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_a})
            linha_id = conexao.execute(text(sql_insercao), _parametros(tenant_a, pais_a)).scalar()
            assert linha_id is not None
        finally:
            transacao.rollback()


# --- exclusao dos registros referenciados por handoffs (tarefa 5.4) ---


def _handoff_de_a(conexao, tenant_a, pais_a):
    conexao.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_a})
    return conexao.execute(text(_SQL_HANDOFF), _parametros(tenant_a, pais_a)).scalar()


def test_excluir_mensagem_referenciada_mantem_o_handoff_sem_a_referencia(clinicas):
    """Pedido de exclusao do titular (LGPD): a mensagem sai e o handoff fica.

    ON DELETE SET NULL (mensagem_id) zera so a coluna da mensagem. tenant_id, que
    tambem faz parte da FK, continua preenchido.
    """
    tenant_a, pais_a = clinicas["a"]
    with engine_app.connect() as conexao:
        transacao = conexao.begin()
        try:
            handoff_id = _handoff_de_a(conexao, tenant_a, pais_a)
            apagadas = conexao.execute(
                text("DELETE FROM mensagens WHERE id = :id"), {"id": pais_a["msg"]}
            ).rowcount
            linha = conexao.execute(
                text(
                    "SELECT tenant_id, mensagem_id, agendamento_id, conversa_id "
                    "FROM handoffs WHERE id = :id"
                ),
                {"id": handoff_id},
            ).first()
        finally:
            transacao.rollback()
    assert apagadas == 1
    assert linha is not None
    assert str(linha.tenant_id) == tenant_a
    assert linha.mensagem_id is None
    assert (linha.agendamento_id, linha.conversa_id) == (pais_a["ag"], pais_a["conv"])


def test_excluir_agendamento_referenciado_por_handoff_e_recusado(clinicas):
    """agendamento_id mantem a regra das outras FKs (NO ACTION)."""
    tenant_a, pais_a = clinicas["a"]
    with engine_app.connect() as conexao:
        transacao = conexao.begin()
        try:
            _handoff_de_a(conexao, tenant_a, pais_a)
            with pytest.raises(IntegrityError) as erro:
                conexao.execute(
                    text("DELETE FROM agendamentos WHERE id = :id"), {"id": pais_a["ag"]}
                )
            assert erro.value.orig.pgcode == "23503"
        finally:
            transacao.rollback()


def test_fk_da_mensagem_zera_so_a_coluna_da_mensagem():
    """Catalogo: o SET NULL tem a lista de colunas. Uma migration que recrie a FK sem
    ela zeraria tambem tenant_id, e o teste de catalogo das FKs nao perceberia."""
    with engine_app.connect() as conexao:
        definicao = conexao.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'fk_handoffs_mensagem_id_tenant'"
            )
        ).scalar()
    assert definicao is not None
    assert definicao.endswith("ON DELETE SET NULL (mensagem_id)")
