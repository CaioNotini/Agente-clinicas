```
Papel: Convenção e template para registros de decisão (ADRs).
Entrada: docs/status.md
Relaciona-se com: ../estudo.md, ../arquitetura.md, ../status.md
```

# Decisões de arquitetura e documentação

Este diretório registra decisões tomadas durante a implementação que ainda não têm lugar em `estudo.md` ou `arquitetura.md`. Decisões já cobertas pelas tabelas D-xx de `arquitetura.md` não são migradas para aqui.

## Convenção de nomes

`NNNN-slug.md`, numeração sequencial de 4 dígitos, sem lacunas, sem reuso de número. `slug` em kebab-case, curto, descrevendo o tema (ex.: `0001-alembic.md`).

## Status possíveis

- **Proposta**: registrada, ainda não aplicada.
- **Aceita**: decidida e em vigor.
- **Substituída**: não vale mais. O registro permanece, com link para a decisão que a substituiu.

## Template

O bloco abaixo é o conteúdo completo de um ADR novo, incluindo o cabeçalho entre cercas de código.

````markdown
```
Papel: <uma linha>
Entrada: docs/status.md
Relaciona-se com: <links relativos para documentos, ADRs ou testes>
```

# NNNN: Título curto da decisão

## Contexto

O que motivou a decisão, e o trecho do documento canônico que a gerou (com link).

## Alternativas consideradas

- Alternativa A: por que foi descartada
- Alternativa B: por que foi descartada

## Decisão

O que foi decidido, em uma frase objetiva.

## Justificativa

Por que essa alternativa, em vez das outras.

## Consequências

O que passa a ser verdade, o que fica mais difícil, o que precisa ser revisitado se mudar.

## Status

Proposta | Aceita | Substituída por NNNN
````
