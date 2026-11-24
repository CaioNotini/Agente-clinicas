"""Migrations rodadas num banco temporario do mesmo cluster.

Cada teste cria um banco vazio, roda o Alembic nele em subprocesso (DB_NAME
trocado no ambiente) e apaga o banco no fim. O banco dos outros testes nao e
tocado. Roles valem para o cluster inteiro, entao as roles criadas pelo banco
principal ja existem quando as migrations rodam no banco temporario.

Limite: descer abaixo da c77398abee4a no banco temporario falharia, porque o
downgrade apaga worker_jobs e ela tem grants no banco principal. Por isso estes
testes nao descem ate a base. O ciclo completo roda na CI, num banco unico.

Usa a conta de migrations (cnotini) para criar e apagar o banco, como o Alembic.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import MIGRATION_DATABASE_URL

RAIZ = Path(__file__).resolve().parents[2]

engine_admin = create_engine(MIGRATION_DATABASE_URL, isolation_level="AUTOCOMMIT")


@pytest.fixture
def banco_temporario():
    nome = f"agente_migr_{uuid.uuid4().hex[:8]}"
    with engine_admin.connect() as conexao:
        conexao.execute(text(f'CREATE DATABASE "{nome}"'))
    try:
        yield nome
    finally:
        with engine_admin.connect() as conexao:
            conexao.execute(text(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)'))


def _alembic(banco, *argumentos):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *argumentos],
        cwd=RAIZ,
        env={**os.environ, "DB_NAME": banco},
        capture_output=True,
        text=True,
        timeout=180,
    )


def _head():
    """Head unico da cadeia de migrations, lido do proprio Alembic."""
    return ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini"))).get_current_head()


def _consultar(banco, sql, parametros=None):
    url = make_url(MIGRATION_DATABASE_URL).set(database=banco)
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conexao:
            return conexao.execute(text(sql), parametros or {}).fetchall()
    finally:
        engine.dispose()


@pytest.mark.timeout(240)
def test_upgrade_head_num_segundo_banco_do_mesmo_cluster(banco_temporario):
    """B3: com as roles ja criadas por outro banco, o upgrade nao falha no CREATE ROLE."""
    resultado = _alembic(banco_temporario, "upgrade", "head")

    assert resultado.returncode == 0, resultado.stderr[-2000:]
    versao = _consultar(banco_temporario, "SELECT version_num FROM alembic_version")
    assert versao == [(_head(),)]
    # A troca de scheduler_service por worker_jobs continua valendo no cluster
    roles = _consultar(
        banco_temporario,
        "SELECT rolname FROM pg_roles WHERE rolname IN ('scheduler_service', 'worker_jobs')",
    )
    assert roles == [("worker_jobs",)]


def _constraints_de_mensagens(banco):
    return _consultar(
        banco,
        "SELECT conname, contype FROM pg_constraint "
        "WHERE conrelid = 'mensagens'::regclass AND contype IN ('p', 'u') "
        "ORDER BY conname",
    )


HEAD_MENSAGENS = [("mensagens_pkey", "p"), ("uq_mensagens_tenant_id_id", "u")]


@pytest.mark.timeout(240)
def test_downgrade_de_mensagens_volta_ao_estado_original(banco_temporario):
    """A6: cada downgrade devolve mensagens.id ao estado que a migration encontrou.

    Estados esperados: depois da c77398abee4a, uma PK chamada pk_mensagens (nome
    dado pela d109eb356688). Depois da 1bc74598f301, nenhuma PK, porque ela
    removeu a unica. Depois da 7e9ab495716d, a PK mensagens_pkey. No head, a
    c3d8e5a1f297 (tarefa 5.4) soma a UNIQUE (tenant_id, id), alvo da FK composta de
    handoffs.mensagem_id.
    """
    resultado = _alembic(banco_temporario, "upgrade", "head")
    assert resultado.returncode == 0, resultado.stderr[-2000:]
    assert _constraints_de_mensagens(banco_temporario) == HEAD_MENSAGENS

    # Desfaz a 7e9ab495716d: volta ao estado sem PK deixado pela 1bc74598f301
    resultado = _alembic(banco_temporario, "downgrade", "9d01c00e9d65")
    assert resultado.returncode == 0, resultado.stderr[-2000:]
    assert _constraints_de_mensagens(banco_temporario) == []

    # Desfaz a 1bc74598f301: volta a PK pk_mensagens, sem UNIQUE extra
    resultado = _alembic(banco_temporario, "downgrade", "c77398abee4a")
    assert resultado.returncode == 0, resultado.stderr[-2000:]
    assert _constraints_de_mensagens(banco_temporario) == [("pk_mensagens", "p")]

    resultado = _alembic(banco_temporario, "upgrade", "head")
    assert resultado.returncode == 0, resultado.stderr[-2000:]
    assert _constraints_de_mensagens(banco_temporario) == HEAD_MENSAGENS
