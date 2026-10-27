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
9. Decisões em aberto
10. Critério de pronto e README
11. Riscos e cuidados

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
7. **O núcleo é escrito à mão.** As etapas 3 a 5 são o miolo do aprendizado de Python. Assistentes, inclusive o Claude Code, servem para revisar e sugerir testes, não para gerar o núcleo.

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

| Camada                 | Projeto de estudo                                                                | MVP                                            | O que muda na migração                                 |
| ---------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------ |
| Backend                | Python + FastAPI (`/health` e endpoint de chat de teste)                         | Python + FastAPI                               | Nada                                                   |
| Banco                  | PostgreSQL + pgvector em Docker Compose, RLS ativo                               | Supabase (Postgres + pgvector + RLS)           | String de conexão, migrations, pooler (etapa 15)       |
| Fila                   | Tabela `jobs` + worker com `SKIP LOCKED`                                         | Igual                                          | Nada                                                   |
| IA                     | Claude Haiku via API direta da Anthropic (Sonnet só para comparação na etapa 10) | Claude Haiku via Bedrock                       | `BedrockClient` substitui `AnthropicClient` (etapa 16) |
| Embeddings             | Cohere Embed Multilingual v3 via Bedrock                                         | Igual                                          | Nada                                                   |
| Canal                  | CLI                                                                              | WhatsApp Cloud API                             | `WhatsAppClient` substitui `CliChannel` (etapa 17)     |
| Painel                 | Painel mínimo na etapa 14, na tecnologia definida em Q-17                        | Painel de monitoramento para as clínicas       | Mesma base                                             |
| Autenticação do painel | Igual ao MVP (tabela `usuarios_painel`)                                          | A definir (Q-17)                               | —                                                      |
| Execução               | Docker Compose na máquina local                                                  | Container Docker na Lightsail, instância única | Deploy (etapa 18)                                      |
| Segredos               | Arquivo `.env` fora do repositório                                               | AWS Secrets Manager                            | Leitura de segredos (etapa 16)                         |
| Observabilidade        | Log estruturado no Postgres                                                      | Métricas da Lightsail + log estruturado        | Acrescentar métricas de infraestrutura                 |
| Testes                 | pytest, CI, isolamento entre tenants                                             | Igual                                          | Teste de isolamento também no painel                   |

### Fluxo de uma mensagem

```
Mensagem (CLI no estudo, WhatsApp no MVP)
 ↓
Channel.receive → grava mensagem (message_id UNIQUE; duplicada é ignorada)
 ↓
Cria job PROCESS_INBOUND_MESSAGE (pending) e confirma recebimento

[worker, processo separado, mesmo código-base]
 ↓
SELECT ... FROM jobs ... FOR UPDATE SKIP LOCKED                   trava do job
 ↓
SELECT estado_conversa ... FOR UPDATE                             trava da conversa
 ↓
Se human_mode = true → não responde; a mensagem aparece no painel
 ↓
Classificação de intenção (categoria + confiança)
 ├─ administrativo / agendamento → RAG / function calling
 ├─ clinico_bloqueado → mensagem fixa + handoff + log_auditoria
 ├─ urgencia → mensagem de segurança fixa + handoff urgente + log_auditoria
 └─ ambiguo (ou confiança < 0,7) → 1 esclarecimento → handoff se persistir
 ↓
Channel.send_text(...)
 ↓
UPDATE estado_conversa, COMMIT, job = done
```

Nas etapas 3 a 5 o bloco de classificação é regra determinística simples. A IA entra na etapa 6, por cima do motor de estados que já funciona.

### Estrutura do repositório

