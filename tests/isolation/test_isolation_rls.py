"""Testes de isolamento entre clínicas (D-04).

A aplicação conecta com app_clinicas, sujeita ao RLS.
Os dados são criados e removidos com a conta de migrations (cnotini).
"""
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL, MIGRATION_DATABASE_URL

# Conexão da aplicação, sujeita ao RLS
engine_app = create_engine(DATABASE_URL)

# Conexão de migrations, dona das tabelas: usada só para preparar e limpar os dados
engine_admin = create_engine(MIGRATION_DATABASE_URL)

# Tabelas com tenant_id, listadas na ordem em que podem ser apagadas (filhas antes das pais)
TABELAS_TENANT = [
    "privacy_requests",
    "consents",
    "handoffs",
    "log_auditoria",
    "jobs",
    "mensagens",
    "conversas",
    "pacientes_contatos",
    "regras_agendamento",
    "profissional_servicos",
    "horarios_trabalho",
    # agendamentos tem FK para profissionais e servicos, entao e apagado antes deles
    "agendamentos",
    "servicos",
    "profissionais",
    "clinicas",
]

# Expressão esperada em USING e WITH CHECK da policy isolamento_tenant, como o
# Postgres a devolve em pg_policies
EXPRESSAO_ISOLAMENTO = "(tenant_id = (current_setting('app.tenant_id'::text))::uuid)"

# Telefone fictício usado em todas as linhas de contato
TELEFONE = "(00) 00000-0000"

def _colunas_minimas(tabela, tenant):
    """Monta as colunas e valores mínimos para inserir uma linha em cada tabela."""
    # Cada tabela tem dependências diferentes; estas são as obrigatórias no schema atual
    base = {"tenant_id": str(tenant)}
    extras = {
        "clinicas": {"nome": "Clinica Intrusa", "ativo": True},
        "profissionais": {"nome": "Profissional Intruso", "ativo": True},
        "servicos": {"nome": "Servico Intruso", "ativo": True},
        "conversas": {"contato_telefone": "(00) 00000-0000", "estado_conversa": "idle", "human_mode": False},
        "pacientes_contatos": {"contato_telefone": "(00) 00000-0000"},
        "mensagens": {"id": f"intruso-{uuid.uuid4()}", "contato_telefone": "(00) 00000-0000", "conteudo": "x", "direcao": "entrada"},
        "jobs": {"type": "SEND_REMINDER", "status": "pending"},
        "log_auditoria": {"acao": "intruso"},
        "consents": {"contato_telefone": "(00) 00000-0000", "tipo": "lembrete", "versao_texto": "v1"},
        "privacy_requests": {"contato_telefone": "(00) 00000-0000", "tipo": "acesso", "status": "aberto"},
        "regras_agendamento": {},
        "profissional_servicos": {"profissional_id": 1, "servico_id": 1},
        "horarios_trabalho": {"profissional_id": 1, "dia_semana": 1, "ativo": True},
        "handoffs": {"conversa_id": 1, "motivo": "urgencia"},
        # Dados validos (fim > inicio, status valido): o unico erro possivel e o RLS
        "agendamentos": {
            "profissional_id": 1, "servico_id": 1,
            "contato_telefone": "(00) 00000-0000",
            "inicio": "2027-01-10 10:00:00+00", "fim": "2027-01-10 10:30:00+00",
            "status": "agendado",
        },
    }
    valores = {**base, **extras.get(tabela, {})}
    nomes = ", ".join(valores.keys())
    marcas = ", ".join(f":{chave}" for chave in valores)
    return {"nomes": nomes, "marcas": marcas, "valores": valores}

