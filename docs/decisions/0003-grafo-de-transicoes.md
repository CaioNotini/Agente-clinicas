```
Papel: registra o grafo de transicoes validas entre os estados da conversa (etapa 4.1).
Entrada: docs/status.md
Relaciona-se com: ../arquitetura.md (D-08, secoes 7, 8.1 e 8.4), ../etapas.md (etapa 4), ../../app/core/estados.py, ../../tests/concurrency/test_estados.py
```

# 0003: Grafo de transicoes entre estados da conversa

## Contexto

A decisao D-08 de [`arquitetura.md`](../arquitetura.md) fixa estado explicito em `conversas.estado_conversa` com cinco estados: `idle`, `coletando_info`, `aguardando_confirmacao`, `escalada`, `encerrada`. A arquitetura cita os estados e da pistas do fluxo nas secoes 8.1 e 8.4, mas nao define o conjunto de transicoes validas entre eles. A etapa 4 (ver [`etapas.md`](../etapas.md)) exige transicoes deterministicas e que transicoes invalidas sejam rejeitadas. Este ADR fixa esse grafo, que D-08 deixou em aberto.

## Alternativas consideradas

- **Permitir qualquer transicao entre os cinco estados.** Descartada: nao atende ao criterio da etapa 4 de rejeitar transicoes invalidas, e tira a garantia de que o estado reflete um fluxo real.
- **Estado inferido pelo LLM a cada mensagem.** Ja descartada em D-08 por custo de tokens e ambiguidade.
- **Incluir `idle -> encerrada`.** Descartada por falta de caso real nesta etapa: fechar a conversa a partir de `idle` dependeria de interpretar conteudo (por exemplo, uma despedida), o que e classificacao de intencao, fora do escopo da etapa 4. O fechamento passa por `coletando_info`, `aguardando_confirmacao` ou `escalada`.
- **`encerrada` como estado terminal.** Descartada: como a conversa e unica por `(tenant_id, contato_telefone)`, o mesmo paciente volta a escrever e a conversa precisa ser retomada. Por isso `encerrada -> idle` e permitida.

## Decisao

O grafo de transicoes validas e, por origem:

| Origem                   | Destinos validos                                      |
| ------------------------ | ----------------------------------------------------- |
| `idle`                   | `coletando_info`, `escalada`                          |
| `coletando_info`         | `aguardando_confirmacao`, `escalada`, `encerrada`, `idle` |
| `aguardando_confirmacao` | `coletando_info`, `escalada`, `encerrada`, `idle`     |
| `escalada`               | `idle`, `encerrada`                                   |
| `encerrada`              | `idle`                                                |

Qualquer par fora dessa tabela e rejeitado, inclusive transicao para o mesmo estado (nao ha laco) e transicao que envolva estado desconhecido. O estado inicial de uma conversa nova e `idle`. A fonte da verdade executavel do grafo e `app/core/estados.py`.

## Justificativa

Um grafo fechado e pequeno torna a maquina de estados verificavel e deterministica, como pedem D-08 e a etapa 4. Cada aresta corresponde a um passo de fluxo previsto na arquitetura: comeco de agendamento (`idle -> coletando_info`), avanco e correcao na coleta (`coletando_info <-> aguardando_confirmacao`), escalonamento a partir de qualquer ponto ativo (`-> escalada`, secoes 8.1 e 8.4), devolucao ao bot (`escalada -> idle`, secao 8.4) e reabertura de uma conversa encerrada pelo mesmo contato (`encerrada -> idle`).

## Consequencias

- O chamador que muda `estado_conversa` deve validar a transicao com `app/core/estados.py` antes de gravar. Uma transicao proibida levanta `TransicaoInvalida`.
- Transicoes dirigidas por conteudo (qual aresta tomar) dependem de classificacao de intencao e entram a partir da etapa 7. A etapa 4 so garante o grafo e o lock.
- Se um fluxo futuro exigir uma aresta nova (por exemplo `idle -> encerrada` com justificativa real), este ADR e o grafo em `app/core/estados.py` precisam ser atualizados juntos.

## Status

Aceita
