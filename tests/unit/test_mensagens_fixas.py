"""Mensagens fixas de urgencia e clinico_bloqueado, e texto de handoff (ADR 0009).

A de urgencia orienta 192 / pronto-socorro de forma incondicional e nunca usa o
texto de handoff. O texto de handoff ao paciente tem um padrao neutro, e o prazo
so aparece quando a clinica o informa. Um teste de charset barra caracteres fora
do alfabeto latino, porque um caractere cirilico parecido ja passou despercebido.
"""
from app.mensagens.fixas import (
    HANDOFF_TEXTO_PACIENTE_PADRAO,
    MENSAGEM_CLINICO_BLOQUEADO,
    MENSAGEM_URGENCIA,
    MENSAGENS_FIXAS,
    contem_apenas_latino,
    montar_texto_handoff_paciente,
)

# --- charset ------------------------------------------------------------------


def test_contem_apenas_latino_aceita_portugues_acentuado():
    assert contem_apenas_latino("Olá, até às 9h. Ligue 192!")


def test_contem_apenas_latino_rejeita_cirilico():
    # "isto" com "т" e "о" cirilicos, visualmente identicos aos latinos
    assert not contem_apenas_latino("isто")


def test_mensagens_fixas_nao_tem_caractere_fora_do_alfabeto_latino():
    for nome, texto in MENSAGENS_FIXAS.items():
        assert contem_apenas_latino(texto), f"{nome} tem caractere nao latino"


# --- urgencia -----------------------------------------------------------------


def test_urgencia_orienta_servico_de_emergencia():
    assert "192" in MENSAGEM_URGENCIA


def test_urgencia_nao_depende_nem_cita_handoff():
    texto = MENSAGEM_URGENCIA.lower()
    assert "recep" not in texto
    # A urgencia nunca usa o texto de handoff ao paciente
    assert HANDOFF_TEXTO_PACIENTE_PADRAO not in MENSAGEM_URGENCIA


# --- clinico_bloqueado --------------------------------------------------------


def test_clinico_bloqueado_nao_promete_recepcao():
    assert "recep" not in MENSAGEM_CLINICO_BLOQUEADO.lower()


# --- texto de handoff ao paciente ---------------------------------------------


def test_handoff_usa_texto_padrao_quando_clinica_nao_preenche():
    assert montar_texto_handoff_paciente(None, None) == HANDOFF_TEXTO_PACIENTE_PADRAO


def test_handoff_usa_texto_da_clinica_quando_preenchido():
    texto = "A gente te retorna em breve."
    assert montar_texto_handoff_paciente(texto, None) == texto


def test_handoff_informa_prazo_quando_a_clinica_define():
    saida = montar_texto_handoff_paciente(None, 120)
    assert "120" in saida


def test_handoff_nao_informa_prazo_quando_nulo():
    saida = montar_texto_handoff_paciente(None, None)
    assert "prazo" not in saida.lower()