def _semear(conexao, tenant):
    """Cria uma linha em cada tabela com tenant_id, para o tenant informado."""
    # Clínica, que é a raiz de todas as demais tabelas
    conexao.execute(
        text("INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (:t, 'Clinica Teste', true)"),
        {"t": str(tenant)},
    )
    # Profissional e serviço, usados nas tabelas de agenda
    profissional = conexao.execute(
        text("INSERT INTO profissionais (tenant_id, nome, ativo) VALUES (:t, 'Profissional Exemplo', true) RETURNING id"),
        {"t": str(tenant)},
    ).scalar()
    servico = conexao.execute(
        text("INSERT INTO servicos (tenant_id, nome, ativo) VALUES (:t, 'Servico Exemplo', true) RETURNING id"),
        {"t": str(tenant)},
    ).scalar()
    # Conversa, usada por handoffs
    conversa = conexao.execute(
        text(
            "INSERT INTO conversas (tenant_id, contato_telefone, estado_conversa, human_mode) "
            "VALUES (:t, :tel, 'idle', false) RETURNING id"
        ),
        {"t": str(tenant), "tel": TELEFONE},
    ).scalar()
    # Tabelas de agenda ligadas ao profissional e ao serviço
    conexao.execute(
        text("INSERT INTO horarios_trabalho (tenant_id, profissional_id, dia_semana, ativo) VALUES (:t, :p, 1, true)"),
        {"t": str(tenant), "p": profissional},
    )
    conexao.execute(
        text("INSERT INTO profissional_servicos (tenant_id, profissional_id, servico_id) VALUES (:t, :p, :s)"),
        {"t": str(tenant), "p": profissional, "s": servico},
    )
    # Um agendamento ativo por tenant, sem sobreposicao (linha unica por tenant)
    conexao.execute(
        text(
            "INSERT INTO agendamentos (tenant_id, profissional_id, servico_id, "
            "contato_telefone, inicio, fim, status) "
            "VALUES (:t, :p, :s, :tel, :ini, :fim, 'agendado')"
        ),
        {
            "t": str(tenant), "p": profissional, "s": servico, "tel": TELEFONE,
            "ini": "2027-01-10 10:00:00+00", "fim": "2027-01-10 10:30:00+00",
        },
    )
    conexao.execute(
        text(
            "INSERT INTO regras_agendamento (tenant_id, antecedencia_minima_horas, "
            "antecedencia_maxima_dias, janela_cancelamento_horas) VALUES (:t, 2, 60, 48)"
        ),
        {"t": str(tenant)},
    )
    # Tabelas de contato e de conversa
    conexao.execute(
        text("INSERT INTO pacientes_contatos (tenant_id, contato_telefone, nome) VALUES (:t, :tel, 'Paciente Exemplo')"),
        {"t": str(tenant), "tel": TELEFONE},
    )
    conexao.execute(
        text(
            "INSERT INTO mensagens (id, tenant_id, contato_telefone, conteudo, direcao) "
            "VALUES (:id, :t, :tel, 'Mensagem exemplo', 'entrada')"
        ),
        {"id": f"msg-{tenant}", "t": str(tenant), "tel": TELEFONE},
    )
    conexao.execute(
        text("INSERT INTO jobs (tenant_id, type, status) VALUES (:t, 'SEND_REMINDER', 'pending')"),
        {"t": str(tenant)},
    )
    conexao.execute(
        text("INSERT INTO log_auditoria (tenant_id, acao) VALUES (:t, 'teste_isolamento')"),
        {"t": str(tenant)},
    )
    conexao.execute(
        text("INSERT INTO handoffs (tenant_id, conversa_id, motivo) VALUES (:t, :c, 'urgencia')"),
        {"t": str(tenant), "c": conversa},
    )
    # Consentimento e pedido de privacidade
    conexao.execute(
        text(
            "INSERT INTO consents (tenant_id, contato_telefone, tipo, versao_texto, canal) "
            "VALUES (:t, :tel, 'lembrete', 'v1', 'whatsapp')"
        ),
        {"t": str(tenant), "tel": TELEFONE},
    )
    conexao.execute(
        text(
            "INSERT INTO privacy_requests (tenant_id, contato_telefone, tipo, status) "
            "VALUES (:t, :tel, 'acesso', 'aberto')"
        ),
        {"t": str(tenant), "tel": TELEFONE},
    )


