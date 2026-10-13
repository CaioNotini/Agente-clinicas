# Agente Clínicas

Agente de IA que atende clínicas pelo WhatsApp: agenda, remarca e cancela consultas, envia lembretes e responde dúvidas administrativas. Começa como projeto de estudo de baixo custo e migra para o MVP atrás das mesmas interfaces.

## Leitura obrigatória antes de qualquer tarefa

1. [`docs/principios.md`](docs/principios.md): princípios de desenvolvimento do projeto. Sempre consultar antes de começar, em qualquer etapa e para qualquer tipo de tarefa.
2. [`docs/status.md`](docs/status.md): etapa ativa, pendências e estado real. Confirmar ali antes de agir. Não presumir o estado.

Se algo nesta conversa contradizer esses dois documentos, eles prevalecem e a contradição deve ser relatada.

## Fluxo de tarefa

Para cada tarefa, nesta ordem:

1. **Identificar:** etapa ativa, objetivo e arquivos envolvidos.
2. **Especificar:** objetivo, escopo, fora do escopo, critérios de aceitação e testes. Aguardar confirmação.
3. **Planejar:** lista curta de arquivos e abordagem. Aguardar confirmação antes de editar.
4. **Implementar:** a menor solução que atende aos critérios.
5. **Testar:** executar os testes relevantes e relatar a saída real.
6. **Documentar:** atualizar o documento canônico afetado, `docs/status.md` se a etapa mudou de estado, e um ADR se houve decisão arquitetural.
7. **Resumir:** o que mudou, o que foi verificado e o que ficou sem validação.

Tarefas triviais (typo, rename, mudança de uma linha sem decisão) juntam os passos 2 e 3 em uma frase de intenção. Os passos 5 e 7 são obrigatórios em toda tarefa.

Como cada princípio é verificado: [`docs/principios.md`](docs/principios.md).

## Regras de desenvolvimento

1. Respeitar a etapa ativa e seu orçamento. Não ativar serviços pagos, infraestrutura de nuvem nem avançar para o MVP sem autorização explícita.
2. Criar ou atualizar testes sempre que o comportamento mudar.
3. Não afirmar que algo funciona sem evidência de validação. Relatar o que não foi testado.
4. Regras de negócio ficam em código determinístico, nunca só no prompt. Regras de domínio ficam nos documentos canônicos e não são copiadas aqui.
5. Toda consulta a dados de clínica filtra por `tenant_id`.
6. Código depende das interfaces (`Channel`, `LLMClient`, `EmbeddingClient`, `AgendaProvider`, `ReminderService`), nunca de uma implementação concreta fora do seu módulo.
7. Não criar abstrações, pastas ou arquivos para possibilidades hipotéticas. Pasta vazia não é criada.
8. Mudança de regra, decisão ou etapa atualiza o documento canônico e `docs/status.md` no mesmo passo.
9. Decisão arquitetural relevante vira ADR em `docs/decisions/`, usando o template desse diretório.
10. Contradição entre documentos, ou ambiguidade que afeta decisão irreversível: parar e perguntar. Não resolver sozinho.
11. Não ler valores de `.env`, não criar `.env` com valores reais e não versionar segredos. Dados sempre fictícios.
12. Nomes de variáveis e funções: claros, curtos e consistentes entre módulos. Entidades semelhantes recebem nomes parecidos.
13. Comentário de uma linha antes de cada bloco de código que não é óbvio.
14. Nenhum commit, reset, revert, amend, rebase ou push sem pedido explícito. Commits são responsabilidade dos desenvolvedores.

## Escrita dos documentos

- Frases simples e diretas.
- Não usar travessão nem ponto e vírgula em `docs/` e neste arquivo. Código, comentários e SQL seguem a sintaxe normal.
- Links relativos para qualquer documento citado, em vez de repetir o conteúdo.
- Cada documento canônico e cada ADR começa com este cabeçalho:

```
Papel: <uma linha>
Entrada: docs/status.md
Relaciona-se com: <links relativos>
```

- Todo arquivo de `docs/` deve ser alcançável a partir de [`docs/status.md`](docs/status.md) em no máximo dois cliques.

## Onde encontrar o quê

- [`docs/status.md`](docs/status.md): etapa ativa, pendências, índice de entrada
- [`docs/estudo.md`](docs/estudo.md): escopo e etapas 0 a 21
- [`docs/arquitetura.md`](docs/arquitetura.md): decisões técnicas, modelo de dados, questões em aberto
- [`docs/principios.md`](docs/principios.md): princípios e como são verificados
- [`docs/decisions/README.md`](docs/decisions/README.md): template e convenção dos ADRs
- [`docs/diagnosticos/2026-10-13-rodada1.md`](docs/diagnosticos/2026-10-13-rodada1.md): diagnóstico histórico
