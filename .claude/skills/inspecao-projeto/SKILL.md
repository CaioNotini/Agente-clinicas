---
name: inspecao-projeto
description: Inspeção somente de leitura do repositório Agente Clínicas. Lê código, testes e docs, encontra bugs, confere o código contra a arquitetura e os ADRs, reverifica os critérios de pronto das etapas fechadas e classifica cada achado. Use quando o desenvolvedor pedir inspeção, diagnóstico, auditoria, revisão geral do projeto ou uma nova rodada. Não use para corrigir bugs, implementar tarefa ou revisar só um diff multi-tenant (para isso existe o agente rls-reviewer).
---

# Inspeção do projeto

Tarefa somente de leitura. Nenhum arquivo é alterado e o `git status` termina igual ao início. Gravar o relatório em `docs/diagnosticos/` e linkar em `docs/status.md` é um passo separado, que só acontece com aprovação (seção Aprovações do `CLAUDE.md`).

Termos usados aqui: **achado** é qualquer item do relatório. Um achado é um **bug** (comportamento errado), uma **divergência** (código e documentação discordam) ou uma **lacuna** (falta teste, falta doc, critério não coberto).

## Checklist

Copie e marque conforme avança:

```
- [ ] 1. Estado declarado
- [ ] 2. Mudanças desde a última rodada
- [ ] 3. Testes e verificações
- [ ] 4. Leitura do código e bugs
- [ ] 5. Isolamento entre clínicas (rls-reviewer)
- [ ] 6. Código contra documentação
- [ ] 7. Critérios de pronto das etapas fechadas
- [ ] 8. Documentação
- [ ] 9. Redundância e itens sem uso
- [ ] 10. Classificação e relatório
```

## 1. Estado declarado

Ler `docs/principios.md`, `docs/status.md` e `docs/etapas.md`. Anotar a etapa ativa, as etapas concluídas e tudo o que o `status.md` dá como verificado.

Essas afirmações são hipóteses a conferir, não fatos. Um `status.md` desatualizado já foi achado de prioridade alta na rodada 2.

## 2. Mudanças desde a última rodada

Abrir o diagnóstico mais recente em `docs/diagnosticos/` e rodar `git log` desde a data dele. Os arquivos alterados nesse intervalo recebem leitura mais cuidadosa nos passos seguintes.

Para cada item do diagnóstico anterior, marcar: resolvido, ainda aberto ou movido para etapa futura (seção "Previstas para etapas futuras" do `status.md`). Manter os IDs originais (A1, B10, C4), porque o `status.md` cita esses IDs.

## 3. Testes e verificações

A suíte depende do Postgres do Docker e das variáveis do `.env`.

- Nunca abrir o `.env` (regra 17 e hook `block_env`).
- Perguntar ao desenvolvedor se o banco está no ar antes de rodar `pytest tests/ -q`. Avisar que `tests/concurrency/` apaga os jobs `pending` e `processing`.
- `alembic check` pode rodar com o banco no ar. O ciclo `upgrade head`, `downgrade base`, `upgrade head` apaga dados, então só com autorização explícita.
- black, isort e pylint, como na CI, não dependem do banco e podem rodar sempre.

Se a suíte não rodar, registrar "Os testes não foram executados durante a inspeção" e seguir. Nunca afirmar que algo passa sem a saída real.

## 4. Leitura do código e bugs

Ler `app/`, `migrations/` e `tests/`, priorizando o que mudou no passo 2. Pontos de maior risco e onde está a regra de cada um (ler na fonte, não copiar para cá):

- Concorrência, ordem por conversa e conclusão do job: ADR 0005, ADR 0008, `tests/concurrency/`
- Transições de estado: ADR 0003
- Agendamento e handoff: ADR 0004, ADR 0009, seção 7 da `arquitetura.md`
- Erros permanentes e novas tentativas: seções 7 e 8.1 da `arquitetura.md`
- Migrations: docstring contra efeito real, downgrade que não restaura o estado anterior, constraint de que um `ON CONFLICT` depende (item 0 da rodada 3)
- Contas de banco e segredos: regras 12, 17 e 18 do `CLAUDE.md`, ADR 0002

Cada possível bug precisa de `arquivo:linha`, do cenário concreto que dá errado e da evidência. Sem evidência, ele entra como Suspeita.

Para cada bug e para cada ponto de risco, perguntar se algum teste atual falharia caso a regra fosse violada (seção Testes do `CLAUDE.md`). Se nenhum falharia, isso é uma lacuna. Descrever a prova por mutação que mostraria a lacuna, sem executar, porque ela exige alterar código.

## 5. Isolamento entre clínicas

Delegar ao agente `rls-reviewer` (`.claude/agents/rls-reviewer.md`), passando as mudanças desde a última rodada. Não repetir a checklist dele aqui. Cada PROBLEMA que ele apontar vira um achado do relatório.