@pytest.fixture(scope="module")
def tenants():
    """Cria dois tenants com dados em todas as tabelas e remove tudo ao final."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    with engine_admin.begin() as conexao:
        _semear(conexao, tenant_a)
        _semear(conexao, tenant_b)
    yield tenant_a, tenant_b
    # Limpeza na ordem das filhas para as pais
    with engine_admin.begin() as conexao:
        for tabela in TABELAS_TENANT:
            conexao.execute(
                text(f"DELETE FROM {tabela} WHERE tenant_id IN (:a, :b)"),
                {"a": str(tenant_a), "b": str(tenant_b)},
            )


def _contar_como(tenant, tabela, condicao="", params=None):
    """Conta linhas da tabela vistas por uma sessão com o tenant informado."""
    with engine_app.begin() as conexao:
        # Define o tenant só para esta transação, como o código da aplicação faria
        conexao.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        return conexao.execute(text(f"SELECT COUNT(*) FROM {tabela} {condicao}"), params or {}).scalar()


def _contar_sem_tenant(tabela):
    """Tenta contar linhas sem definir nenhum tenant na sessão."""
    with engine_app.begin() as conexao:
        return conexao.execute(text(f"SELECT COUNT(*) FROM {tabela}")).scalar()


@pytest.mark.parametrize("tabela", TABELAS_TENANT)
def test_leitura_mostra_so_o_proprio_tenant(tabela, tenants):
    """Com o tenant A, só aparecem linhas de A, e A enxerga a própria linha."""
    tenant_a, tenant_b = tenants
    proprias = _contar_como(tenant_a, tabela, "WHERE tenant_id = :t", {"t": str(tenant_a)})
    # Controle: sem isso, o teste passaria mesmo com a tabela vazia
    assert proprias >= 1
    total_visivel = _contar_como(tenant_a, tabela)
    # Isolamento: o total visível é igual ao que pertence a A, sem nenhuma linha de B
    assert total_visivel == proprias
    assert _contar_como(tenant_a, tabela, "WHERE tenant_id = :t", {"t": str(tenant_b)}) == 0


@pytest.mark.parametrize("tabela", TABELAS_TENANT)
def test_leitura_sem_tenant_e_bloqueada(tabela, tenants):
    """Sem tenant definido na sessão, a consulta deve falhar, e não listar linhas."""
    with pytest.raises(DBAPIError):
        _contar_sem_tenant(tabela)


@pytest.mark.parametrize("tabela", TABELAS_TENANT)
def test_escrita_para_outro_tenant_e_bloqueada(tabela, tenants):
    """Inserir linha com tenant_id de outra clínica deve ser rejeitado pela WITH CHECK."""
    tenant_a, tenant_b = tenants
    # Em clinicas, o tenant_id é a própria identidade: a escrita cruzada é criar uma clínica nova
    # com um UUID que não existe, para o único erro possível ser o RLS
    tenant_alvo = uuid.uuid4() if tabela == "clinicas" else tenant_b
    colunas = _colunas_minimas(tabela, tenant_alvo)
    with engine_app.connect() as conexao:
        transacao = conexao.begin()
        try:
            conexao.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_a)})
            with pytest.raises(DBAPIError, match="row-level security"):
                conexao.execute(
                    text(f"INSERT INTO {tabela} ({colunas['nomes']}) VALUES ({colunas['marcas']})"),
                    colunas["valores"],
                )
        finally:
            transacao.rollback()


@pytest.mark.parametrize("tabela", TABELAS_TENANT)
def test_alteracao_e_exclusao_de_outro_tenant_nao_afetam_linhas(tabela, tenants):
    """Com o tenant A, UPDATE e DELETE sobre linhas de B não podem atingir nada."""
    tenant_a, tenant_b = tenants
    # Conexão com rollback no fim, para o teste não alterar os dados mesmo se falhar
    with engine_app.connect() as conexao:
        transacao = conexao.begin()
        conexao.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_a)})
        atualizadas = conexao.execute(
            text(f"UPDATE {tabela} SET tenant_id = tenant_id WHERE tenant_id = :b"),
            {"b": str(tenant_b)},
        ).rowcount
        apagadas = conexao.execute(
            text(f"DELETE FROM {tabela} WHERE tenant_id = :b"),
            {"b": str(tenant_b)},
        ).rowcount
        transacao.rollback()
    assert atualizadas == 0
    assert apagadas == 0


# --- app.tenant_id vazio (ADR 0011) ------------------------------------------------
#
# Um set_config(..., true) vale so ate o fim da transacao. Depois dela, na mesma
# conexao do pool, o setting fica '' em vez de sumir. A garantia e que essa conexao
# nao ve, cria, altera nem apaga linha de nenhuma clinica. O codigo de erro (22P02 no
# cast ''::uuid) depende do plano da consulta, entao e registrado, nao afirmado.

# So estas barreiras contam. Qualquer outro erro (FK, unicidade, NOT NULL) falha o
# teste, porque poderia esconder uma policy que deixou a escrita passar. O 42501 serve
# ao RLS e a falta de grant: a mensagem separa os dois. Com grant, a policy nem chegou
# a ser exercitada, e o teste so registra.
_POLICY_22P02 = "policy (22P02)"
_POLICY_RLS = "policy (42501, row-level security)"
_GRANT = "grant (42501)"
_NENHUMA_LINHA = "policy (nenhuma linha)"


@contextmanager
def _conexao_com_setting_vazio(tenant):
    """Conexao app_clinicas cujo app.tenant_id ficou '' depois de uma transacao."""
    engine = create_engine(DATABASE_URL, poolclass=NullPool)
    try:
        with engine.connect() as conexao:
            with conexao.begin():
                conexao.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)}
                )
            vazio = conexao.execute(text("SELECT current_setting('app.tenant_id')")).scalar()
            conexao.rollback()
            # Sem isto o teste estaria exercitando o setting ausente, e nao o vazio
            assert vazio == "", f"setting esperado vazio, veio {vazio!r}"
            yield conexao
    finally:
        engine.dispose()


def _executar_e_confirmar(conexao, sql, params):
    """Executa e confirma a transacao. Devolve (linhas ou rowcount, erro do banco)."""
    try:
        with conexao.begin():
            resultado = conexao.execute(text(sql), params)
            return (resultado.all() if resultado.returns_rows else resultado.rowcount), None
    except DBAPIError as erro:
        return None, erro


def _barreira(erro, efeito_nulo):
    """Qual barreira impediu a operacao. None quando nada impediu ou o erro nao conta."""
    if erro is None:
        return _NENHUMA_LINHA if efeito_nulo else None
    codigo = getattr(erro.orig, "pgcode", None)
    if codigo == "22P02":
        return _POLICY_22P02
    if codigo == "42501":
        return _POLICY_RLS if "row-level security" in str(erro.orig) else _GRANT
    return None


def _registrar_barreira(request, erro, efeito_nulo):
    """Guarda a barreira no relatorio (junitxml). O codigo e registrado, nao afirmado."""
    barreira = _barreira(erro, efeito_nulo)
    codigo = getattr(getattr(erro, "orig", None), "pgcode", None)
    request.node.user_properties.append(("barreira", barreira or f"nao aceita ({codigo})"))
    return barreira


def _controle_de_dados(tenants, tabela):
    """Sem linhas das duas clinicas, 'nenhuma linha' passaria por tabela vazia."""
    contagens = tuple(_contar_como(tenant, tabela) for tenant in tenants)
    assert min(contagens) >= 1, contagens
    return contagens


def _ab(tenants):
    return {"a": str(tenants[0]), "b": str(tenants[1])}


@pytest.mark.parametrize("tabela", TABELAS_TENANT)
def test_setting_vazio_select_nao_devolve_linhas(tabela, tenants, request):
    _controle_de_dados(tenants, tabela)
    with _conexao_com_setting_vazio(tenants[0]) as conexao:
        linhas, erro = _executar_e_confirmar(conexao, f"SELECT tenant_id FROM {tabela}", {})
    assert _registrar_barreira(request, erro, linhas == []), (linhas, erro)


@pytest.mark.parametrize("tabela", TABELAS_TENANT)
def test_setting_vazio_insert_nao_cria_linha(tabela, tenants, request):
    tenant_a, tenant_b = tenants
    # Em clinicas, o tenant_id e a propria identidade: o alvo e um UUID novo
    alvo = uuid.uuid4() if tabela == "clinicas" else tenant_b
    colunas = _colunas_minimas(tabela, alvo)
    antes = _contar_como(alvo, tabela)
    criadas, erro = None, None
    try:
        with _conexao_com_setting_vazio(tenant_a) as conexao:
            criadas, erro = _executar_e_confirmar(
                conexao,
                f"INSERT INTO {tabela} ({colunas['nomes']}) VALUES ({colunas['marcas']}) "
                "RETURNING ctid::text",
                colunas["valores"],
            )
    finally:
        # Se a policy falhar e a linha for criada, ela sai pela conta de administracao
        if criadas:
            with engine_admin.begin() as conexao:
                for (ctid,) in criadas:
                    conexao.execute(
                        text(f"DELETE FROM {tabela} WHERE ctid = CAST(:c AS tid)"),
                        {"c": ctid},
                    )
    barreira = _registrar_barreira(request, erro, False)
    assert not criadas, f"linha criada com setting vazio: {criadas}"
    assert barreira, f"barrado por erro que nao e a policy: {erro}"
    assert _contar_como(alvo, tabela) == antes


@pytest.mark.parametrize("tabela", TABELAS_TENANT)
def test_setting_vazio_update_nao_altera_linhas(tabela, tenants, request):
    _controle_de_dados(tenants, tabela)
    with _conexao_com_setting_vazio(tenants[0]) as conexao:
        alteradas, erro = _executar_e_confirmar(
            conexao,
            f"UPDATE {tabela} SET tenant_id = tenant_id WHERE tenant_id IN (:a, :b)",
            _ab(tenants),
        )
    assert _registrar_barreira(request, erro, alteradas == 0), (alteradas, erro)


@pytest.mark.parametrize("tabela", TABELAS_TENANT)
def test_setting_vazio_delete_nao_apaga_linhas(tabela, tenants, request):
    tenant_a, tenant_b = tenants
    antes = _controle_de_dados(tenants, tabela)
    with _conexao_com_setting_vazio(tenant_a) as conexao:
        apagadas, erro = _executar_e_confirmar(
            conexao,
            f"DELETE FROM {tabela} WHERE tenant_id IN (:a, :b)",
            _ab(tenants),
        )
    assert _registrar_barreira(request, erro, apagadas == 0), (apagadas, erro)
    assert (_contar_como(tenant_a, tabela), _contar_como(tenant_b, tabela)) == antes

def _problemas_de_cobertura_rls():
    """Confere no catálogo cada tabela de public com coluna tenant_id.

    Lê o catálogo com app_clinicas, a mesma conta dos demais testes de isolamento.
    Devolve a lista de problemas encontrados, vazia quando tudo está coberto.
    """
    with engine_app.connect() as conexao:
        tabelas = conexao.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_attribute a ON a.attrelid = c.oid "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
                "AND a.attname = 'tenant_id' AND NOT a.attisdropped "
                "ORDER BY c.relname"
            )
        ).fetchall()
        policies = conexao.execute(
            text(
                "SELECT tablename, policyname, permissive, cmd, qual, with_check "
                "FROM pg_policies WHERE schemaname = 'public'"
            )
        ).fetchall()

    problemas = []
    nomes_no_catalogo = {tabela.relname for tabela in tabelas}
    for tabela in tabelas:
        nome = tabela.relname
        if not tabela.relrowsecurity:
            problemas.append(f"{nome}: RLS desligado")
        if not tabela.relforcerowsecurity:
            problemas.append(f"{nome}: sem FORCE ROW LEVEL SECURITY")
        if nome not in TABELAS_TENANT:
            problemas.append(f"{nome}: fora de TABELAS_TENANT")
        da_tabela = [p for p in policies if p.tablename == nome]
        isolamento = [p for p in da_tabela if p.policyname == "isolamento_tenant"]
        if not isolamento:
            problemas.append(f"{nome}: sem policy isolamento_tenant")
            continue
        policy = isolamento[0]
        if policy.cmd != "ALL":
            problemas.append(f"{nome}: isolamento_tenant não vale para todos os comandos")
        if policy.qual != EXPRESSAO_ISOLAMENTO:
            problemas.append(f"{nome}: USING inesperado em isolamento_tenant")
        if policy.with_check != EXPRESSAO_ISOLAMENTO:
            problemas.append(f"{nome}: WITH CHECK inesperado em isolamento_tenant")
        # Policies permissivas se somam por OR: outra policy alargaria o acesso
        permissivas = [p for p in da_tabela if p.permissive == "PERMISSIVE"]
        if len(permissivas) != 1:
            problemas.append(f"{nome}: {len(permissivas)} policies permissivas, esperada 1")
    for nome in TABELAS_TENANT:
        if nome not in nomes_no_catalogo:
            problemas.append(f"{nome}: está em TABELAS_TENANT e não existe com tenant_id")
    return problemas


def test_toda_tabela_com_tenant_id_esta_coberta_pelo_rls():
    """Regra 20 do CLAUDE.md, verificada pelo catálogo e não por uma lista manual."""
    assert _problemas_de_cobertura_rls() == []


def _fks_entre_clinicas_sem_tenant():
    """FKs de uma tabela com tenant_id para outra tabela com tenant_id sem o par tenant_id.

    A verificação de FK ignora o RLS, então a FK precisa incluir tenant_id nos dois
    lados, na mesma posição (ADR 0007). A FK para clinicas.tenant_id é a própria
    clínica e fica de fora.
    """
    with engine_app.connect() as conexao:
        fks = conexao.execute(
            text(
                "SELECT c.conname, c.conrelid::regclass::text AS filha, "
                "c.confrelid::regclass::text AS pai, "
                "ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(n, i) "
                "      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n "
                "      ORDER BY k.i)::text[] AS colunas, "
                "ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(n, i) "
                "      JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.n "
                "      ORDER BY k.i)::text[] AS referenciadas "
                "FROM pg_constraint c "
                "WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace "
                "ORDER BY c.conname"
            )
        ).fetchall()
        com_tenant = {
            linha.table_name
            for linha in conexao.execute(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = 'tenant_id'"
                )
            )
        }

    problemas = []
    for fk in fks:
        if fk.filha not in com_tenant or fk.pai not in com_tenant:
            continue
        if fk.pai == "clinicas" and fk.referenciadas == ["tenant_id"]:
            continue
        pares = list(zip(fk.colunas, fk.referenciadas))
        if ("tenant_id", "tenant_id") not in pares:
            problemas.append(f"{fk.conname}: {fk.filha} -> {fk.pai} sem tenant_id")
    return problemas


def test_fk_entre_tabelas_de_clinica_inclui_tenant_id():
    """ADR 0007: nenhuma FK entre tabelas de clínica referencia só o id."""
    assert _fks_entre_clinicas_sem_tenant() == []
