"""Classificacao por regra, baseline da etapa 7 (tarefa 7.1, ADR 0012).

Funcao pura e rapida, sem banco nem rede, porque tambem serve a verificacao de
urgencia com human_mode ativo e, na etapa 9, a dispensa da espera do agrupamento.
Devolve ResultadoClassificacao com origem regra e confianca vazia.

Como funciona:
1. O texto e normalizado uma vez (minusculas, sem acento, sem pontuacao, espacos
   simples). Todas as expressoes abaixo sao escritas ja nessa forma.
2. Cada categoria tem suas expressoes como dado, no topo do modulo. Para estender a
   regra, acrescente uma expressao na tupla certa e um caso de teste.
3. Urgencia usa so frases fortes e especificas. Quando ela dispara, o LLM nao e
   consultado, entao um falso positivo nao tem correcao (revisao do ADR 0012 na 7.2).
   Palavra solta como "peito", "respirar", "sangue", "desmaio" ou "emergencia" nunca
   basta.
4. clinico_bloqueado combina dois sinais: um termo de saude e, para o subtipo
   pergunta, um pedido de orientacao. Sem pedido de orientacao o subtipo e sintoma,
   que tambem e o padrao do ADR 0012.
5. Quem pede para marcar ("qual especialidade devo marcar", "voces atendem isso")
   esta agendando. Nesse caso o termo de saude sozinho nao cria clinico_bloqueado
   (linha AG-09 do guia). Com pedido de orientacao, o clinico continua.
"""

import re
import unicodedata

from app.classification.resultado import (
    ADMINISTRATIVO,
    AGENDAMENTO,
    CLINICO_BLOQUEADO,
    ORIGEM_REGRA,
    PERGUNTA,
    SINTOMA,
    URGENCIA,
    Intencao,
    ResultadoClassificacao,
)

# --- expressoes, ja no texto normalizado (sem acento, minusculas) ---

# Risco imediato a vida. So frases fortes: alta precisao antes de recall.
_URGENCIA = (
    r"dor (muito )?(forte )?no peito",
    r"aperto no peito",
    r"falta( de)? ar",
    r"(dificil|dificuldade|nao consigo|nao to conseguindo|nao estou conseguindo)"
    r"( de| pra| para)? respirar",
    r"sangrando muito",
    r"sangrando sem parar",
    r"nao para de sangrar",
    r"sangramento (forte|intenso|que nao para)",
    r"desmaiei",
    r"acab\w+ de desmaiar",
    r"perd\w+ (a consciencia|os sentidos)",
    r"desmai\w+ e nao (acorda|acordou)",
    r"overdose",
    r"(muitos|varios|\d{2,}) (comprimidos|remedios) de uma vez",
    r"convuls\w*",
    r"(boca|rosto) (torta|torto|caido|caida)",
    r"nao consigo mexer (o|a|um|uma|meu|minha) (braco|perna|lado)",
    r"(penso|pensando|pensei|vontade|quero|vou) (em )?"
    r"(me machucar|me cortar|me matar|tirar (a )?minha (propria )?vida"
    r"|acabar com (a )?minha vida|morrer)",
    r"suicid\w*",
    r"nao aguento mais viver",
)

# Termo de saude: o assunto da mensagem e o corpo ou um tratamento do paciente.
# "exame" e "sangue" sozinhos nao entram, porque "voces fazem exame de sangue?"
# e administrativo (AD-06).
_SAUDE = (
    r"dor(es)?",
    r"doendo",
    r"doi",
    r"doeu",
    r"remedio(s)?",
    r"medicamento(s)?",
    r"medicacao",
    r"comprimido(s)?",
    r"antibiotico(s)?",
    r"ibuprofeno",
    r"dipirona",
    r"paracetamol",
    r"pomada",
    r"\d+ ?mg",
    r"mg",
    r"dose",
    r"sintoma(s)?",
    r"febre",
    r"inchad[oa]",
    r"inchou",
    r"inchaco",
    r"mancha(s)?",
    r"pinta",
    r"ferida",
    r"coceira",
    r"tosse",
    r"tontura",
    r"tonto",
    r"enjoo",
    r"enxaqueca",
    r"diabetes",
    r"pressao alta",
    r"remedio da pressao",
    r"ansiedade",
    r"depressao",
    r"cancer",
    r"infeccao",
    r"sangrou",
    r"sangrando",
    r"(meu|o) exame deu",
    r"resultado do (meu )?exame",
    r"hemoglobina",
    r"muita sede",
)

