"""Validação da config do LLM (etapa 6.1). Lê LLM_MODEL e ANTHROPIC_API_KEY só na chamada.

Sem API e sem banco. Valores fictícios. A validação não roda no import de app.config,
então importar o módulo sem essas variáveis continua funcionando (ADR 0010).
"""
import pytest

from app.config import MAX_TOKENS_PADRAO, ler_config_llm
from app.llm.base import ConfigLLM


def _definir(monkeypatch, modelo, chave):
    for nome, valor in (("LLM_MODEL", modelo), ("ANTHROPIC_API_KEY", chave)):
        if valor is None:
            monkeypatch.delenv(nome, raising=False)
        else:
            monkeypatch.setenv(nome, valor)


def test_sucesso_devolve_config_e_chave(monkeypatch):
    _definir(monkeypatch, "claude-haiku-teste", "chave-ficticia")
    config, chave = ler_config_llm()
    assert isinstance(config, ConfigLLM)
    assert config.modelo == "claude-haiku-teste"
    assert config.max_tokens == MAX_TOKENS_PADRAO
    assert config.esforco is None
    assert chave == "chave-ficticia"


@pytest.mark.parametrize(
    "modelo, chave, ausente",
    [
        (None, "chave-ficticia", "LLM_MODEL"),
        ("modelo", None, "ANTHROPIC_API_KEY"),
    ],
)
def test_variavel_ausente_levanta_runtimeerror(monkeypatch, modelo, chave, ausente):
    _definir(monkeypatch, modelo, chave)
    with pytest.raises(RuntimeError) as erro:
        ler_config_llm()
    assert ausente in str(erro.value)


def test_as_duas_ausentes_aparecem_na_mensagem(monkeypatch):
    _definir(monkeypatch, None, None)
    with pytest.raises(RuntimeError) as erro:
        ler_config_llm()
    mensagem = str(erro.value)
    assert "LLM_MODEL" in mensagem
    assert "ANTHROPIC_API_KEY" in mensagem
