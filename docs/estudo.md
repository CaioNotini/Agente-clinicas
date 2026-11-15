```
Papel: Escopo, premissas e orçamento do projeto de estudo.
Entrada: docs/status.md
Relaciona-se com: arquitetura.md, etapas.md, decisions/0001-alembic.md, status.md
```

# Motor do agente de agendamento: projeto de estudo

Núcleo do MVP construído como projeto de estudo. Este projeto é a base do MVP: a mesma sequência de etapas leva do estudo ao produto, sem reescrita.

Outubro de 2026 · rascunho pessoal · v1.2 · alinhado à arquitetura do MVP v2.1

## Sumário

1. Visão geral
2. Princípios para a migração ser simples
3. Escopo: o que entra no estudo, o que entra só no MVP
4. Stack e arquitetura
5. Dados
6. Plano de construção
7. O que manter idêntico ao MVP
8. Migração: como as etapas 15 a 21 levam ao MVP
9. Critério de pronto e README
10. Riscos e cuidados

---

## 1. Visão geral

O objetivo é um projeto de estudo que vai servir como base para o núcleo do agente de agendamento. Esse núcleo é o mesmo que vai para produção: estados, fila, classificação, RAG, ferramentas, auditoria, handoff e painel.

A diferença entre estudo e MVP está em três pontos: canal (CLI no estudo, WhatsApp no MVP), infraestrutura (Docker local no estudo, Supabase e Lightsail no MVP) e provedor de IA (API direta no estudo, Bedrock no MVP). As interfaces que separam esses pontos são as mesmas nos dois ambientes.

| Fator                | Situação                                                                          |
| -------------------- | --------------------------------------------------------------------------------- |
| Desenvolvimento      | 1 pessoa, part-time, cursando duas graduações                                     |
| Orçamento            | Próximo de zero no estudo. Infraestrutura do MVP segue o teto da arquitetura v2.1 |
| Dado tratado         | Somente fictício, em todo o estudo, testes e demo                                 |
| Objetivo             | Projeto de estudo para chegar a um MVP em produção                                |
| Entregável do estudo | Repositório com README, testes, suíte de avaliação e diagrama                     |
| Entregável final     | MVP em produção com piloto e painel para clínicas                                 |

**Cronograma.** Tudo é tratado por ordem de dependência, sem prazo. Quando uma etapa termina, a próxima começa se as dependências estiverem prontas.

## 2. Princípios para a migração ser simples

1. **Mesmo vocabulário do MVP.** Tabelas, campos, estados, tipos de job, categorias de intenção e ferramentas têm os mesmos nomes. Renomear depois é a migração mais chata e menos útil.
2. **Tudo que muda entre estudo e MVP fica atrás de uma interface.** Canal, LLM, embeddings, agenda, lembretes e notificação. A migração troca implementações, não o miolo.
3. **Regra de negócio em Python comum e testado.** Conflito de horário, janela de cancelamento e agendamento duplicado nunca vivem no prompt. A IA interpreta e redige; o código decide.
4. **Estado explícito no banco, não no prompt.**
5. **`tenant_id` e RLS desde o primeiro dia**, mesmo com uma clínica só. É o que permite passar para multicliente sem mexer no schema.
6. **Configuração por variável de ambiente.** Nenhuma chave no código nem no repositório.

## 3. Escopo: o que entra no estudo, o que entra só no MVP

| Parte                                                               | Seção da arquitetura v2.1 | No estudo                                                 | Só no MVP                         |
| ------------------------------------------------------------------- | ------------------------- | --------------------------------------------------------- | --------------------------------- |
| Classificação com confiança e mensagens fixas                       | 8.3                       | Etapa 7                                                   | —                                 |
| Máquina de estados reduzida e lock por conversa                     | 8.1                       | Etapa 4                                                   | —                                 |
| Fila de jobs com `SKIP LOCKED` e deduplicação                       | 8.1                       | Etapa 3                                                   | —                                 |
| RLS, `tenant_id` e teste de isolamento                              | D-04, seção 9.3           | Etapa 2 (obrigatório)                                     | Teste também no painel (etapa 14) |
| Function calling com as 4 ferramentas                               | 7                         | Etapa 9                                                   | —                                 |
| RAG por clínica com pgvector e Cohere via Bedrock                   | D-14                      | Etapa 8                                                   | —                                 |
| Agendamento atrás de `AgendaProvider`                               | D-17                      | Só `AgendaPropria`                                        | —                                 |
| Lembretes T-7 e T-1 com regras de borda                             | 8.2                       | Etapa 11                                                  | —                                 |
| Handoff com `human_mode` e takeover                                 | 8.4                       | Etapa 13                                                  | —                                 |
| Notificação de handoff no WhatsApp pessoal                          | 8.4                       | Etapa 13, com canal simulado                              | Template real aprovado (etapa 20) |
| Painel de monitoramento com login                                   | 5, D-22                   | Etapa 14                                                  | —                                 |
| Tabelas `handoffs`, `log_auditoria`, `consents`, `privacy_requests` | 7                         | Schema na etapa 2; `consents` e `privacy_requests` vazias | Uso real no piloto                |
| Métricas                                                            | 12                        | Log estruturado e script de relatório                     | Painel mostra as métricas         |
| WhatsApp Cloud API e templates                                      | 4                         | Fora (canal CLI)                                          | Etapas 17 e 20                    |
| Bedrock para LLM                                                    | D-13                      | Fora (API direta)                                         | Etapa 16                          |
| Supabase                                                            | D-02                      | Fora (Postgres em Docker)                                 | Etapa 15                          |
| Lightsail e deploy                                                  | D-19                      | Fora                                                      | Etapa 18                          |
| Secrets Manager e credenciais IAM                                   | D-24                      | Fora (`.env` fora do repositório)                         | Etapas 16 e 18                    |
| Adaptadores de agenda externa                                       | D-17                      | Fora                                                      | Fora (só sob demanda)             |
| LGPD formal e forma jurídica                                        | 12                        | Fora                                                      | Etapa 20                          |