```
agente-clinica/
├── app/
│   ├── core/            # estados, transições, regras de negócio
│   ├── channels/        # base.py (Channel), cli.py (estudo), whatsapp.py (MVP)
│   ├── llm/             # base.py (LLMClient), anthropic_client.py (estudo), bedrock_client.py (MVP)
│   ├── embeddings/      # base.py (EmbeddingClient), bedrock_client.py (estudo e MVP)
│   ├── agenda/          # base.py (AgendaProvider), agenda_propria.py
│   ├── jobs/            # fila, worker, retries
│   ├── classification/  # baseline por regra + classificador com LLM
│   ├── rag/             # chunking, indexação, busca filtrada por tenant e categoria
│   ├── tools/           # as 4 ferramentas expostas ao modelo
│   ├── reminders/       # ReminderService e varredura
│   ├── handoff/         # abertura, notificação, takeover (human_mode)
│   ├── auditoria/       # escrita em log_auditoria, handoffs e consents
│   ├── painel/          # rotas e telas do painel (etapa 14)
│   ├── auth/            # login e permissões por clínica (etapa 14)
│   └── db/              # modelos (migrations do Alembic ficam na raiz do repo, ver ADR 0001)
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── concurrency/     # dois workers, mensagens seguidas
│   └── isolation/       # vazamento entre clínicas (obrigatório)
├── eval/                # conversas simuladas, tentativas de desvio, run_eval.py
├── docs/                # documentacao completa do projeto
├── .github/
├── migrations/          # Alembic
├── requirements.txt
├── requirements-dev.txt
├── CLAUDE.md
├── docker-compose.yml
└── README.md
```

### Contratos (interfaces)

| Interface                                           | Estudo                   | MVP                      | Etapa de implementação  |
| --------------------------------------------------- | ------------------------ | ------------------------ | ----------------------- |
| `Channel` — receber, enviar texto e template        | `CliChannel`             | `WhatsAppClient`         | 3 (CLI) e 17 (WhatsApp) |
| `LLMClient` — completar, com ferramentas            | `AnthropicClient`        | `BedrockClient`          | 6 e 16                  |
| `EmbeddingClient` — gerar embeddings                | `BedrockEmbeddingClient` | `BedrockEmbeddingClient` | 8                       |
| `AgendaProvider` — disponibilidade, criar, cancelar | `AgendaPropria`          | `AgendaPropria`          | 5                       |
| `ReminderService` — enviar lembrete                 | Igual                    | Igual                    | 11                      |

O `LLMClient` normaliza dentro dele o formato de resposta e de chamada de ferramenta, para que o restante do código não saiba qual provedor está por trás.

## 5. Dados

Um banco só, com `tenant_id` em toda tabela. Nomes iguais aos da arquitetura v2.1.

| Tabela                                                                    | Etapa                    | Observação                                                                                |
| ------------------------------------------------------------------------- | ------------------------ | ----------------------------------------------------------------------------------------- |
| `clinicas`                                                                | 2                        | Configuração como dado, incluindo `telefone_plantao` da recepção                          |
| `profissionais`, `servicos`, `profissional_servicos`, `horarios_trabalho` | 2                        | Base da agenda                                                                            |
| `regras_agendamento`                                                      | 2                        | Antecedência, janela de cancelamento                                                      |
| `pacientes_contatos`                                                      | 2                        | Dado mínimo: nome e telefone, ambos fictícios                                             |
| `conversas`                                                               | 2                        | `estado_conversa` e `human_mode`                                                          |
| `mensagens`                                                               | 2                        | `message_id` com UNIQUE                                                                   |
| `handoffs`                                                                | 2 (schema), 5 e 13 (uso) | Conversa, motivo, notificação, quem assumiu                                               |
| `log_auditoria`                                                           | 2 (schema), 7 (uso)      | Mensagens bloqueadas ou de urgência                                                       |
| `consents`                                                                | 2                        | Criada e **vazia**. Preenchida só no piloto                                               |
| `privacy_requests`                                                        | 2                        | Criada e **vazia**. Preenchida só no piloto                                               |
| `jobs`                                                                    | 3                        | `type`, `payload`, `status`, `run_at`, `attempts`, `locked_at`, `locked_by`, `last_error` |
| `agendamentos`                                                            | 5                        | Profissional, serviço, data e hora, status                                                |
| `conhecimento_clinica`                                                    | 8                        | Chunks, embedding, `categoria`, modelo de embedding                                       |
| `lembretes`                                                               | 11                       | `enviar_em`, `status`, resposta do paciente                                               |
| `usuarios_painel`                                                         | 14                       | Usuário da clínica, papel, clínica vinculada                                              |

Ficam fora do estudo, e entram só no MVP, a configuração de infraestrutura e as credenciais, que nunca são armazenadas no banco de estudo.

## 6. Plano de construção

Fonte única das etapas 0 a 21, suas entregas e dependências: [`etapas.md`](./etapas.md).

## 7. O que manter idêntico ao MVP

