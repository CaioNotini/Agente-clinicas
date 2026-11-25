"""Testes reais da API da Anthropic que fecham a etapa 6 (criterio de pronto).

Marcador llm_real: excluido por padrao no pytest.ini (-m "not llm_real"). So o
desenvolvedor roda, com `pytest -m llm_real -v`, e a CI nunca roda. As chamadas
reais geram custo; a implementacao e o teste foram aprovados pelo desenvolvedor
(regra 22 do CLAUDE.md).

Sem banco: esta pasta nao tem conftest, entao nenhuma fixture conecta ao Postgres.
O codigo nunca le o .env, so usa os.getenv. tenant_id e um UUID ficticio fixo, do
mesmo tipo (str de UUID) usado no resto do projeto, e so vai ao log.

Ressalvas conhecidas:
- esforco fica None nos testes. O campo nao e enviado a API, entao o claude-haiku-5-5
  usa o esforco padrao medium, com raciocinio adaptativo sempre ligado. Enviar o
  esforco e da etapa 7 (ADR 0010).
- No teste 1, max_tokens e 1024 para o raciocinio adaptativo nao cortar a resposta.
  Se mesmo assim o motivo vier max_tokens, o teste falha com uma mensagem clara.
- No teste 2, o completar nao expoe tool_choice, entao a obrigacao de usar a
  ferramenta vem so do prompt. E confiavel com instrucao clara, mas ha risco pequeno
  de o modelo responder em texto em vez de chamar a ferramenta.
"""
import os
import uuid

import pytest
from structlog.testing import capture_logs

from app.config import ler_config_llm
from app.llm.anthropic_client import AnthropicClient
from app.llm.base import ConfigLLM
from app.llm.erros import ErroLLMPermanente
from app.llm.fabrica import criar_sdk_anthropic

# Pula tudo se faltar ANTHROPIC_API_KEY ou LLM_MODEL, dizendo qual falta.
_FALTANDO = [nome for nome in ("ANTHROPIC_API_KEY", "LLM_MODEL") if not os.getenv(nome)]
pytestmark = [
    pytest.mark.llm_real,
    pytest.mark.skipif(
        bool(_FALTANDO),
        reason=f"variaveis ausentes para o teste real: {', '.join(_FALTANDO)}",
    ),
]

# tenant_id ficticio fixo, do mesmo tipo (str de UUID) usado no resto do projeto.
TENANT_FICTICIO = str(uuid.UUID("11111111-1111-1111-1111-111111111111"))

# Timeout generoso por teste: a chamada real pode demorar. Sobrescreve o global de 10 s.
TIMEOUT_REAL = 60


def _config(max_tokens=1024, modelo=None):
    """ConfigLLM a partir do ambiente, permitindo sobrescrever max_tokens e modelo."""
    config, _ = ler_config_llm()
    return ConfigLLM(
        modelo=modelo or config.modelo, max_tokens=max_tokens, esforco=None
    )


def _cliente_real(config, chave=None):
    """AnthropicClient sobre o SDK real, criado pela fabrica da aplicacao (ADR 0010)."""
    if chave is None:
        _, chave = ler_config_llm()
    return AnthropicClient(criar_sdk_anthropic(chave), config)


