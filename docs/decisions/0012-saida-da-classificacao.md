```
Papel: define o formato da saída da classificação, os limites de confiança, o subtipo de clinico_bloqueado e a regra de prioridade entre intenções, comuns ao baseline por regra e ao classificador com LLM.
Entrada: docs/status.md
Relaciona-se com: ../arquitetura.md (D-09, D-10, seções 7, 8.1 e 8.3, Q-06 e Q-07), ../etapas.md (etapas 7, 9 e 10), ../guias_respostas/guia_respostas.md (decisões 13, 14, 22, 23 e 25), 0003-grafo-de-transicoes.md, 0010-llmclient.md
```

# 0012: Saída da classificação

## Contexto

A etapa 7 tem duas classificações: a regra da tarefa 7.1, que serve de baseline, e o LLM da tarefa 7.2. O baseline existe para ser comparado com o LLM na etapa 10, então os dois precisam devolver o mesmo formato. Por isso este ADR vem antes da 7.1.

O que já estava decidido:

- Categorias fechadas `administrativo`, `agendamento`, `clinico_bloqueado`, `urgencia` e `ambiguo`, com score de confiança (D-09 e seção 7 da [arquitetura](../arquitetura.md#7-modelo-de-dados)).
- `clinico_bloqueado` e `urgencia` respondem com mensagem fixa, nunca gerada (D-10).
- A classificação devolve uma lista de intenções. Com `urgencia` na lista, só a mensagem de urgência sai. `clinico_bloqueado` é tratado antes das demais (decisão 23 do [guia](../guias_respostas/guia_respostas.md#decisões-aprovadas-registradas-na-planilha), refinada em 2026-11-26, seção 8.1 da [arquitetura](../arquitetura.md#81-mensagem-recebida)).
- `clinico_bloqueado` tem duas respostas, uma para a pergunta clínica e outra para o sintoma (decisões 22 e 25, seção 8.3 da [arquitetura](../arquitetura.md#83-escopo-clínico)).
- A urgência é verificada antes do `human_mode` (decisão 13). A direção registrada na 8.1 é que, com `human_mode` ativo, essa verificação use só a regra.

Faltava definir o formato da saída, como os limites de confiança se aplicam a cada categoria, como a saída separa as duas respostas de `clinico_bloqueado` e como a decisão é calculada a partir da lista.

## Alternativas consideradas

- **Uma única categoria por mensagem:** descartada pela decisão 23. A mensagem "quero marcar e quanto custa?" tem duas intenções, e as duas devem ser respondidas.
- **O LLM decide o que fazer, além de rotular:** descartada. A decisão é regra de negócio e fica em código determinístico e testado (regra 4 do [CLAUDE.md](../../CLAUDE.md)). Uma decisão gerada pelo modelo não é verificável.
- **Um limite único de 0,7 para todas as categorias:** descartada. Uma urgência com confiança 0,6 seria descartada e, se a lista ficasse vazia, viraria `ambiguo`, que leva a um esclarecimento antes do handoff. Isso contraria o princípio da assimetria ("na dúvida, escala"), seção 8.3 da [arquitetura](../arquitetura.md#83-escopo-clínico).
- **Duas categorias no lugar do subtipo (por exemplo `clinico_pergunta` e `clinico_sintoma`):** descartada. A D-09 mantém as categorias fechadas, e a categoria `clinico_bloqueado` continua sendo a unidade do recall e da auditoria. O subtipo muda só a forma da resposta.
- **Confiança 1,0 nas intenções da regra:** descartada. Daria a impressão de certeza absoluta e distorceria a comparação de calibração com o LLM.
- **`ambiguo` como intenção que o LLM pode devolver:** descartada. `ambiguo` ao lado de outra intenção não tem significado claro, e o resultado de "não sei" já é coberto pela lista vazia.
- **Saída inválida do LLM tratada como `ambiguo`:** descartada. Uma urgência numa saída malformada iria para o esclarecimento.
- **Saída inválida do LLM tratada como erro transitório:** descartada. Gastaria mais chamadas pagas e atrasaria a resposta, com a mesma chance de vir inválida de novo.

## Decisão

A classificação devolve uma lista de intenções rotuladas, com a origem, e uma função pura do código calcula a decisão a partir dessa lista.

### Formato

`ResultadoClassificacao`:

| Campo | Conteúdo |
| ----- | -------- |
| `intencoes` | lista de `Intencao`, com no máximo uma por categoria. Pode ser vazia |
| `origem` | `regra` ou `llm` |

`Intencao`:

| Campo | Conteúdo |
| ----- | -------- |
| `categoria` | `administrativo`, `agendamento`, `clinico_bloqueado` ou `urgencia` |
| `subtipo` | `pergunta` ou `sintoma`, só quando a categoria é `clinico_bloqueado`. Vazio nas demais |
| `confianca` | número de 0 a 1 quando a origem é `llm`. Vazio quando a origem é `regra` |

- As 5 categorias da D-09 continuam fechadas. `ambiguo` nunca entra na lista. Ele é a decisão quando não sobra intenção confiável.
- O LLM só rotula. Ele não escolhe a resposta nem a ordem.
- Uma saída do LLM é inválida quando tem categoria desconhecida, categoria repetida, `ambiguo` na lista, confiança fora de 0 a 1 ou vazia, ou subtipo fora de `clinico_bloqueado`. A saída inválida é descartada por inteiro, vale o resultado da regra (origem `regra`) e o fato vai ao log estruturado, sem o conteúdo da mensagem.

### Limites de confiança

- Origem `llm`: `urgencia` e `clinico_bloqueado` são aceitas com confiança a partir de 0,5. `administrativo` e `agendamento` são aceitas a partir de 0,7. Intenção abaixo do limite da categoria é descartada.
- Origem `regra`: a intenção é aceita sem comparação com limite.
- Lista vazia depois dos limites leva a `ambiguo`.
- Os dois valores são iniciais e são calibrados na etapa 10 (Q-06 da [arquitetura](../arquitetura.md#13-questões-em-aberto)).

### Subtipo de `clinico_bloqueado`

- `pergunta`: a mensagem espera uma resposta clínica ("posso tomar esse remédio?"). Recebe a mensagem fixa de clínico bloqueado e abre o handoff.
- `sintoma`: a mensagem espera atendimento ("estou com dor nas costas"). Recebe a oferta de atendimento: o paciente escolhe entre o handoff e seguir com o agendamento (decisão 22).
- Quando o subtipo é incerto, o padrão é `sintoma`, tanto no LLM quanto na regra. A regra também preenche o subtipo.
- As métricas de recall são por categoria. O erro de subtipo é medido à parte na etapa 10.

### Regra de prioridade

Uma função pura recebe as intenções aceitas e devolve a decisão: a lista ordenada do que tratar.

1. Com `urgencia`: só a urgência. As demais intenções são descartadas (decisão 13 e refinamento da decisão 23).
2. Com `clinico_bloqueado`: ele primeiro, com a resposta do subtipo, e as demais intenções depois.
3. Sem as duas: `administrativo` antes de `agendamento`.
4. Lista vazia: `ambiguo`.

A função é testada com todas as combinações das 4 categorias que podem estar na lista, os 16 subconjuntos, incluindo a lista vazia, e com os dois subtipos.

Se as intenções seguintes ao `clinico_bloqueado` saem na mesma resposta ou no turno seguinte fica para a etapa 9.

### Relação com outras decisões

Estes pontos ficam registrados aqui e não são implementados por este ADR:

- Em conversa com `human_mode` ativo, a verificação de urgência usa só a regra, sem LLM (seção 8.1 da [arquitetura](../arquitetura.md#81-mensagem-recebida)).
- A mesma regra decide se a mensagem pula a espera do agrupamento (decisão 14).
- Por isso a regra é uma função pura e rápida, sem banco nem rede.
- A escolha entre classificação só por LLM, só por regra ou híbrida continua na Q-07, decidida na etapa 10. `origem` tem um valor só por resultado. Este ADR não define como combinar as duas.
- Auditoria: o escopo continua o da seção 7 da [arquitetura](../arquitetura.md#7-modelo-de-dados), ou seja, as mensagens com `clinico_bloqueado` ou `urgencia`. Nelas, `log_auditoria` grava também a lista completa de intenções, a origem e a decisão resultante. Este ADR não decide sobre o conteúdo da mensagem na auditoria. A divergência entre "categoria e texto original" e as colunas `acao`, `descricao` e `dados` continua listada no [status](../status.md) e se resolve na tarefa 7.4.

## Justificativa

- **Lista com origem.** O mesmo formato nas duas origens permite comparar regra e LLM na etapa 10 sem conversão. A origem separa o que pode ter calibração do que não pode.
- **Decisão no código.** A prioridade é regra de negócio de segurança. Numa função pura ela é testável por completo, com todas as combinações, e não depende do comportamento do modelo.
- **`ambiguo` fora da lista.** Ele significa a falta de intenção confiável. Mantê-lo fora evita combinações sem sentido e reduz os casos de teste a subconjuntos das 4 categorias reais.
- **Saída inválida cai na regra.** A regra está sempre disponível e reconhece as urgências que ela já cobre, o que evita perder uma urgência por causa de uma saída malformada.
- **Dois limites.** Pelo princípio da assimetria, errar para o lado de `urgencia` e `clinico_bloqueado` custa menos que deixá-las passar. O valor de 0,5 é um ponto inicial conservador, escolhido entre acionar a urgência demais, o que a decisão 25 quer evitar e que leva a conversa para `escalada`, e acionar de menos. A confiança declarada pelo LLM não é uma probabilidade calibrada, então o valor não tem leitura probabilística. Ele é calibrado na etapa 10.
- **Ordem `administrativo` antes de `agendamento`.** A dúvida administrativa se resolve no mesmo turno. O agendamento abre um fluxo de vários turnos (`coletando_info`). Com ele no fim da resposta, a próxima mensagem do paciente responde à pergunta do agendamento.
- **Subtipo com padrão `sintoma`.** Nos dois subtipos o agente nunca responde conteúdo clínico, então a proteção principal é a mesma. A diferença é só se o handoff é forçado ou oferecido. Handoff forçado em excesso sobrecarrega o profissional ou a secretaria, principalmente nos perfis sem secretaria (P3 e P4), que são os mais frequentes.
- **Confiança vazia na regra.** A regra não estima incerteza. Um valor fixo seria inventado e entraria na calibração como se fosse medida. Para o baseline, as métricas são precisão e recall. A calibração vale só para o LLM.

## Consequências

- A D-09 passa a ter dois limites, com o score de confiança só na origem `llm`. A arquitetura sobe para a versão 2.3, e a Q-06 passa a calibrar os dois valores.
- O critério de pronto da etapa 7 deixa de ser "abaixo de 0,7 vira `ambiguo`" e passa a ser "abaixo do limite da categoria".
- A regra da 7.1 e o LLM da 7.2 devolvem `ResultadoClassificacao`. A função de prioridade é a mesma para os dois.
- Na 7.2, o esquema de saída estruturada do LLM segue este formato. A validação da saída é do código, não do modelo.
- O erro de subtipo não aparece no recall por categoria. Ele precisa de métrica própria na etapa 10.
- Pendência da 7.2, sem decisão agora: avaliar se a regra roda sempre antes do LLM, como primeira linha de defesa. Se a regra detectar `urgencia`, a mensagem sai sem esperar o LLM. Isso também cobriria a falha ou o timeout da chamada ao LLM, que hoje levaria o job a novas tentativas com a urgência esperando ([ADR 0010](./0010-llmclient.md)).
- Pendência da 7.3: o texto da oferta de atendimento precisa soar natural também quando a mensagem era uma pergunta, já que o subtipo incerto cai em `sintoma`. Exemplo: "essa questão precisa ser avaliada pelo(a) {profissional}".
- Se uma categoria nova entrar, a função de prioridade, a ordem fixa e os testes das combinações precisam ser revistos, junto com uma nova versão da D-09.

## Status

Aceita
