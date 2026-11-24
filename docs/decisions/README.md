```
Papel: Convenção e template para registros de decisão (ADRs).
Entrada: docs/status.md
Relaciona-se com: ../estudo.md, ../arquitetura.md, ../status.md
```

# Decisões de arquitetura e documentação

Este diretório registra decisões tomadas durante a implementação que ainda não têm lugar em `estudo.md` ou `arquitetura.md`. Decisões já cobertas pelas tabelas D-xx de `arquitetura.md` não são migradas para aqui.

## Registros

- [0001: Alembic na raiz do repositório](./0001-alembic.md)
- [0002: Contas de banco](./0002-contas-de-banco.md)
- [0003: Grafo de transições entre estados da conversa](./0003-grafo-de-transicoes.md)
- [0004: Conflito de horário de agendamentos](./0004-conflito-de-horario.md)
- [0005: Ordem de processamento por conversa](./0005-ordem-por-conversa.md)
- [0006: Provisionamento das roles automatizadas](./0006-provisionamento-de-roles.md)
- [0007: FKs compostas com tenant_id](./0007-fks-compostas-por-tenant.md)
- [0008: Conclusão atômica do job](./0008-conclusao-atomica-do-job.md)
- [0009: Agendamento e handoff da etapa 5 sem presumir recepção](./0009-agendamento-handoff-etapa5.md)
- [0010: Contrato do LLMClient e SDK da Anthropic na versão 2026-10-21 da API](./0010-llmclient.md)

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
