"""Classificacao por regra, baseline da etapa 7 (tarefa 7.1, ADR 0012).

Funcao pura e rapida, sem banco nem rede, porque tambem serve a verificacao de
urgencia com human_mode ativo e, na etapa 9, a dispensa da espera do agrupamento.
Devolve ResultadoClassificacao com origem regra e confianca vazia.

Principios:
1. Urgencia. Um falso negativo da regra e coberto pelo LLM, porque a urgencia e a
   uniao das duas origens. Um falso positivo nao tem correcao, porque com a regra
   disparada o LLM nao e consultado. Na duvida, a regra de urgencia nao dispara.
   O piso de cobertura sao as 5 urgencias de docs/fake_clinic/pergs_bloqueadas.md
   e as linhas UR-01 e UR-02 do guia. Elas continuam obrigatorias, porque com
   human_mode ativo ou com o LLM falhando so a regra existe.
   Excecao para autolesao: a negacao suprime a urgencia, mas o passado nao.
   "Tentei me matar ano passado" recebe a mensagem de urgencia, porque ela cita o
   CVV, que e apoio, e o historico de tentativa e um risco que continua.
2. Clinico, versao mais fraca do mesmo principio. Um sintoma vago que a regra nao
   pega e coberto pelo LLM. Um clinico falso transforma uma pergunta administrativa
   numa recusa. Na duvida entre ampliar o vocabulario de saude e deixar para o LLM,
   deixe para o LLM. Termo ambiguo ("mg", "dose", "sede", "resultado do exame")
   nao entra.
3. Expressoes sao padroes que generalizam, nao frases copiadas das fontes dos
   testes. Palavra de vocabulario do dominio (reembolso, convenio) pode ficar.

Como funciona:
1. O texto e normalizado (minusculas, sem acento, sem pontuacao, espacos simples).
   Todas as expressoes abaixo sao escritas ja nessa forma.
2. Cada categoria tem suas expressoes como dado, no topo do modulo. Para estender a
   regra, acrescente uma expressao na tupla certa e um caso de teste.
3. Urgencia e avaliada por trecho (pontuacao e "mas" separam os trechos). Nao conta
   quando uma negacao vem logo antes ("nao estou com dor no peito") ou quando o
   trecho fala do passado ("tive dor no peito mes passado") sem marca de agora.
   "desde ontem" e "ha 3 dias" continuam sendo atuais. O passado nao vale para
   autolesao (principio 1).
4. clinico_bloqueado combina dois sinais: um termo de saude nao negado e, para o
   subtipo pergunta, um pedido de orientacao ligado a uma conduta clinica ("devo
   tomar", "pode ser grave", "o que faco com essa dor"). "deveria", "pode ser",
   "tudo bem" e "o que faco" sozinhos nao contam. Sem pedido de orientacao o
   subtipo e sintoma, que tambem e o padrao do ADR 0012.
5. Pedido de agendamento (verbo de agenda, "tem horario", "qual especialista",
   "voces atendem isso") com termo de saude e sem pedido de orientacao e
   agendamento, nao clinico (decisao 4, linhas AG-09 e AG-09b). Substantivo solto
   ("uma marca vermelha") nao e pedido de agendamento.
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

# Risco imediato a vida. So frases fortes que descrevem o que acontece agora.
_URGENCIA = (
    r"dor (muito )?(forte )?no peito",
    r"aperto no peito",
    r"falta( de)? ar(?! condicionad)",
    # respirar pelo nariz entupido nao e falta de ar
    r"(dificil|dificuldade|nao consigo|nao to conseguindo|nao estou conseguindo)"
    r"( de| pra| para)? respirar(?! (direito )?pel[oa] (nariz|narina))",
    # sangramento ativo e sem controle. "sangramento forte" sozinho fica com o LLM
    r"sangrando muito",
    r"sangrando sem parar",
    r"nao para de sangrar",
    r"sangramento que nao para",
    r"desmaiei",
    r"acab\w+ de desmai\w+",
    r"desmai\w+ (agora|agorinha|ha pouco|neste momento)",
    r"desmai\w+ (\w+ )?e nao (acorda|acordou|responde|reage)",
    r"perd\w+ (a consciencia|os sentidos)",
    # overdose em curso ou no ato recente, porque o efeito continua depois do ato.
    # "tem como fazer overdose de vitamina?" nao entra.
    r"(tendo|tomei|tomou|tomaram|tive|teve|deu) (uma )?overdose",
    # quem tomou muitos de uma vez, nao quem toma varios remedios por dia
    r"(tomei|tomou|engoli|engoliu) (uns |umas )?(muitos|muitas|varios|varias|\d{2,})"
    r" (comprimidos|remedios|pilulas|capsulas)",
    # convulsao so no presente. "remedio pra convulsao" nao entra.
    r"convulsionando",
    r"(esta|ta|to|estou|esta tendo|ta tendo|to tendo|estou tendo) (uma )?convuls\w+",
    r"(teve|tive|deu) (uma )?convuls\w+ (agora|agorinha|ha pouco|neste momento)",
    # sinais de AVC. "rosto caido" sozinho e queixa estetica
    r"boca (torta|caida)",
    r"rosto (torto|paralisado|caido de um lado)",
    r"nao consigo mexer (o|a|um|uma|meu|minha) (braco|perna|lado)",
)

# Autolesao. A negacao suprime, o passado nao (principio 1 do docstring).
_AUTOLESAO = (
    # "morrer de" e figura de linguagem ("vou morrer de tedio")
    r"(penso|pensando|pensei|vontade|quero|vou) (em |de )?"
    r"(me machucar|me cortar|me matar|tirar (a )?minha (propria )?vida"
    r"|acabar com (a )?minha vida|morrer(?! de\b))",
    r"tent\w+ (me |se )?matar",
    r"suicid\w*",
    r"nao aguento mais viver",
)

# Negacao logo antes da expressao de urgencia, com ate tres palavras no meio
# ("nao estou com dor no peito", "nao tenho falta de ar")
_NEGACAO_ANTES = re.compile(r"\b(?:nao|nunca|sem|nem)(?: \w+){0,3} $")

# Fato passado. Minutos e horas nao entram ("sangrando faz uns 30 minutos")
_PASSADO = re.compile(
    r"\b(?:(?:semana|mes|ano) passad[oa]"
    r"|(?:ha|faz) (?:\w+ ){0,2}(?:semanas?|mes|meses|anos?)"
    r"|anos atras|no passado)\b"
)
_AGORA = re.compile(r"\b(?:agora|hoje|ainda|neste momento|desde)\b")

# Termo de saude: o assunto da mensagem e o corpo ou um tratamento do paciente.
# "exame", "sangue", "mg", "dose" e "sede" sozinhos nao entram (principio 2).
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
    r"boca (\w+ )?seca",
    r"diabetes",
    r"pressao alta",
    r"ansiedade",
    r"depressao",
    r"cancer",
    r"infeccao",
    r"sangrou",
    r"sangrando",
    r"exame (deu|veio|mostrou|acusou)",
    r"hemoglobina",
)

# Termo de saude negado nao conta ("e urgente, mas nao doi", OD-03). "nao doi so
# quando..." afirma que doi no resto do tempo.
_SAUDE_NEGADA = re.compile(
    r"\b(?:nao (?:doi|doeu|ta doendo|esta doendo)(?! so\b)"
    r"|nao (?:estou|to|tenho|sinto|senti) (?:com )?(?:dor|dores|febre)"
    r"|sem (?:dor|dores|febre))\b"
)

# Pedido de orientacao clinica, sempre ligado a uma conduta ou a um diagnostico.
# "devo" e "deveria" sozinhos nao entram: "qual especialidade devo marcar?" e
# agendamento (AG-09).
_ORIENTACAO = (
    r"posso (tomar|usar|beber|comer|misturar|parar|continuar)",
    r"devo (tomar|usar|continuar|parar|fazer|evitar)",
    r"deveria (tomar|usar|continuar|parar|fazer|evitar|ir)",
    r"tenho que (tomar|parar|continuar)",
    r"preciso (tomar|parar|continuar)",
    r"tudo bem (eu )?(tomar|usar|parar|continuar|misturar|beber|comer)",
    r"(isso )?e normal",
    r"e (ruim|grave|perigoso)",
    r"faz mal",
    r"pode ser (algo |alguma coisa )?(grave|serio|perigoso|ruim|preocupante|normal)",
    r"pode ser (cancer|tumor|infeccao|alergia|diabetes)",
    r"o que pode ser",
    r"o que (eu )?tenho",
    r"acha(m)? que (eu )?tenho",
    r"o que (eu )?(faco|fazer|devo fazer) (com|pra|para|contra) (\w+ ){0,2}dor(es)?",
    r"qual remedio",
    r"quantos mg",
    r"qual (a )?dose",
    r"(voce|vc|voces|vcs) (tomaria|usaria|recomenda|recomendaria|indica|indicaria"
    r"|sugere|sugeriria|receitaria|passaria)",
    r"(e|seria) (mais )?bom (pra|para|contra)",
)

# Pedido de agendamento: verbo de agenda ou pergunta de especialidade ou servico.
# Tambem e o que tira o termo de saude sozinho do clinico_bloqueado (AG-09, AG-09b).
_AGENDAMENTO = (
    r"(marcar|agendar|remarcar|desmarcar|cancelar)",
    r"(marco|agendo|remarco|desmarco|cancelo)",
    r"me marca",
    r"marca (pra|para) mim",
    r"encaixe",
    r"tem horario",
    r"horario (disponivel|livre|vago)",
    r"quero (uma )?consulta",
    r"com quem (eu )?(marco|agendo|passo)",
    # pedido de consulta com uma especialidade ou profissional ("ver isso com dermato")
    r"com (o |a )?(dermato\w*|ortoped\w*|clinico geral|dentista|doutor|doutora|dr|dra)",
    # qual profissional procurar a partir de um sintoma (decisao 4)
    r"(qual|que) (tipo de )?(especialidade|especialista|medic[oa]|profissional)",
    r"(atende|atendem|trata|tratam|cuida|cuidam)( de)? (isso|disso)",
    r"(psicolog\w*|medic[oa]s?|profissional|especialista|alguem|dentista)"
    r" que (atende|trata|cuida)",
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
    # servico oferecido pela clinica ("voces fazem exame de sangue?", AD-06)
    r"(voces|a clinica) (fazem|faz|aplicam|aplica|oferecem|oferece|realizam|realiza)",
    r"resultado do (meu |seu )?exame",
    r"especialidades",
    r"antecedencia",
    r"chegar antes",
    r"emergencia(s)?",
    r"faltar",
)


def _compilar(expressoes):
    # \b nas duas pontas: "dor" nao casa com "dorme", "falta" nao casa com "faltar"
    return re.compile(r"\b(?:" + "|".join(expressoes) + r")\b")


_RE_URGENCIA = _compilar(_URGENCIA)
_RE_AUTOLESAO = _compilar(_AUTOLESAO)
_RE_SAUDE = _compilar(_SAUDE)
_RE_ORIENTACAO = _compilar(_ORIENTACAO)
_RE_AGENDAMENTO = _compilar(_AGENDAMENTO)
_RE_ADMINISTRATIVO = _compilar(_ADMINISTRATIVO)

_FORA_DE_PALAVRA = re.compile(r"[^a-z0-9]+")
# A pontuacao separa os trechos antes de a normalizacao apaga-la. "mas" separa
# depois, ja no texto normalizado.
_PONTUACAO = re.compile(r"[.,;:!?\n]+")
_MAS = re.compile(r"\bmas\b")


def _normalizar(texto: str) -> str:
    """Minusculas, sem acento, sem pontuacao e com espacos simples."""
    sem_acento = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto.lower())
        if not unicodedata.combining(caractere)
    )
    return _FORA_DE_PALAVRA.sub(" ", sem_acento).strip()


def _tem_urgencia(texto: str) -> bool:
    """Urgencia atual e afirmada em algum trecho do texto."""
    for parte in _PONTUACAO.split(texto):
        for trecho in _MAS.split(_normalizar(parte)):
            trecho = trecho.strip()
            no_passado = _PASSADO.search(trecho) and not _AGORA.search(trecho)
            expressoes = (
                (_RE_AUTOLESAO,) if no_passado else (_RE_URGENCIA, _RE_AUTOLESAO)
            )
            for expressao in expressoes:
                for achado in expressao.finditer(trecho):
                    if not _NEGACAO_ANTES.search(trecho[: achado.start()]):
                        return True
    return False


def classificar_por_regra(texto: str) -> ResultadoClassificacao:
    """Rotula o texto com as intencoes que a regra reconhece."""
    if not isinstance(texto, str):
        raise TypeError("classificar_por_regra espera texto (str)")

    normalizado = _normalizar(texto)
    intencoes = []

    if _tem_urgencia(texto):
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