## 6. Código contra documentação

Para cada decisão da `arquitetura.md` e de cada ADR aceito que a etapa ativa ou as fechadas tocam, marcar uma das opções:

- implementado como documentado
- implementado diferente do documentado
- documentado e não implementado
- implementado e não documentado

Numa divergência, dizer qual lado parece certo e por quê, sem resolver (regra 11).

## 7. Critérios de pronto das etapas fechadas

Para cada etapa dada como concluída no `status.md`, e para a ativa se o `status.md` disser que o critério foi conferido, reler o critério em `etapas.md` e conferir contra o código e os testes atuais. Não confiar na marcação de concluída.

Um critério que não se sustenta mais é sempre Crítico.

## 8. Documentação

- Cabeçalho `Papel`, `Entrada` e `Relaciona-se com` em cada documento canônico e ADR
- Regra dos dois cliques a partir do `status.md`
- Links quebrados e referências a ADR ou ID que não existem
- Travessão ou ponto e vírgula em `docs/`
- Ambiguidades já listadas no `status.md`: continuam abertas?

## 9. Redundância e itens sem uso

Procurar o que já não serve mais, na documentação e no código. Para cada item, mostrar a evidência de que ele está sobrando, como o grep sem chamador, os dois trechos duplicados lado a lado ou o commit que o tornou obsoleto.

Na documentação:

- Regra, decisão ou tabela repetida em mais de um documento. O par `estudo.md` e `arquitetura.md` é o caso recorrente. Indicar qual é o documento canônico e qual trecho vira link.
- Pendência, questão em aberto ou ambiguidade do `status.md` e da `arquitetura.md` que já foi resolvida no código ou num ADR.
- Informação volátil sem uso na etapa ativa, como preços e cotações detalhados.
- Lembretes de funcionalidade futura fora do lugar canônico (`etapas.md` ou "Fora do escopo do MVP").

No código e na configuração:

- Função, classe, módulo, constante ou campo de config sem chamador fora dos testes. Confirmar com grep em `app/`, `scripts/`, `migrations/` e `tests/`.
- Import e variável sem uso (o pylint da CI já aponta parte disso).
- Código comentado, ramo que nunca executa e tratamento de erro para um caso que não acontece mais.
- Dependência em `requirements.txt` ou `requirements-dev.txt` que nenhum arquivo importa.
- Marker do `pytest.ini`, fixture ou helper de teste que nenhum teste usa.
- Teste que repete exatamente o que outro já prova, com a mesma entrada e a mesma asserção.

O que nunca é redundante, mesmo que pareça:

- Migrations já aplicadas. Elas são o histórico do banco e não se apagam. Uma migration com docstring errada é achado de documentação, não de remoção.
- ADR substituído. Ele fica com o status "Substituída", conforme `docs/decisions/README.md`.
- Diagnósticos antigos em `docs/diagnosticos/`, que são registro histórico.
- Interfaces aprovadas na arquitetura (Channel, LLMClient, EmbeddingClient, AgendaProvider, ReminderService), mesmo com uma implementação só (regra 7).
- Testes de isolamento, concorrência e mutação. Na dúvida, o teste fica. Remover teste para simplificar vai contra a seção Testes do `CLAUDE.md`.
- Algo previsto em `etapas.md` para uma etapa futura. Isso é um adiamento, não algo sem uso, e não entra neste passo.

Recomendação para cada item:

- **Remover:** sem uso confirmado e sem papel histórico.
- **Consolidar:** a informação está certa, mas repetida. Manter no documento canônico e trocar a outra cópia por link.
- **Manter:** parecia redundante, mas tem motivo para ficar. Registrar o motivo, para a próxima rodada não apontar de novo.

Remover algo é uma alteração destrutiva e só acontece com aprovação, fora da inspeção. Uma remoção que toque em schema, policy, role ou contrato público vai para o Grupo A.

## 10. Classificação e relatório

Seguir [template-diagnostico.md](template-diagnostico.md) à risca. Ele define a classificação (Crítico, Importante, Melhoria), a legenda de evidência e os grupos A, B e C.

Ordenar a correção pelas dependências entre achados, não só pela gravidade.

Entregar o relatório no chat. Depois, perguntar se deve gravá-lo como `docs/diagnosticos/AAAA-MM-DD-rodadaN.md` e acrescentar o link no `status.md`.

## Regras

- Somente leitura: nenhuma edição, migration ou commit durante a inspeção.
- A correção sugerida é uma direção, não código pronto. O desenvolvedor implementa.
- Zero achados críticos é um resultado válido. Não inventar achado para encher o relatório.
- Esta inspeção não é validação independente, porque foi feita pelo mesmo modelo que ajuda a escrever o código. Dizer isso na seção "O que continua sem validação".
