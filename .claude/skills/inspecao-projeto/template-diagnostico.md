# Template do diagnóstico

Use exatamente esta estrutura. O arquivo final vai para `docs/`, então valem as regras de escrita do `CLAUDE.md`: frases simples, links relativos, sem travessão e sem ponto e vírgula.

## Classificação

- **Crítico:** vazamento entre clínicas, perda ou duplicação de dado, falha de segurança ou de segredo, setup do zero quebrado, critério de pronto de etapa fechada que não se sustenta.
- **Importante:** bug realista num fluxo principal, divergência entre código e documentação que vai induzir a erro, lacuna de teste em ponto crítico.
- **Melhoria:** caso de borda raro, dívida técnica, documentação sem impacto no comportamento.

Pode qualificar a classificação quando ajudar, como em "Crítico para reprodutibilidade" ou "Importante como risco futuro".

## Evidência

- **Confirmado:** lido no código e coerente com o comportamento documentado do Postgres ou do SQLAlchemy.
- **Confirmado por teste:** um teste ou comando rodado nesta inspeção mostra o problema.
- **Confirmado pelo desenvolvedor:** observado por ele em execução real.
- **Suspeita:** depende de verificação no banco ou em execução.

## Grupos

- **Grupo A:** exige decisão de schema ou arquitetura e ADR.
- **Grupo B:** correção pequena, sem decisão.
- **Grupo C:** adiar para a etapa correspondente.

## Estrutura do arquivo

````markdown
```
Papel: Diagnóstico da rodada N, feito em AAAA-MM-DD. Não reflete o estado atual.
Entrada: docs/status.md
Relaciona-se com: ../status.md, ../etapas.md, ../arquitetura.md, <ADRs citados>, <diagnóstico anterior>
```

# Diagnóstico da rodada N

Inspeção somente de leitura em AAAA-MM-DD, no commit `<hash>`. Nenhum arquivo foi alterado.

<Três a cinco linhas: estado geral, quantos achados em cada classificação, o que bloqueia fechar a etapa ativa.>

## Estado das etapas

<O que o status.md afirma, e o que foi encontrado de diferente.>

## Testes e verificações

<Comandos rodados e a saída real resumida. Ou: "Os testes não foram executados durante a inspeção.">

## Grupo A: exige decisão de schema ou arquitetura e ADR

### A1. <título curto>

- **Classificação:** <Crítico | Importante | Melhoria>. <Evidência>.
- **Onde:** [arquivo:linha](../../caminho#Lx)
- **O que acontece:** <o problema>
- **Cenário que quebra:** <passo a passo concreto>
- **Teste que prova o problema:** <teste existente que falha, ou o teste ou a prova por mutação a escrever>
- **Correção sugerida:** <direção, não código>
- **Arquivos:** <o que a correção vai tocar>
- **Etapa:** <onde corrigir>

## Grupo B: correções pequenas sem decisão

### B1. <mesmo formato>

## Grupo C: adiar para a etapa correspondente

### C1. <mesmo formato>

## Código contra documentação

| Decisão ou trecho | Fonte | Situação | Observação |
| ----------------- | ----- | -------- | ---------- |

## Critérios de pronto das etapas fechadas

| Etapa | Critério | Ainda se sustenta | Evidência |
| ----- | -------- | ----------------- | --------- |

## Itens da rodada anterior

| ID | Situação atual |
| -- | -------------- |

## Documentação

<Links quebrados, cabeçalhos, dois cliques, ambiguidades do status.md.>

## Redundância e itens sem uso

| Item | Onde | Tipo | Evidência | Recomendação | Motivo |
| ---- | ---- | ---- | --------- | ------------ | ------ |

Tipo: duplicado, obsoleto ou sem uso. Recomendação: remover, consolidar ou manter. Itens marcados como manter registram o motivo, para não voltarem na próxima rodada.

## Ordem sugerida

1. <ID e motivo da posição, considerando as dependências>

## O que continua sem validação

<O que não deu para verificar só pela leitura. Inclui sempre: esta inspeção foi feita pelo mesmo modelo que ajuda a escrever o código e não substitui a validação do desenvolvedor.>
````
