"""Conexoes da aplicacao com limite de tempo (item B12 do plano).

Sem connect_timeout, uma conexao com o banco inacessivel fica presa pelo tempo
padrao do sistema operacional. O teste confere os parametros que o engine da
aplicacao passa ao driver de verdade, pelo evento do_connect.
"""
from sqlalchemy import event, text

from app.db import database


def test_engine_da_aplicacao_usa_connect_timeout():
    capturados = {}

    def capturar(dialect, conn_rec, cargs, cparams):
        # So a chave testada: cparams tem a senha, e uma falha mostraria o dicionario
        capturados["connect_timeout"] = cparams.get("connect_timeout")

    event.listen(database.engine, "do_connect", capturar)
    try:
        database.engine.dispose()  # forca uma conexao nova
        with database.engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    finally:
        event.remove(database.engine, "do_connect", capturar)

    timeout = capturados["connect_timeout"]
    assert timeout == database.CONNECT_TIMEOUT_SEGUNDOS


def test_engine_do_worker_usa_connect_timeout():
    from app.jobs import worker

    capturados = {}

    def capturar(dialect, conn_rec, cargs, cparams):
        # So a chave testada: cparams tem a senha, e uma falha mostraria o dicionario
        capturados["connect_timeout"] = cparams.get("connect_timeout")

    event.listen(worker.engine_worker, "do_connect", capturar)
    try:
        worker.engine_worker.dispose()  # forca uma conexao nova
        with worker.engine_worker.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    finally:
        event.remove(worker.engine_worker, "do_connect", capturar)

    timeout = capturados["connect_timeout"]
    assert timeout == database.CONNECT_TIMEOUT_SEGUNDOS
