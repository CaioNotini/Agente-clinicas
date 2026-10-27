# Agente Clínicas

Agente de IA que atende clínicas pelo WhatsApp: agenda, remarca e cancela consultas, envia lembretes e responde dúvidas administrativas. Começa como projeto de estudo de baixo custo e migra para o MVP atrás das mesmas interfaces.

## Leitura obrigatória antes de qualquer tarefa

1. [`docs/principios.md`](docs/principios.md): princípios de desenvolvimento do projeto. Sempre consultar antes de começar, em qualquer etapa e para qualquer tipo de tarefa.
2. [`docs/status.md`](docs/status.md): etapa ativa, pendências e estado real. Confirmar ali antes de agir. Não presumir o estado. Sequência completa das etapas em [`docs/etapas.md`](docs/etapas.md).
3. Consultar as especificações, a arquitetura, os testes e os ADRs pertinentes à tarefa. Não carregar documentos irrelevantes sem necessidade.

Se algo nesta conversa contradizer esses tres documentos, eles prevalecem e a contradição deve ser relatada.

## Fluxo de tarefa

Para cada tarefa, nesta ordem:

1. **Identificar:** comfirmar a etapa ativa, objetivo e arquivos envolvidos.
2. **Especificar:** definir objetivo, escopo, itens fora do escopo, critérios de aceitação e testes. Aguardar confirmação.
3. **Planejar:** para tarefas não triviais, apresentar uma abordagem curta, arquivos afetados, riscos e testes.
4. **Implementar:** produzir a menor solução completa que atenda aos critérios, sem antecipar funcionalidades futuras.
5. **Testar:** executar os testes e as verificações pertinentes. Analisar falhas e regressões.
6. **Documentar:** atualizar o documento canônico afetado, `docs/status.md` se a etapa mudou de estado, e um ADR se houve decisão arquitetural.
7. **Resumir:** informar o que mudou, as decisões tomadas, os testes executados, seus resultados reais e o que permanece sem validação.

## Aprovações

1. Tarefas não triviais: aguardar confirmação ao final da especificação e ao final do plano. Após aprovar o plano, executar somente o que ele prevê.
2. Tarefas triviais: registrar a intenção em uma frase e executar. Os passos de testar e resumir continuam obrigatórios.
3. Alterações destrutivas, decisões arquiteturais, mudanças de segurança e qualquer ação fora do plano aprovado exigem aprovação explícita antes da execução.
4. Contradições e ambiguidades que afetem requisitos, segurança ou decisões irreversíveis: parar e perguntar.

## Regras de desenvolvimento

1. Respeitar a etapa ativa e seu orçamento. Não ativar serviços pagos, infraestrutura de nuvem nem avançar para o MVP sem autorização explícita.
2. Criar ou atualizar testes sempre que o comportamento mudar. Os critérios de qualidade estão na seção [Testes](#testes).
3. Não afirmar que algo funciona sem evidência de validação. Relatar o que não foi testado.
4. Regras de negócio ficam em código determinístico, nunca só no prompt. Regras de domínio ficam nos documentos canônicos e não são copiadas aqui.
5. Toda operação sobre dados pertencentes a uma clínica deve respeitar o tenant_id autorizado para aquela operação. Não confiar em um identificador de clínica fornecido pelo cliente sem validar a autorização correspondente.
6. Testar o isolamento entre clínicas, incluindo leituras, criações, atualizações, exclusões, relacionamentos e tarefas assíncronas quando aplicáveis.
7. Utilizar as interfaces aprovadas na arquitetura, como Channel, LLMClient, EmbeddingClient, AgendaProvider e ReminderService, quando forem pertinentes. Não criar abstrações ou dependências indiretas sem justificativa.
8. Não criar abstrações, pastas ou arquivos para possibilidades hipotéticas. Não criar pastas vazias.
9. Mudanças de regras, decisões ou estado do projeto devem atualizar os documentos canônicos pertinentes. Atualizar docs/status.md quando o estado real mudar.
10. Decisões arquiteturais relevantes devem ser registradas em ADRs em docs/decisions/, usando o template do diretório.
11. Não resolver silenciosamente contradições ou ambiguidades que afetem requisitos, segurança ou decisões importantes.
12. Não abrir, imprimir, copiar ou expor segredos. Não criar arquivos .env com valores reais nem versionar credenciais. Usar exclusivamente dados fictícios.
13. Seguir os procedimentos aprovados para executar testes e comandos que dependam de variáveis de ambiente, sem expor seus valores.
14. Utilizar nomes claros, curtos e consistentes para variáveis, funções e entidades relacionadas.
15. Escrever código claro e autoexplicativo. Adicionar comentários quando explicarem motivos, restrições ou comportamentos não óbvios. Não repetir em comentários o que o código já expressa claramente.
16. Nenhum commit, reset, revert, amend, rebase ou push sem pedido explícito. Commits são responsabilidade dos desenvolvedores.
17. Voce nunca, em hipotese alguma, deve acessar o arquivo .env
18. Banco: a aplicação usa somente `app_clinicas`. Nunca usar `cnotini` (superusuário) nem `scheduler_service` (BYPASSRLS) em código de aplicação. Ver [ADR 0002](docs/decisions/0002-contas-de-banco.md).
19. Testes de isolamento usam somente `app_clinicas` para verificar o RLS. Dados de teste podem ser criados com `cnotini`, mas a verificação não.
20. Toda tabela nova com `tenant_id` recebe a policy `isolamento_tenant`, entra em `TABELAS_TENANT` e é coberta pelos testes de isolamento antes de ser considerada concluída.
21. Não criar, alterar ou remover roles, policies, grants nem o RLS sem pedido explícito. Essas mudanças exigem ADR.

## Testes

- Testes devem cobrir os casos de falha relevantes: entradas inválidas, estados inesperados e cenários negativos.
- Em mudanças críticas (isolamento, autorização, concorrência, lembretes e classificação clínica), revisar cenários de falha e possíveis regressões antes de dar a tarefa como concluída.
- Passar nos testes não basta. Avaliar se eles detectariam uma violação real do requisito.
- Testes escritos ou revisados pelo mesmo modelo não constituem validação independente. A validação final cabe ao desenvolvedor.
- Não alegar que uma integração externa funciona em condições reais quando apenas testes locais ou mocks foram executados.
- Se um teste falhar, investigar a causa. Não remover, pular ou enfraquecer o teste para obter aprovação.

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
- Priorizar documentos canônicos claros, sem duplicação de regras ou decisões.
- Distinguir fatos verificados, decisões aprovadas, hipóteses, questões pendentes e funcionalidades planejadas.
