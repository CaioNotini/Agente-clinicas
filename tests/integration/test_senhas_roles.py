"""Senhas das roles automatizadas definidas pelo script (ADR 0006).

Um banco novo deve ficar utilizavel sem ALTER ROLE manual: o script
scripts/definir_senhas.py le as senhas das variaveis de ambiente e as aplica em
app_clinicas e worker_jobs. As senhas nunca sao impressas, nem pelo script nem
pelas mensagens de falha destes testes.

O ALTER ROLE de preparo e de restauracao usa a conta de administracao (cnotini).
A verificacao do login usa a propria role, como a aplicacao e o worker fazem.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL, MIGRATION_DATABASE_URL, WORKER_DATABASE_URL

RAIZ = Path(__file__).resolve().parents[2]

engine_admin = create_engine(MIGRATION_DATABASE_URL)

ROLES = [
    pytest.param("app_clinicas", "APP_DB_PASSWORD", DATABASE_URL, id="app_clinicas"),
    pytest.param("worker_jobs", "WORKER_DB_PASSWORD", WORKER_DATABASE_URL, id="worker_jobs"),
]


def _rodar_script(**sobrescritas):
    ambiente = {**os.environ, **sobrescritas}
    return subprocess.run(
        [sys.executable, "-m", "scripts.definir_senhas"],
        cwd=RAIZ,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _alterar_senha(role, senha):
    """ALTER ROLE pela conta de administracao. senha=None remove a senha."""
    conexao = engine_admin.raw_connection()
    try:
        with conexao.cursor() as cursor:
            valor = sql.SQL("NULL") if senha is None else sql.Literal(senha)
            cursor.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(role), valor)
            )
        conexao.commit()
    finally:
        conexao.close()


def _consegue_logar(url):
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False
    finally:
        engine.dispose()


def _vazou_senha(resultado):
    saida = resultado.stdout + resultado.stderr
    return any(
        os.environ[nome] in saida for nome in ("APP_DB_PASSWORD", "WORKER_DB_PASSWORD")
    )


@pytest.mark.timeout(120)
@pytest.mark.parametrize("role, var_senha, url", ROLES)
def test_script_devolve_o_login_a_role_sem_senha(role, var_senha, url):
    """Prova do problema: sem senha a role nao loga. O script resolve sem ALTER manual."""
    try:
        _alterar_senha(role, None)
        assert not _consegue_logar(url), "a role ainda loga sem senha"

        resultado = _rodar_script()

        assert resultado.returncode == 0, resultado.stderr
        vazou = _vazou_senha(resultado)
        assert not vazou, "o script imprimiu uma senha"
        assert _consegue_logar(url)
    finally:
        # Restaura pela conta de administracao, mesmo que o script falhe
        _alterar_senha(role, os.environ[var_senha])


@pytest.mark.timeout(120)
@pytest.mark.parametrize(
    "variavel, esperado",
    [("APP_DB_USER", "app_clinicas"), ("WORKER_DB_USER", "worker_jobs")],
)
def test_script_recusa_nome_de_role_inesperado(variavel, esperado):
    """Um .env com outra role, como o superusuario, nao pode ter a senha trocada."""
    resultado = _rodar_script(**{variavel: "cnotini"})

    assert resultado.returncode != 0
    assert f"{variavel} deve ser {esperado}" in resultado.stderr
    vazou = _vazou_senha(resultado)
    assert not vazou, "o script imprimiu uma senha"
    # Nada foi alterado: as tres contas continuam logando com as senhas atuais
    assert _consegue_logar(MIGRATION_DATABASE_URL)
    assert _consegue_logar(DATABASE_URL)
    assert _consegue_logar(WORKER_DATABASE_URL)