@pytest.mark.timeout(TIMEOUT_REAL)
def test_texto_simples():
    """Caminho feliz real: a resposta normalizada e a telemetria no log."""
    config = _config(max_tokens=1024)
    cliente = _cliente_real(config)
    system = "Responda em uma frase curta."
    prompt = "Diga ola para uma clinica ficticia."
    mensagens = [{"role": "user", "content": prompt}]

    with capture_logs() as logs:
        resposta = cliente.completar(
            tenant_id=TENANT_FICTICIO, system=system, mensagens=mensagens
        )

    assert resposta.motivo_parada == "end_turn", (
        f"motivo_parada={resposta.motivo_parada} (tokens_saida={resposta.tokens_saida}); "
        "o raciocinio adaptativo pode ter estourado max_tokens"
    )
    assert resposta.texto.strip() != ""
    assert resposta.tokens_entrada > 0
    assert resposta.tokens_saida > 0
    assert resposta.latencia_ms > 0
    assert resposta.modelo == config.modelo
    assert resposta.id_requisicao and resposta.id_requisicao.startswith("req_")

    eventos = [log for log in logs if log.get("event") == "llm_chamada"]
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento["tenant_id"] == TENANT_FICTICIO
    assert evento["modelo"] == config.modelo
    assert evento["tokens_entrada"] == resposta.tokens_entrada
    assert evento["tokens_saida"] == resposta.tokens_saida
    assert evento["latencia_ms"] == resposta.latencia_ms
    assert evento["motivo_parada"] == "end_turn"
    assert evento["id_requisicao"] == resposta.id_requisicao

    # O prompt e a resposta nunca entram no log.
    blob = repr(logs)
    assert prompt not in blob
    assert resposta.texto not in blob


@pytest.mark.timeout(TIMEOUT_REAL)
def test_chamada_de_ferramenta():
    """Function calling real: motivo tool_use, nome e argumentos como dicionario."""
    config = _config(max_tokens=1024)
    cliente = _cliente_real(config)
    ferramentas = [
        {
            "name": "verificar_disponibilidade",
            "description": "Verifica a disponibilidade de horarios para uma data.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "string",
                        "description": "Data no formato AAAA-MM-DD",
                    }
                },
                "required": ["data"],
            },
        }
    ]
    system = (
        "Use a ferramenta verificar_disponibilidade quando precisar checar horarios."
    )
    mensagens = [
        {
            "role": "user",
            "content": "Verifique a disponibilidade para a data 2026-12-01 usando a ferramenta.",
        }
    ]

    resposta = cliente.completar(
        tenant_id=TENANT_FICTICIO,
        system=system,
        mensagens=mensagens,
        ferramentas=ferramentas,
    )

    assert resposta.motivo_parada == "tool_use"
    assert len(resposta.chamadas_ferramenta) >= 1
    chamada = resposta.chamadas_ferramenta[0]
    assert chamada.nome == "verificar_disponibilidade"
    assert isinstance(chamada.entrada, dict)
    assert "data" in chamada.entrada


@pytest.mark.timeout(TIMEOUT_REAL)
def test_modelo_inexistente_e_erro_permanente():
    """Modelo invalido: erro permanente e llm_chamada_falhou com status 404.

    A requisicao que falha nao e cobrada.
    """
    config = _config(modelo="modelo-inexistente-zzz")
    cliente = _cliente_real(config)

    with capture_logs() as logs:
        with pytest.raises(ErroLLMPermanente):
            cliente.completar(
                tenant_id=TENANT_FICTICIO,
                system="oi",
                mensagens=[{"role": "user", "content": "oi"}],
            )

    eventos = [log for log in logs if log.get("event") == "llm_chamada_falhou"]
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento["status"] == 404
    assert evento.get("id_requisicao", "").startswith("req_")
    assert "tokens_entrada" not in evento
    assert "tokens_saida" not in evento


@pytest.mark.timeout(TIMEOUT_REAL)
def test_chave_invalida_e_erro_permanente():
    """Chave invalida: erro permanente e llm_chamada_falhou com status 401."""
    config = _config()
    cliente = _cliente_real(config, chave="sk-ant-chave-invalida-para-teste")

    with capture_logs() as logs:
        with pytest.raises(ErroLLMPermanente):
            cliente.completar(
                tenant_id=TENANT_FICTICIO,
                system="oi",
                mensagens=[{"role": "user", "content": "oi"}],
            )

    eventos = [log for log in logs if log.get("event") == "llm_chamada_falhou"]
    assert len(eventos) == 1
    assert eventos[0]["status"] == 401
