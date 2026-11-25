"""Criacao do cliente LLM: timeout e max_retries fixos no codigo (A8, ADR 0010).

Sem rede e sem chave real: criar o SDK nao faz chamada, e as variaveis sao ficticias,
definidas por monkeypatch. Nenhum teste aqui chama a API (regra 22 do CLAUDE.md).
"""
import re
from pathlib import Path

import pytest

from app.jobs.worker import LIMITE_LOCK_SEGUNDOS
from app.llm import fabrica
from app.llm.anthropic_client import AnthropicClient
from app.llm.fabrica import criar_cliente_llm

RAIZ_APP = Path(__file__).resolve().parents[2] / "app"
ARQUIVO_FABRICA = RAIZ_APP / "llm" / "fabrica.py"


def _definir(monkeypatch, modelo, chave):
    for nome, valor in (("LLM_MODEL", modelo), ("ANTHROPIC_API_KEY", chave)):
        if valor is None:
            monkeypatch.delenv(nome, raising=False)
        else:
            monkeypatch.setenv(nome, valor)


def test_sdk_da_aplicacao_tem_max_retries_zero_e_timeout_de_60_s(monkeypatch):
    _definir(monkeypatch, "claude-haiku-teste", "chave-ficticia")

    cliente = criar_cliente_llm()

    assert isinstance(cliente, AnthropicClient)
    sdk = cliente._sdk  # pylint: disable=protected-access
    assert sdk.max_retries == 0
    assert sdk.timeout.read == 60
    assert sdk.timeout.write == 60
    assert sdk.timeout.pool == 60
    assert sdk.timeout.connect == 5


def test_timeout_menor_que_o_limite_de_orfao_do_job(monkeypatch):
    # Um timeout igual ou maior que o limite deixaria a chamada travada virar orfa e
    # ser paga de novo por outro worker. Vale para cada fase do httpx.
    _definir(monkeypatch, "claude-haiku-teste", "chave-ficticia")

    sdk = criar_cliente_llm()._sdk  # pylint: disable=protected-access

    for fase in (sdk.timeout.connect, sdk.timeout.read, sdk.timeout.write):
        assert fase is not None
        assert fase < LIMITE_LOCK_SEGUNDOS
    assert sdk.timeout.pool < LIMITE_LOCK_SEGUNDOS


@pytest.mark.parametrize(
    "modelo, chave",
    [(None, "chave-ficticia"), ("claude-haiku-teste", None), (None, None)],
)
def test_sem_variavel_nao_cria_o_sdk(monkeypatch, modelo, chave):
    _definir(monkeypatch, modelo, chave)

    def falhar(_chave):
        raise AssertionError("o SDK nao pode ser criado sem configuracao")

    monkeypatch.setattr(fabrica, "criar_sdk_anthropic", falhar)

    with pytest.raises(RuntimeError, match="Variáveis ausentes"):
        criar_cliente_llm()


def test_so_a_fabrica_cria_o_sdk_em_app():
    # Garante que nenhum outro modulo de app/ cria o SDK sem timeout e max_retries.
    padrao = re.compile(r"\b(Async)?Anthropic\s*\(")
    fora_da_fabrica = [
        str(arquivo.relative_to(RAIZ_APP))
        for arquivo in RAIZ_APP.rglob("*.py")
        if arquivo != ARQUIVO_FABRICA
        and padrao.search(arquivo.read_text(encoding="utf-8"))
    ]

    assert not fora_da_fabrica
    assert padrao.search(ARQUIVO_FABRICA.read_text(encoding="utf-8"))