| Elemento                       | Valor a preservar                                                                       | Seção da v2.1 |
| ------------------------------ | --------------------------------------------------------------------------------------- | ------------- |
| Nomes de tabelas e campos      | Os da seção 5                                                                           | 7             |
| Estados da conversa            | `idle`, `coletando_info`, `aguardando_confirmacao`, `escalada`, `encerrada`             | 7             |
| `human_mode`                   | Campo em `conversas`, mesmo sem painel no estudo                                        | 8.4           |
| Tipos de job                   | `PROCESS_INBOUND_MESSAGE`, `SEND_WHATSAPP`, `SEND_REMINDER`, `NOTIFY_HANDOFF`           | 7             |
| Status de job                  | `pending`, `processing`, `done`, `failed`, `dead`                                       | 7             |
| Categorias de intenção         | `administrativo`, `agendamento`, `clinico_bloqueado`, `urgencia`, `ambiguo`             | 7             |
| Threshold inicial de confiança | 0,7, a calibrar na etapa 10                                                             | 8.3           |
| Mensagens fixas                | Para `clinico_bloqueado` e `urgencia`, nunca geradas                                    | 8.3           |
| Ferramentas                    | `verificar_disponibilidade`, `criar_agendamento`, `cancelar`, `buscar_duvida_frequente` | 7             |
| Duas travas                    | `SKIP LOCKED` no job e `FOR UPDATE` na conversa                                         | 8.1           |
| Deduplicação                   | UNIQUE no `message_id`                                                                  | 8.1           |
| Isolamento                     | `tenant_id` em toda tabela, RLS e teste de isolamento                                   | D-03, D-04    |
| Filtro de conteúdo             | `categoria` em `conhecimento_clinica`, filtrado antes da busca                          | 8.3           |
| Regras de lembrete             | T-7 e T-1, consultas com menos de 7 dias, remarcação                                    | 8.2           |
| Modelo de embeddings           | Cohere Embed Multilingual v3 via Bedrock, dimensão 1024                                 | D-14          |
| Auditoria                      | `log_auditoria` para toda mensagem bloqueada ou de urgência                             | 8.3           |

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

## 9. Decisões em aberto

| Decisão                                                        | Como o projeto responde                                     | Etapa  |
| -------------------------------------------------------------- | ----------------------------------------------------------- | ------ |
| Rigor da classificação: 100% LLM, 100% regra ou híbrida (Q-07) | Baseline por regra contra LLM, com custo e latência medidos | 7 e 10 |
| Tentativas de esclarecimento antes de handoff (Q-05)           | Testar 1 contra 2 tentativas nas conversas simuladas        | 10     |
| Conjunto de tentativas de desvio (Q-08)                        | Conjunto dedicado na suíte                                  | 10     |
| Threshold de confiança (Q-06)                                  | Ajustar 0,7 com dado, não com intuição                      | 10     |
| Custo médio por conversa (Q-10)                                | Medido desde a etapa 6                                      | 6 e 10 |
| Tecnologia e autenticação do painel (Q-17)                     | Decidir antes da etapa 13                                   | 13     |
| Metas de sucesso do piloto (Q-15)                              | Não definidas agora; pré-requisito da etapa 21              | 21     |
|                                                                |

## 10. Critério de pronto e README

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

## 11. Riscos e cuidados

- **Escopo.** Não começar WhatsApp, deploy ou painel antes da etapa 12. A ordem existe para evitar esse risco.
- **Cronograma.** Sem prazo, o risco é a etapa se estender sem fim. O controle é o critério de pronto de cada etapa, não uma data.
- **Sigilo.** Antes de publicar o repositório, separar o núcleo genérico das regras e detalhes do produto.
- **Dados e segredos.** Só dado fictício. `.env` no `.gitignore`, nenhuma chave no repositório.
- **Custo.** Definir alerta de gasto (AWS Budgets) na conta de desenvolvimento e teto na conta da API da Anthropic. Rodar a suíte completa de avaliação só quando necessário.
- **Conta AWS.** Conta dedicada, com e-mail operacional e MFA no usuário root. Uso diário por usuário IAM de permissão mínima.
- **Aprendizado.** Se o núcleo (etapas 3 a 5) for gerado por assistente em vez de escrito, o projeto vira portfólio sem virar aprendizado.