## 4. Stack e arquitetura

Comparação reduzida entre o estudo e o MVP. Detalhes de cada camada, incluindo o ponto de troca na migração, estão em [arquitetura.md, seção 4](./arquitetura.md#4-stack).

| Camada                                             | No estudo                                                                        | No MVP                                         |
| -------------------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------- |
| [Backend](./arquitetura.md#4-stack)                | Python + FastAPI (`/health` e endpoint de chat de teste)                         | Python + FastAPI                               |
| [Banco](./arquitetura.md#4-stack)                  | PostgreSQL + pgvector em Docker Compose, RLS ativo                               | Supabase (Postgres + pgvector + RLS)           |
| [Fila](./arquitetura.md#4-stack)                   | Tabela `jobs` + worker com `SKIP LOCKED`                                         | Igual                                          |
| [IA](./arquitetura.md#4-stack)                     | Claude Haiku via API direta da Anthropic (Sonnet só para comparação na etapa 10) | Claude Haiku via Bedrock                       |
| [Embeddings](./arquitetura.md#4-stack)             | Cohere Embed Multilingual v3 via Bedrock                                         | Igual                                          |
| [Canal](./arquitetura.md#4-stack)                  | CLI                                                                              | WhatsApp Cloud API                             |
| [Painel](./arquitetura.md#4-stack)                 | Painel mínimo na etapa 14, na tecnologia definida em Q-17                        | Painel de monitoramento para as clínicas       |
| [Autenticação do painel](./arquitetura.md#4-stack) | Igual ao MVP (tabela `usuarios_painel`)                                          | A definir (Q-17)                               |
| [Execução](./arquitetura.md#4-stack)               | Docker Compose na máquina local                                                  | Container Docker na Lightsail, instância única |
| [Segredos](./arquitetura.md#4-stack)               | Arquivo `.env` fora do repositório                                               | AWS Secrets Manager                            |
| [Observabilidade](./arquitetura.md#4-stack)        | Log estruturado no Postgres                                                      | Métricas da Lightsail + log estruturado        |
| [Testes](./arquitetura.md#4-stack)                 | pytest, CI, isolamento entre tenants                                             | Igual                                          |

### Fluxo de uma mensagem

Fluxo completo de uma mensagem recebida, incluindo as duas travas de concorrência: [arquitetura.md, seção 8.1](./arquitetura.md#81-mensagem-recebida).

### Estrutura do repositório

Estrutura de pastas com comentários: [arquitetura.md, seção 6](./arquitetura.md#6-estrutura-do-código).

### Contratos (interfaces)

O estudo implementa estas interfaces, com a classe concreta entre parênteses.

- `Channel` (`CliChannel`)
- `LLMClient` (`AnthropicClient`)
- `EmbeddingClient` (`BedrockEmbeddingClient`)
- `AgendaProvider` (`AgendaPropria`)
- `ReminderService` (igual ao MVP)

Responsabilidade de cada interface e a implementação do MVP estão em [arquitetura.md, seção 6](./arquitetura.md#interfaces).

## 5. Dados

Um banco só, com `tenant_id` em toda tabela. Nomes iguais aos da arquitetura v2.1. Modelo de dados completo, tabela por tabela: [arquitetura.md, seção 7](./arquitetura.md#7-modelo-de-dados). A etapa que cria cada tabela está em [etapas.md](./etapas.md).

Ficam fora do estudo, e entram só no MVP, a configuração de infraestrutura e as credenciais, que nunca são armazenadas no banco de estudo.

## 6. Plano de construção

Fonte única das etapas 0 a 21, suas entregas e dependências: [`etapas.md`](./etapas.md).

## 7. O que manter idêntico ao MVP

Estados da conversa, status de job, tipos de job, categorias de intenção e as ferramentas expostas ao modelo são valores fixos, definidos em [arquitetura.md, seção 7](./arquitetura.md#7-modelo-de-dados).

| Elemento                       | Valor a preservar                                              | Seção da v2.1 |
| ------------------------------ | -------------------------------------------------------------- | ------------- |
| Nomes de tabelas e campos      | Os da seção 5                                                  | 7             |
| `human_mode`                   | Campo em `conversas`, mesmo sem painel no estudo               | 8.4           |
| Threshold inicial de confiança | 0,7, a calibrar na etapa 10                                    | 8.3           |
| Mensagens fixas                | Para `clinico_bloqueado` e `urgencia`, nunca geradas           | 8.3           |
| Duas travas                    | `SKIP LOCKED` no job e `FOR UPDATE` na conversa                | 8.1           |
| Deduplicação                   | Chave primária em `mensagens.id`                               | 8.1           |
| Isolamento                     | `tenant_id` em toda tabela, RLS e teste de isolamento          | D-03, D-04    |
| Filtro de conteúdo             | `categoria` em `conhecimento_clinica`, filtrado antes da busca | 8.3           |
| Regras de lembrete             | T-7 e T-1, consultas com menos de 7 dias, remarcação           | 8.2           |
| Modelo de embeddings           | Cohere Embed Multilingual v3 via Bedrock, dimensão 1024        | D-14          |
| Auditoria                      | `log_auditoria` para toda mensagem bloqueada ou de urgência    | 8.3           |

## 8. Migração: como as etapas 15 a 21 levam ao MVP

A migração não é uma reescrita. Cada etapa troca uma implementação atrás de uma interface, ou adiciona um componente que o estudo não tinha.

| Etapa            | O que muda                                                     | O que não muda                      |
| ---------------- | -------------------------------------------------------------- | ----------------------------------- |
| 15 Supabase      | String de conexão, migrations, pooler, validação de BYPASSRLS  | Schema, RLS e testes                |
| 16 Bedrock (LLM) | `BedrockClient` implementa `LLMClient`                         | Prompts, ferramentas, classificação |
| 17 WhatsApp      | `WhatsAppClient` implementa `Channel`, com webhook e templates | Fila, estados, lock e regras        |
| 18 Lightsail     | Container e script de deploy                                   | Código da aplicação                 |
| 20 Pré-piloto    | Templates reais, Business Verification, forma jurídica         | Núcleo                              |
| 21 Piloto        | Dado real, com controles de LGPD ativos                        | Núcleo e painel                     |

**Cuidados na migração:**

- **Embeddings.** Como o modelo é o mesmo nos dois ambientes, não há reindexação. Cada chunk continua registrando o modelo usado.
- **Supabase fora da VPC.** O banco é acessado pela internet com TLS e allowlist de IP quando disponível. Isso precisa constar no contrato com as clínicas como subprocessador.
- **Worker e RLS.** O worker usa role dedicada com BYPASSRLS, nunca usada em requisição. Validar no Supabase antes da etapa 15 (Q-02).
- **Pooler.** Worker e API seguram transações longas por causa dos locks. Confirmar que o pooler em modo transação é compatível (Q-03).
- **Dados.** O banco de estudo contém só dado fictício e nunca recebe dado real de paciente.

## 9. Critério de pronto e README

**Estudo pronto (etapa 12):**

- Os testes passam em CI, incluindo concorrência (etapas 3 e 4) e isolamento com RLS (etapa 2).
- A suíte de avaliação roda com um comando, e os resultados estão registrados no README.
- Existe um diagrama do fluxo da seção 4.
- O README tem "Decisões e tradeoffs": tamanho de chunk, o que falhou, o que mudaria.
- O README tem "Como evoluir para produção", em linhas gerais.
- Existe demonstração gravada do fluxo em CLI, com dados fictícios.

**MVP pronto (etapa 21):**

- Etapas 13 e 14 concluídas, com teste de isolamento cobrindo o painel.
- Migração concluída: Supabase, Bedrock, WhatsApp e Lightsail, com rollback testado.
- Suíte de avaliação reexecutada no Bedrock, com resultado registrado.
- Pré-requisitos do piloto atendidos (etapa 20), e metas de sucesso definidas (Q-15).

## 10. Riscos e cuidados

- **Escopo.** Não começar WhatsApp, deploy ou painel antes da etapa 12. A ordem existe para evitar esse risco.
- **Cronograma.** Sem prazo, o risco é a etapa se estender sem fim. O controle é o critério de pronto de cada etapa, não uma data.
- **Sigilo.** Antes de publicar o repositório, separar o núcleo genérico das regras e detalhes do produto.
- **Dados e segredos.** Só dado fictício. `.env` no `.gitignore`, nenhuma chave no repositório.
- **Custo.** Definir alerta de gasto (AWS Budgets) na conta de desenvolvimento e teto na conta da API da Anthropic. Rodar a suíte completa de avaliação só quando necessário.
- **Conta AWS.** Conta dedicada, com e-mail operacional e MFA no usuário root. Uso diário por usuário IAM de permissão mínima.
