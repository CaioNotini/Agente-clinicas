"""Entrada do canal CLI (item B12 do plano). Sem banco: gravar_e_enfileirar e trocado."""
import io
import uuid

import pytest

from app.channels import cli
from app.jobs.queue import ColisaoIdEntreTenants, ResultadoEnfileiramento

TENANT = str(uuid.uuid4())
TELEFONE = "(11) 90000-0000"


def test_tenant_que_nao_e_uuid_encerra_com_mensagem_de_uso(monkeypatch, capsys):
    def nao_pode_gravar(mensagem):
        raise AssertionError("gravou com tenant invalido")

    monkeypatch.setattr(cli, "gravar_e_enfileirar", nao_pode_gravar)
    monkeypatch.setattr("sys.stdin", io.StringIO("oi\n"))

    with pytest.raises(SystemExit) as saida:
        cli.main(["--tenant", "abc", "--telefone", TELEFONE])

    assert saida.value.code == 2
    assert "--tenant" in capsys.readouterr().err


def test_colisao_de_id_avisa_e_continua_com_a_proxima_mensagem(monkeypatch, capsys):
    chamadas = []

    def gravar(mensagem):
        chamadas.append(mensagem.conteudo)
        if len(chamadas) == 1:
            raise ColisaoIdEntreTenants("id ja existe em outro tenant")
        return ResultadoEnfileiramento(duplicada=False, job_id=7)

    monkeypatch.setattr(cli, "gravar_e_enfileirar", gravar)
    monkeypatch.setattr("sys.stdin", io.StringIO("primeira\nsegunda\n"))

    cli.main(["--tenant", TENANT, "--telefone", TELEFONE])

    saida = capsys.readouterr().out
    assert chamadas == ["primeira", "segunda"]
    assert "nao gravada" in saida
    # O texto da excecao nao vai ao contato
    assert "outro tenant" not in saida
    assert "recebido e enfileirado: job 7" in saida
