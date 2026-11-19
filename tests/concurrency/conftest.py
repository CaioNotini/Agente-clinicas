"""Fila de jobs isolada para os testes de concorrencia (item B9 do plano).

reivindicar_job e processar_um capturam qualquer job elegivel da fila, de qualquer
clinica. Um job deixado no banco local, por exemplo pelo CLI, seria capturado no
lugar do job do teste. Antes de cada teste, os jobs pending e processing sao
apagados com a conta de administracao. Jobs done e dead ficam, porque a captura
os ignora.
"""
import pytest
from sqlalchemy import create_engine, text

from app.config import MIGRATION_DATABASE_URL

engine_admin = create_engine(MIGRATION_DATABASE_URL)


@pytest.fixture(autouse=True)
def fila_vazia():
    with engine_admin.begin() as conexao:
        conexao.execute(text("DELETE FROM jobs WHERE status IN ('pending', 'processing')"))
    yield
