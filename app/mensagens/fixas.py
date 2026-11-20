"""Mensagens fixas de urgencia e clinico_bloqueado, e texto de handoff (ADR 0009).

A de urgencia orienta 192 / pronto-socorro de forma incondicional e nunca usa o
texto de handoff da clinica. O texto de handoff ao paciente tem um padrao neutro, e
o prazo so aparece quando a clinica o informa.

contem_apenas_latino barra caractere fora do alfabeto latino, porque um caractere
cirilico visualmente identico ja passou despercebido numa revisao. As mensagens
fixas ainda passam por revisao clinica antes do piloto (etapa 20).
"""
import unicodedata
from typing import Optional

MENSAGEM_URGENCIA = (
    "Se isto for uma emergência, ligue 192 (SAMU) ou procure o pronto-socorro "
    "mais próximo agora. Este canal não faz atendimento de urgência."
)

MENSAGEM_CLINICO_BLOQUEADO = (
    "Essa é uma pergunta que só a equipe da clínica pode responder com segurança. "
    "Vou registrar seu contato para que o responsável pelo atendimento retorne."
)

HANDOFF_TEXTO_PACIENTE_PADRAO = (
    "Vou encaminhar seu atendimento para uma pessoa da equipe. "
    "Em breve você recebe um retorno por aqui."
)

# Textos fixos cobertos pelo teste de charset
MENSAGENS_FIXAS = {
    "MENSAGEM_URGENCIA": MENSAGEM_URGENCIA,
    "MENSAGEM_CLINICO_BLOQUEADO": MENSAGEM_CLINICO_BLOQUEADO,
    "HANDOFF_TEXTO_PACIENTE_PADRAO": HANDOFF_TEXTO_PACIENTE_PADRAO,
}


def contem_apenas_latino(texto: str) -> bool:
    """True se toda letra de texto for do alfabeto latino.

    Pontuacao, digitos e espacos sao ignorados. Letras acentuadas do portugues
    continuam validas, porque sao do script latino. Uma letra cirilica ou grega
    reprova.
    """
    for caractere in texto:
        if caractere.isalpha() and not unicodedata.name(caractere, "").startswith(
            "LATIN"
        ):
            return False
    return True


def montar_texto_handoff_paciente(
    texto_clinica: Optional[str], prazo_minutos: Optional[int]
) -> str:
    """Texto informado ao paciente quando um handoff e aberto.

    Usa o texto da clinica, ou o padrao neutro quando ela nao preenche. O prazo so
    entra quando a clinica o define (prazo_minutos nao nulo).
    """
    base = texto_clinica if texto_clinica else HANDOFF_TEXTO_PACIENTE_PADRAO
    if prazo_minutos is None:
        return base
    return f"{base} O prazo de resposta é de até {prazo_minutos} minutos."