# Pedido de orientacao clinica: a pessoa espera uma resposta, nao um horario.
# "devo" sozinho nao entra, porque "qual especialidade devo marcar?" e agendamento.
_ORIENTACAO = (
    r"posso (tomar|usar|beber|comer|misturar|parar|continuar)",
    r"devo (tomar|usar|continuar|parar|procurar|fazer)",
    r"deveria",
    r"tenho que (tomar|parar|continuar)",
    r"preciso (tomar|parar|continuar)",
    r"(isso )?e normal",
    r"e (ruim|grave|perigoso)",
    r"faz mal",
    r"pode ser",
    r"o que (eu )?faco",
    r"o que pode ser",
    r"o que (eu )?tenho",
    r"acha(m)? que (eu )?tenho",
    r"tudo bem",
    r"qual remedio",
    r"quantos mg",
    r"qual (a )?dose",
    r"(voce|vc) tomaria",
    r"seria bom (pra|para)",
)

# Pedido de agendamento explicito. Tambem e o que tira o termo de saude sozinho do
# clinico_bloqueado (AG-09 e AG-09b).
_AGENDAMENTO = (
    r"marcar",
    r"marca",
    r"agendar",
    r"agendamento",
    r"remarcar",
    r"desmarcar",
    r"cancelar",
    r"encaixe",
    r"tem horario",
    r"horario (disponivel|livre|vago)",
    r"quero (uma )?consulta",
    r"qual especialidade",
    r"atendem isso",
    r"atende isso",
    r"com quem (eu )?(marco|agendo|passo)",
    # pedido de consulta com uma especialidade ou profissional ("ver isso com dermato")
    r"com (o |a )?(dermato\w*|ortoped\w*|clinico geral|dentista|doutor|doutora|dr|dra)",
)

_ADMINISTRATIVO = (
    r"funcionamento",
    r"que horas (abre|fecha|voces abrem|voces fecham)",
    r"abre (no|aos|de) sabado",
    r"onde fica",
    r"endereco",
    r"estacionamento",
    r"convenio(s)?",
    r"plano",
    r"aceita(m)?",
    r"particular",
    r"quanto custa",
    r"custa",
    r"valor",
    r"preco",
    r"pagamento",
    r"parcela\w*",
    r"cartao",
    r"pix",
    r"reembolso",
    r"documento(s)?",
    r"preciso levar",
    r"levar na consulta",
    r"voces fazem",
    r"especialidades",
    r"antecedencia",
    r"chegar antes",
    r"emergencia(s)?",
    r"faltar",
)


def _compilar(expressoes):
    # \b nas duas pontas: "dor" nao casa com "dorme", "falta" nao casa com "faltar"
    return re.compile(r"\b(?:" + "|".join(expressoes) + r")\b")


# Termo de saude negado nao conta ("e urgente, mas nao doi", OD-03)
_SAUDE_NEGADA = re.compile(
    r"\b(?:nao (?:doi|doeu|ta doendo|esta doendo)|sem (?:dor|dores|febre))\b"
)

_RE_URGENCIA = _compilar(_URGENCIA)
_RE_SAUDE = _compilar(_SAUDE)
_RE_ORIENTACAO = _compilar(_ORIENTACAO)
_RE_AGENDAMENTO = _compilar(_AGENDAMENTO)
_RE_ADMINISTRATIVO = _compilar(_ADMINISTRATIVO)

_FORA_DE_PALAVRA = re.compile(r"[^a-z0-9]+")


def _normalizar(texto: str) -> str:
    """Minusculas, sem acento, sem pontuacao e com espacos simples."""
    sem_acento = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto.lower())
        if not unicodedata.combining(caractere)
    )
    return _FORA_DE_PALAVRA.sub(" ", sem_acento).strip()


def classificar_por_regra(texto: str) -> ResultadoClassificacao:
    """Rotula o texto com as intencoes que a regra reconhece."""
    if not isinstance(texto, str):
        raise TypeError("classificar_por_regra espera texto (str)")

    normalizado = _normalizar(texto)
    intencoes = []

    if _RE_URGENCIA.search(normalizado):
        intencoes.append(Intencao(URGENCIA))

    pede_orientacao = bool(_RE_ORIENTACAO.search(normalizado))
    pede_agendamento = bool(_RE_AGENDAMENTO.search(normalizado))
    fala_de_saude = bool(_RE_SAUDE.search(_SAUDE_NEGADA.sub(" ", normalizado)))

    # Termo de saude com pedido de orientacao: pergunta clinica, mesmo que a pessoa
    # tambem queira marcar. Termo de saude sem orientacao e sem pedido de marcar:
    # sintoma. Termo de saude so com pedido de marcar: e agendamento (AG-09).
    if fala_de_saude and (pede_orientacao or not pede_agendamento):
        subtipo = PERGUNTA if pede_orientacao else SINTOMA
        intencoes.append(Intencao(CLINICO_BLOQUEADO, subtipo=subtipo))

    if _RE_ADMINISTRATIVO.search(normalizado):
        intencoes.append(Intencao(ADMINISTRATIVO))

    if pede_agendamento:
        intencoes.append(Intencao(AGENDAMENTO))

    return ResultadoClassificacao(tuple(intencoes), ORIGEM_REGRA)