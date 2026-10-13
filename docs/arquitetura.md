# Arquitetura do MVP: agente de agendamento para clínicas via WhatsApp

Outubro de 2026 · versão 2.1 · documento de referência para os sócios e para o desenvolvimento · alinhado ao plano de estudo v1.2

---

## 1. Resumo

O produto é um agente de IA que atende clínicas pelo WhatsApp. Ele agenda, remarca e cancela consultas, envia lembretes para reduzir no-show e responde dúvidas administrativas. Não faz orientação clínica.

A clínica acompanha tudo por um **painel de monitoramento**: vê a agenda, o histórico das conversas e as métricas, e assume uma conversa quando o agente encaminha o caso para a recepção. Quando há handoff, a recepção é avisada no WhatsApp pessoal de quem está de plantão, com link direto para a conversa no painel.

A arquitetura é um backend Python (FastAPI) com um worker que processa mensagens a partir de uma fila no PostgreSQL. Cada mensagem é classificada, passa por uma máquina de estados explícita com lock por conversa, e só então aciona o modelo de IA (Claude Haiku) por meio de ferramentas determinísticas. Regras de negócio ficam em código comum e testado; a IA interpreta e redige. Um único banco PostgreSQL (Supabase no MVP) atende todas as clínicas, com `tenant_id` em toda tabela e Row Level Security.

O MVP é construído a partir do **projeto de estudo**. Os módulos, interfaces, tabelas e nomes são os mesmos nos dois. A migração troca implementações atrás das interfaces e não reescreve o núcleo. O plano de estudo é a base do MVP: a mesma sequência de etapas leva do estudo ao produto.

## 2. Premissas

| Fator | Situação |
|---|---|
| Time | 2 desenvolvedores part-time. Um deles também está cursando duas graduações |
| Orçamento de infraestrutura | Teto de R$600/mês enquanto não houver cliente pagante |
| Dado tratado | Dado de saúde, sensível pela LGPD. Estudo, testes e demo usam apenas dado fictício |
| Cronograma | Tratado por ordem de dependência, sem prazo fixo |
| Valores comerciais | Mensalidade e preços serão definidos depois do desenvolvimento |
| Metas de sucesso | Não definidas agora; ficam como questão em aberto (Q-15) |

Princípio que guia todas as decisões: **simples o bastante para uma pessoa operar, desenhado para não precisar de reescrita ao crescer para multicliente.**

## 3. Decisões

Decisões com status **Travada** não são revisitadas sem nova versão deste documento. Decisões **Em aberto** estão na seção 14.

| ID | Decisão | Status | Alternativa descartada e motivo |
|---|---|---|---|
| D-01 | Backend em Python + FastAPI | Travada | Node/TypeScript: o time domina Python, e o estudo é em Python |
| D-02 | PostgreSQL com pgvector como único banco. Docker no estudo, Supabase no MVP | Travada | Banco de vetor separado: mais um serviço para operar |
| D-03 | Banco único multi-tenant, com `tenant_id` em toda tabela desde o primeiro dia | Travada | Banco ou schema por cliente: custo e operação incompatíveis com o orçamento. Revisável se um contrato exigir |
| D-04 | Row Level Security ativo desde o início, no estudo e no MVP, com teste de isolamento obrigatório | Travada | Confiar só na aplicação: um bug de filtro vazaria dado entre clínicas |
| D-05 | Role de worker com BYPASSRLS, usada só pelo processo de jobs e pela varredura de lembretes. Nunca em código que atende requisição | Travada (validação no Supabase, Q-02) | Worker com a role da aplicação: não enxerga jobs de todas as clínicas |
| D-06 | Fila de jobs em tabela PostgreSQL com `SKIP LOCKED` e deduplicação por `message_id` | Travada | Celery + Redis: mais infraestrutura. Gatilho de migração: segunda instância da aplicação |
| D-07 | Lock por conversa com `SELECT ... FOR UPDATE` | Travada | Fila FIFO por conversa: mais complexa, sem ganho no volume de piloto |
| D-08 | Estado explícito em `conversas.estado_conversa`, com 5 estados | Travada | Estado inferido pelo LLM a cada mensagem: custo de tokens e ambiguidade |
| D-09 | Classificação em categoria fechada + score de confiança; abaixo de 0,7 vira `ambiguo` | Travada (threshold a calibrar, Q-06) | Só rótulo sem confiança: não trata casos de fronteira |
| D-10 | `clinico_bloqueado` e `urgencia` respondem com mensagem fixa aprovada, nunca gerada | Travada | Resposta gerada pelo LLM: risco de recusa parcialmente clínica e de variação não auditável |
| D-11 | Ferramentas determinísticas. A lista de ferramentas é a barreira de escopo | Travada | Modelo livre com regras no prompt: não é verificável |
| D-12 | Orquestração própria sobre a API do modelo, sem LangChain | Travada | LangChain/LangGraph: abstrações difíceis de depurar, dependências pesadas e quebras entre versões |
| D-13 | Claude Haiku. No estudo via API direta da Anthropic; no MVP via AWS Bedrock, com retenção zero travada por conta/projeto | Travada | API direta no MVP: retenção depende de contrato empresarial. Modelos da linha Mythos/Fable exigem compartilhamento de dados no Bedrock, portanto não são usados. Sonnet só para comparação pontual na etapa 10 |
| D-14 | Embeddings: Cohere Embed Multilingual v3 via AWS Bedrock, nos dois ambientes, dimensão 1024 | Travada (validações na etapa 8, Q-01) | Modelo local via Ollama: indisponível no Bedrock, o que obrigaria reindexação na migração. Titan Text Embeddings V2: alternativa se a validação falhar |
| D-15 | WhatsApp Cloud API direto pela Meta, sem BSP | Travada | BSP (Twilio, 360dialog, Zenvia): mensalidade de plataforma |
| D-16 | Canal CLI no estudo, atrás da interface `Channel` | Travada | — |
| D-17 | Agendamento atrás de `AgendaProvider`. `AgendaPropria` é o padrão; adaptadores externos só sob demanda de cliente real | Travada | Integração com Google Calendar, iClinic ou Feegow desde o início: esforço alto sem cliente pedindo |
| D-18 | Lembretes em T-7 dias (pede confirmação e oferece remarcação) e T-1 dia (confirmação curta), com regras para consultas marcadas com menos de 7 dias (seção 8.2). Tabela `lembretes` é a fonte da verdade; varredura a cada 15 minutos cria jobs `SEND_REMINDER` | Travada | Job por lembrete no APScheduler: perde agendamentos se a aplicação reiniciar |
| D-19 | Hospedagem da aplicação na Lightsail, instância única, container Docker | Travada | Elastic Beanstalk e EC2 com Auto Scaling: mais peças AWS para um piloto de instância única |
| D-20 | Observabilidade: métricas da Lightsail (infra) e log estruturado no Postgres (produto e agente) | Travada | Stack dedicada de observabilidade: mais um serviço para manter |
| D-21 | Supabase Free na demo, Pro no piloto com dado real | Travada | Free no piloto: sem backup diário e com pausa por inatividade |
| D-22 | **Painel de monitoramento no MVP** (substitui a decisão anterior de não ter painel). A clínica vê agenda, conversas, handoffs e métricas, e assume conversas. Resumo diário pelo WhatsApp continua como complemento | Travada (revisa a versão 2.0 deste documento) | Sem painel: a recepção não teria como acompanhar nem assumir conversas |
| D-23 | Sem Multi-AZ e sem VPC privada no banco. Conexão TLS com restrição de IP de origem quando disponível | Travada (tradeoff aceito) | RDS em VPC: custo e operação que o orçamento não comporta |
| D-24 | Tokens da Meta no AWS Secrets Manager. Credencial IAM de permissão mínima na Lightsail, rotacionada | Travada | Token em variável de ambiente ou planilha: risco de segurança |
| D-25 | Escopo clínico: o produto é atendimento administrativo. Qualquer orientação de saúde está fora | Travada | — |
| D-26 | Tabelas `handoffs`, `consents` e `privacy_requests` criadas no schema inicial. `consents` e `privacy_requests` ficam vazias até o piloto | Travada | Criar depois: reconstruir consentimento retroativamente não é auditável |
| D-27 | Dado fictício em todo ambiente de estudo, testes e demo | Travada | — |
| D-28 | Cronograma por ordem de dependência, sem prazo. Não há estimativa de semanas | Travada | Calendário fixo: não reflete a disponibilidade part-time |
| D-29 | Handoff com notificação no WhatsApp pessoal da recepção de plantão. A resposta ao paciente é feita no painel, e sai pelo número oficial da clínica (ver seção 8.4) | Travada | Transferir a conversa para o WhatsApp pessoal: a conversa da Cloud API não pode sair do número oficial |
| D-30 | Valores comerciais (mensalidade, taxa de implantação) definidos após o desenvolvimento | Travada | — |
| D-31 | Metas de sucesso do piloto não definidas agora | Em aberto (Q-15) | — |

## 4. Stack

| Camada | MVP | Projeto de estudo | Ponto de troca |
|---|---|---|---|
| Backend | Python + FastAPI | Python + FastAPI | — |
| Banco | PostgreSQL + pgvector no Supabase, RLS ativo | PostgreSQL + pgvector em Docker Compose, RLS ativo | String de conexão, migrations |
| Fila | Tabela `jobs` + worker com `SKIP LOCKED` | Igual | — |
| IA | Claude Haiku via AWS Bedrock | Claude Haiku via API direta da Anthropic | `BedrockClient` substitui `AnthropicClient` |
| Embeddings | Cohere Embed Multilingual v3 via Bedrock | Igual | — |
| Canal | WhatsApp Cloud API | CLI | `WhatsAppClient` substitui `CliChannel` |
| Painel | Aplicação web para a clínica (Q-17 define a tecnologia) | Painel mínimo na etapa 14, mesma tecnologia | — |
| Autenticação do painel | A definir (Q-17), com tabela `usuarios_painel` | Igual | — |
| Execução | Container Docker na Lightsail, instância única | Docker Compose local | Deploy |
| Segredos | AWS Secrets Manager | Arquivo `.env` fora do repositório | Leitura de segredos |
| Observabilidade | Métricas da Lightsail + log estruturado no Postgres | Log estruturado no Postgres | — |
| Testes e CI | pytest, CI, teste de isolamento entre clínicas | pytest, CI, teste de isolamento entre clínicas | — |

## 5. Arquitetura de componentes

```
                    ┌─────────────────────────────┐
  Paciente ──────►  │ WhatsApp (Meta Cloud API)   │ ◄── Recepção (painel)
                    └──────────────┬──────────────┘
                                   │ webhook (assinatura X-Hub-Signature-256)
                                   ▼
┌──────────────────────── Lightsail (instância única, Docker) ────────────────────────┐
│                                                                                      │
│  ┌──────────────────┐   ┌──────────────────────────────────┐  ┌──────────────────┐  │
│  │ API (FastAPI)    │   │ Worker (mesmo código-base)       │  │ Painel web       │  │
│  │ - webhook        │   │ - consome jobs (SKIP LOCKED)     │  │ - agenda         │  │
│  │ - grava mensagem │   │ - trava conversa (FOR UPDATE)    │  │ - conversas      │  │
│  │ - cria job       │   │ - classifica, decide, chama tools│  │ - handoffs       │  │
│  │ - /health        │   │ - varredura de lembretes (15 min)│  │ - métricas       │  │
│  └────────┬─────────┘   │ - notifica handoff               │  └────────┬─────────┘  │
│           │             └──────┬──────────────┬────────────┘           │            │
└───────────┼────────────────────┼──────────────┼────────────────────────┼────────────┘
            │ TLS                │ TLS          │ TLS (IAM)              │ TLS
            ▼                    ▼              ▼                        ▼
┌────────────────────────┐ ┌──────────────┐ ┌──────────────────┐ ┌────────────────────┐
│ Supabase (PostgreSQL)  │ │ AWS Bedrock  │ │ AWS Secrets Mgr  │ │ Usuários da clínica│
│ - tenant_id + RLS      │ │ Haiku +      │ │ tokens Meta      │ │ (login no painel)  │
│ - pgvector (RAG)       │ │ Cohere Embed │ └──────────────────┘ └────────────────────┘
│ - jobs, conversas,     │ │ retenção zero│
│   agenda, handoffs,    │ └──────────────┘
│   log_auditoria        │
└────────────────────────┘
```

**Regras de rede.** O banco aceita conexão apenas com TLS e, quando o plano permitir, apenas do IP fixo da Lightsail. A aplicação não expõe o banco. O webhook da Meta é o único endpoint público de integração, validado pela assinatura. O painel é o único acesso humano, protegido por login.

**Quem usa qual credencial.**

| Processo | Credencial de banco | Acesso à AWS |
|---|---|---|
| API e painel (requisições) | Role da aplicação, sujeita a RLS | Bedrock e Secrets Manager, via credencial IAM mínima |
| Worker e varredura de lembretes | Role `scheduler_service` com BYPASSRLS | Igual |
| Migrations | Role de migração, usada só no deploy | Não usa |

## 6. Estrutura do código

A estrutura é a mesma do plano de estudo. Os módulos de núcleo (`core`, `classification`, `jobs`, `tools`, `rag`, `reminders`, `auditoria`) não importam implementação concreta de canal, LLM, embedding ou agenda. Dependem só das interfaces.

```
agente-clinica/
├── app/
│   ├── core/            # estados, transições, orquestração da mensagem
│   ├── channels/        # base.py (Channel), cli.py (estudo), whatsapp.py (MVP)
│   ├── llm/             # base.py (LLMClient), anthropic_client.py (estudo), bedrock_client.py (MVP)
│   ├── embeddings/      # base.py (EmbeddingClient), bedrock_client.py (estudo e MVP)
│   ├── agenda/          # base.py (AgendaProvider), agenda_propria.py
│   ├── jobs/            # fila, worker, retries, status
│   ├── classification/  # baseline por regra + classificador com LLM
│   ├── rag/             # chunking, indexação, busca filtrada por tenant e categoria
│   ├── tools/           # as 4 ferramentas expostas ao modelo
│   ├── reminders/       # ReminderService e varredura
│   ├── handoff/         # abertura de handoff, notificação, takeover (human_mode)
│   ├── auditoria/       # escrita em log_auditoria, handoffs e consents
│   ├── painel/          # rotas e telas do painel da clínica
│   ├── auth/            # login, usuários do painel, permissões por clínica
│   └── db/              # modelos e migrations (Alembic)
├── tests/
│   ├── unit/            # regras de negócio sem I/O
│   ├── integration/     # banco real, fila, lock
│   ├── concurrency/     # dois workers, mensagens seguidas
│   └── isolation/       # vazamento entre clínicas (obrigatório)
├── eval/                # conversas simuladas, tentativas de desvio, run_eval.py
├── docker-compose.yml
└── README.md
```

### Interfaces

| Interface | Responsabilidade | Estudo | MVP | Etapa |
|---|---|---|---|---|
| `Channel` | Receber e enviar mensagem; enviar template fora da janela de 24h | `CliChannel` | `WhatsAppClient` | 3 e 17 |
| `LLMClient` | Completar com ferramentas e saída estruturada; registrar tokens e latência | `AnthropicClient` | `BedrockClient` | 6 e 16 |
| `EmbeddingClient` | Gerar embeddings e registrar o modelo usado | `BedrockEmbeddingClient` | `BedrockEmbeddingClient` | 8 |
| `AgendaProvider` | Disponibilidade, criar, cancelar | `AgendaPropria` | `AgendaPropria` | 5 |
| `ReminderService` | Enviar lembrete e registrar resposta | Igual | Igual | 11 |

O `LLMClient` normaliza o formato de resposta e de chamada de ferramenta. O restante do código não sabe qual provedor está por trás.

## 7. Modelo de dados

Um banco, `tenant_id` em toda tabela. Nomes idênticos entre estudo e MVP.

| Tabela | Etapa | Conteúdo |
|---|---|---|
| `clinicas` | 2 | Tenant e configuração como dado (tom de voz, regras, horário, telefone de plantão da recepção) |
| `profissionais`, `servicos`, `profissional_servicos`, `horarios_trabalho` | 2 | Base da agenda |
| `regras_agendamento` | 2 | Antecedência mínima e máxima, janela de cancelamento |
| `pacientes_contatos` | 2 | Nome e telefone, sem prontuário |
| `conversas` | 2 | `estado_conversa`, `human_mode`, `contato_id` |
| `mensagens` | 2 | `message_id` com UNIQUE |
| `jobs` | 3 | `type`, `payload`, `status`, `run_at`, `attempts`, `locked_at`, `locked_by`, `last_error` |
| `agendamentos` | 5 | Profissional, serviço, data e hora, status |
| `handoffs` | 2 (schema) e 5 (uso) | Conversa, motivo, notificação enviada, quem assumiu, início e devolução ao bot |
| `conhecimento_clinica` | 8 | Chunks com embedding, `categoria` (permitido/bloqueado) e modelo de embedding |
| `log_auditoria` | 2 (schema) e 7 (uso) | Toda mensagem `clinico_bloqueado` ou `urgencia`, com categoria e texto original |
| `lembretes` | 11 | `enviar_em`, `status`, resposta do paciente |
| `consents` | 2 | Contato, tipo, data, versão do texto, canal. **Vazia até o piloto** |
| `privacy_requests` | 2 | Contato, tipo de pedido, status, datas. **Vazia até o piloto** |
| `usuarios_painel` | 14 | Usuário da clínica, papel, clínica vinculada |

Índice de lembretes pendentes:

```sql
CREATE INDEX idx_lembretes_pendentes ON lembretes (enviar_em) WHERE status = 'pendente';
```

Valores fixos, iguais no estudo e no MVP:

- **Estados da conversa:** `idle`, `coletando_info`, `aguardando_confirmacao`, `escalada`, `encerrada`.
- **Status de job:** `pending`, `processing`, `done`, `failed`, `dead`.
- **Tipos de job:** `PROCESS_INBOUND_MESSAGE`, `SEND_WHATSAPP`, `SEND_REMINDER`, `NOTIFY_HANDOFF`.
- **Categorias de intenção:** `administrativo`, `agendamento`, `clinico_bloqueado`, `urgencia`, `ambiguo`.
- **Ferramentas expostas ao modelo:** `verificar_disponibilidade`, `criar_agendamento`, `cancelar`, `buscar_duvida_frequente`.

## 8. Fluxos principais

### 8.1 Mensagem recebida

```
Mensagem (WhatsApp ou CLI)
 ↓
Channel.receive → grava em mensagens (message_id UNIQUE; duplicada é ignorada)
 ↓
Cria job PROCESS_INBOUND_MESSAGE (pending) e confirma recebimento

[worker]
 ↓
SELECT ... FROM jobs ... FOR UPDATE SKIP LOCKED                  trava do job
 ↓
SELECT estado_conversa FROM conversas WHERE id = ... FOR UPDATE  trava da conversa
 ↓
Se human_mode = true → não responde; a mensagem aparece no painel
 ↓
Classificação (categoria + confiança)
 ├─ administrativo / agendamento  → RAG / function calling
 ├─ clinico_bloqueado             → mensagem fixa + handoff + log_auditoria
 ├─ urgencia                      → mensagem de segurança fixa + handoff urgente + log_auditoria
 └─ ambiguo, ou confiança < 0,7   → 1 esclarecimento → handoff se persistir
 ↓
Channel.send_text(...)
 ↓
UPDATE estado_conversa; COMMIT; job = done
```

As duas travas resolvem problemas diferentes. `SKIP LOCKED` impede que dois workers peguem o mesmo job. `FOR UPDATE` na conversa impede que duas mensagens da mesma conversa sejam processadas ao mesmo tempo.

Nas etapas 3 a 5 a classificação é por regra determinística. A IA entra na etapa 6, por cima do motor de estados que já funciona.

### 8.2 Lembretes

Regra de antecedência, aplicada quando o agendamento é confirmado:

| Momento | Quando se aplica | Conteúdo | Ação esperada do paciente |
|---|---|---|---|
| T-7 dias | Consulta marcada com 7 dias ou mais de antecedência | Pede confirmação e oferece remarcação | Confirmar, remarcar ou cancelar |
| T-1 dia | Consulta marcada com mais de 1 dia de antecedência (com ou sem T-7) | Confirmação curta | Confirmar, remarcar ou cancelar |
| Confirmação imediata | Consulta marcada com menos de 1 dia de antecedência | Confirma o horário no momento do agendamento | Não há lembrete futuro |

Fluxo:

```
Agendamento confirmado → aplica a regra de antecedência e cria registros em lembretes

[varredura, a cada 15 min, role scheduler_service]
 ↓
ReminderService.buscar_pendentes() → lembretes com enviar_em <= agora e status 'pendente'
 ↓
Para cada um: cria job SEND_REMINDER (run_at = agora) e marca como 'enfileirado'
 ↓
[worker] ReminderService.send_reminder(...) → Channel.send_template(...)
 ↓
Resposta do paciente → classificação restrita (confirmar / cancelar / remarcar / dúvida)
 ↓
Sem resposta ao T-7 → nenhum lembrete adicional; o próximo passo é o T-1
Sem resposta ao T-1 → handoff para a recepção (seção 8.4)
```

Regras complementares:

- **Consultas marcadas entre 1 e 7 dias de antecedência** recebem só o T-1, porque o T-7 já passou no momento do agendamento.
- **Remarcação:** os lembretes pendentes da consulta anterior são cancelados, e a regra é aplicada de novo à nova data.
- **Cancelamento pelo paciente:** cancela os lembretes pendentes.
- **Janela de cancelamento:** para o T-1 permitir reaproveitar a vaga, a janela de cancelamento de cada clínica precisa ser maior que 1 dia (Q-13).
- **Testes:** cada regra tem teste unitário, incluindo os casos de borda (7 dias exatos, 1 dia exato e menos de 1 dia).

O envio concorrente com `asyncio.gather` resolve o gargalo de volume. Celery entra só quando o envio ficar lento o bastante para não caber no ciclo de 15 minutos.

### 8.3 Escopo clínico

Três camadas, em ordem:

1. **Ferramentas.** O modelo só pode chamar as quatro ferramentas da seção 7. Não existe ferramenta para responder sobre saúde.
2. **Classificação com confiança.** Antes de gerar texto livre, a mensagem é classificada. Confiança abaixo de 0,7 vira `ambiguo`. A assimetria é deliberada: na dúvida, o sistema escala em vez de responder.
3. **Mensagens fixas.** `clinico_bloqueado` e `urgencia` respondem com texto aprovado previamente, idealmente revisado por alguém com formação clínica antes do piloto. Exemplo:

> "Essa é uma pergunta que só [nome da clínica] pode responder com segurança. Vou te conectar com a recepção agora."

**Linha de corte:** se a resposta muda conforme o estado de saúde da pessoa, é fora do escopo. Se é igual para qualquer paciente, é administrativo.

**Conteúdo de RAG.** Cada chunk de `conhecimento_clinica` tem `categoria`. A busca filtra por `tenant_id` e por categoria permitida antes da similaridade, para que um FAQ mal escrito pela clínica não vire fonte de resposta clínica.

### 8.4 Handoff e painel

Um handoff é aberto quando: a mensagem é `clinico_bloqueado` ou `urgencia`, a conversa cai em `escalada`, ou o paciente não é entendido após o esclarecimento.

```
Handoff aberto → grava em handoffs e muda estado_conversa para 'escalada'
 ↓
Job NOTIFY_HANDOFF → envia template ao WhatsApp pessoal da recepção de plantão
 (número em clinicas.telefone_plantao; inclui motivo e link para a conversa no painel)
 ↓
Recepção abre o painel e lê o histórico
 ↓
"Assumir conversa" → human_mode = true. O bot para de responder nesta conversa.
 ↓
Recepção responde pelo painel → sai pelo número oficial da clínica
 ↓
"Devolver ao bot" ou encerramento → human_mode = false; registra fim no handoff
```

Pontos que precisam ficar claros:

- **A conversa não sai do número oficial.** A conversa do paciente continua no número da Cloud API, e a recepção responde pelo painel. O WhatsApp pessoal serve só para avisar e levar ao painel. Se a intenção for que a recepção converse diretamente pelo WhatsApp pessoal, isso é outro produto, fora do MVP (Q-18).
- **Janela de 24 horas.** Se a recepção responder depois de 24 horas da última mensagem do paciente, a resposta só é aceita com template aprovado pela Meta. O painel precisa avisar isso.
- **Notificação com template.** O aviso ao WhatsApp pessoal da recepção também é um template aprovado, porque é mensagem iniciada pelo negócio.
- **Cada tentativa de handoff é registrada** em `handoffs`, incluindo quem foi notificado, quando, e quem assumiu.

## 9. Ambientes, deploy e testes

### 9.1 Ambientes

| Ambiente | Banco | Canal | IA e embeddings | Hospedagem | Dado |
|---|---|---|---|---|---|
| Desenvolvimento local | Postgres + pgvector em Docker, RLS ativo | CLI | LLM via API direta; embeddings via Bedrock | Máquina local | Fictício |
| Demo (vídeo) | Supabase Free | Número de teste da Meta | Bedrock | Lightsail | Fictício |
| Piloto | Supabase Pro | Número real via Embedded Signup | Bedrock | Lightsail | Real, com controles de LGPD ativos |

A troca entre ambientes é feita por configuração, sem mudança de código, porque as implementações são trocadas atrás das interfaces.

O ambiente local precisa de credencial IAM de permissão mínima, com acesso ao modelo de embeddings e ao Haiku no Bedrock. Essa credencial não é a do usuário root.

### 9.2 Deploy

1. Cada commit na branch principal gera uma imagem Docker com tag do hash do commit.
2. A pipeline roda os testes. Falha bloqueia o deploy.
3. Migrations rodam antes da troca da imagem, com a role de migração.
4. A imagem nova sobe na Lightsail por script (SSH + `docker compose`).
5. Rollback: subir novamente a tag anterior. No piloto, é feito snapshot da instância antes de cada deploy.

### 9.3 Testes

| Tipo | O que cobre | Quando roda |
|---|---|---|
| Unitários | Regras de agendamento (conflito, duplicidade, antecedência, janela de cancelamento), regras de lembrete (T-7, T-1, consultas com menos de 7 dias, remarcação), transições de estado | Toda mudança |
| Integração | Fila, `SKIP LOCKED`, deduplicação, persistência, handoff | Toda mudança |
| Concorrência | Dois workers no mesmo job; mensagens seguidas da mesma conversa sem agendamento duplicado | CI |
| Isolamento | Consulta de uma clínica nunca retorna dado de outra, com RLS ativo, em todas as tabelas com `tenant_id`, inclusive pelo painel | CI. Obrigatório antes de qualquer piloto |
| Painel | Usuário de uma clínica não vê conversas, agenda nem handoffs de outra | CI |
| Avaliação de IA | 30 a 50 conversas simuladas e conjunto de tentativas de desvio. Métricas: acerto de intenção, recall de `clinico_bloqueado` e `urgencia` (falso negativo é o erro mais caro), escalonamento correto, custo e latência | Sob demanda e antes de mudar prompt ou modelo. Reexecutada após a migração para o Bedrock |

## 10. Escopo do MVP

| Dentro do MVP | Fora do MVP |
|---|---|
| Atendimento via WhatsApp com agente de IA | Adaptadores de Google Calendar, iClinic e Feegow |
| Agendamento, remarcação e cancelamento | Celery e Redis |
| Lembretes T-7 e T-1 com regras de borda | Multi-AZ e VPC privada |
| RAG por clínica com filtro de categoria | Conversa transferida para o WhatsApp pessoal da recepção |
| Handoff com notificação e takeover pelo painel | Deploy em containers gerenciados e autoscaling |
| **Painel de monitoramento** com agenda, conversas, handoffs e métricas | Observabilidade dedicada (Langfuse etc.) |
| Login do painel, com acesso restrito à própria clínica | Fluxo self-service de conexão de WhatsApp |
| Resumo diário pelo WhatsApp da recepção | Tela de consentimento, wording jurídico e atendimento automatizado de pedidos de privacidade (depois do piloto) |
| Configuração por clínica como dado | Valores comerciais (definidos depois do desenvolvimento) |
| Schema de consentimento e direitos do titular, ainda vazio | MCP e prompt caching como requisitos (são opcionais) |
| Teste de isolamento entre clínicas | |

## 11. Plano de construção

A ordem é por dependência. Não há prazo. Quando a etapa estiver pronta, passa-se para a próxima que tiver as dependências atendidas. A numeração é a mesma do plano de estudo v1.2.

### Fase A: núcleo sem IA (estudo)

| Etapa | Entrega | Depende de |
|---|---|---|
| 0 | Escopo, clínica fictícia, FAQ, lista de perguntas clínicas que o agente nunca responde | — |
| 1 | Repositório, Docker Compose, `/health`, pytest, CI | 0 |
| 2 | Schema multi-tenant, RLS ativo, role de worker, tabelas `handoffs`, `consents`, `privacy_requests` e `log_auditoria` (`consents` e `privacy_requests` vazias), teste de isolamento | 1 |
| 3 | Canal CLI, fila de jobs, worker | 2 |
| 4 | Motor de estados sem IA, lock por conversa | 3 |
| 5 | Agendamento e handoff determinísticos | 4 |

### Fase B: inteligência artificial (estudo)

| Etapa | Entrega | Depende de |
|---|---|---|
| 6 | `LLMClient` com API direta da Anthropic (Haiku); registro de tokens e latência | 4 |
| 7 | Classificação com confiança, mensagens fixas, `auditoria/` gravando `log_auditoria` | 5 e 6 |
| 8 | RAG por clínica com `BedrockEmbeddingClient` (Cohere). Teste de recuperação com 20 a 30 perguntas reais antes da carga completa (Q-01) | 2 e 6 |
| 9 | Function calling sobre o motor de estados | 5, 7 e 8 |
| 10 | Suíte de avaliação; comparação pontual com Sonnet | 7 a 9 |
| 11 | Lembretes T-7 e T-1: varredura, jobs, regras de borda, remarcação e escalonamento sem resposta | 5 |
| 12 | Endurecimento: concorrência e isolamento consolidados; prompt caching se houver ganho medido | 10 e 11 |

### Fase C: painel e handoff (MVP)

| Etapa | Entrega | Depende de |
|---|---|---|
| 13 | Handoff completo: abertura, notificação ao WhatsApp pessoal da recepção, `human_mode`, takeover e devolução ao bot. Template de notificação | 7 e 12 |
| 14 | Painel de monitoramento: login, usuários, agenda, conversas, handoffs e métricas; isolamento entre clínicas no painel | 13 e Q-17 definida |

### Fase D: migração e go-live (MVP)

| Etapa | Entrega | Depende de |
|---|---|---|
| 15 | Migração para Supabase: projeto novo, migrations, RLS, role de worker validada (Q-02), pooler testado com locks (Q-03), restauração de backup testada | 12 |
| 16 | Migração para Bedrock: `BedrockClient` com identificador exato do modelo, reexecução da suíte de avaliação, comparação com o resultado do estudo | 10 e 15 |
| 17 | `WhatsAppClient`: Cloud API, webhook com assinatura, templates, teste com número de teste da Meta | 13 |
| 18 | Deploy na Lightsail: container, script de deploy, snapshot, rollback testado | 15, 16 e 17 |
| 19 | Demo gravada com dados fictícios | 18 |
| 20 | Pré-piloto: Business Verification, templates aprovados, Embedded Signup assistido, forma jurídica (Q-14), plano Pro e Secrets Manager. A Business Verification começa durante a etapa 17 | 18 e 19 |
| 21 | Piloto com clínicas reais. Metas de sucesso definidas antes (Q-15) | 20 |

**Observações sobre a ordem.** A etapa 20 começa antes do fim da 17, porque a verificação da Meta corre fora do controle do time. A etapa 14 depende da definição da tecnologia do painel (Q-17), que deve ser decidida até a etapa 13.

## 12. Operação, segurança e LGPD

**Fundação técnica (agora).** Criptografia em trânsito e em repouso, isolamento por tenant com RLS, minimização de dado (sem prontuário), log de auditoria, controle de acesso, retenção zero na IA, segredos fora do código.

**Formalização (com o piloto real).** Contrato de tratamento de dados com cada clínica, com a lista de subprocessadores (Meta, AWS e Supabase). Política de privacidade. Encarregado de dados. Fluxo formal de consentimento, que preenche a tabela `consents`. Procedimento para pedidos de privacidade, que usa `privacy_requests`.

**Credenciais.** Tokens da Meta ficam no Secrets Manager, por clínica, obtidos pelo fluxo oficial de autorização. Existe um processo mínimo de reconexão para quando um token expirar ou for revogado. A credencial IAM da aplicação tem permissão mínima e é rotacionada, porque a Lightsail não assume roles IAM.

**Acesso ao painel.** Cada usuário pertence a uma clínica e só enxerga os dados dela. O acesso é protegido por login, e o papel do usuário define o que ele pode fazer (por exemplo, ver ou também assumir conversas).

**Conta e titularidade.** A conta AWS é dedicada ao projeto, com um e-mail operacional, não pessoal, controlado pelos dois sócios. O mesmo endereço é usado no Business Manager da Meta, no Supabase e na Lightsail. O usuário root tem MFA e não é usado no dia a dia. Alertas de cobrança (AWS Budgets) vão para esse endereço. Um CNPJ não é necessário para desenvolvimento e demo, mas passa a ser necessário antes do piloto pago (Q-14).

**Backup.** Plano Pro do Supabase, com backup diário e retenção de 7 dias. A restauração é testada antes do piloto.

**Multicliente.** Cada clínica tem o próprio número de WhatsApp, sob o mesmo Business Manager na Meta. Um único webhook atende todas as clínicas, identificando a clínica pelo `phone_number_id`. A clínica é dona do número e do histórico; o time é operador autorizado.

**Monitoramento.** Métricas da Lightsail para infraestrutura. Log estruturado para produto: taxa de confirmação de lembrete, taxa de agendamento concluído pelo agente, taxa de handoff, latência média e custo médio por conversa. Essas métricas aparecem no painel da clínica.

## 13. Custos

Esta seção trata só da infraestrutura. Mensalidade e preços comerciais são definidos depois do desenvolvimento (D-30). Câmbio de referência: US$1 = R$5,10. Valores de planos de terceiros devem ser confirmados nas páginas oficiais antes do piloto.

| Cenário | Composição | Total |
|---|---|---|
| Demo | Lightsail (~US$5–10), Supabase Free, WhatsApp de teste, Bedrock incluindo embeddings (~US$5) | ~R$50–75/mês |
| Piloto (central) | Lightsail (~US$7), Supabase Pro (US$25), WhatsApp (US$10–14), Bedrock incluindo embeddings (US$10–14), Secrets Manager (US$1–2 para 2 a 4 clínicas) | ~R$270–315/mês |
| Piloto (desvio) | Lightsail (~US$12), Supabase Pro + compute (~US$40), WhatsApp (~US$15), Bedrock (~US$50), Secrets Manager (~US$2) | ~R$655/mês |

**Sobre o Bedrock.** Não há custo fixo: paga-se por token processado, no Haiku e no Cohere Embed. Indexar os FAQs de uma clínica custa centavos, uma vez, e cada pergunta de paciente é uma frase curta. Os preços por milhão de tokens devem ser conferidos na página oficial antes de fechar o orçamento. O Secrets Manager cobra uma taxa mensal por segredo guardado. Como há um token da Meta por clínica, esse custo cresce com o número de clínicas.

**Ponto de atenção.** O cenário de desvio ultrapassa o teto de R$600 (Q-10). As alavancas, em ordem: acompanhar o custo médio por conversa desde a etapa 6; ativar prompt caching; fazer upgrade de compute do Supabase só com dado de latência que justifique; e, se o teto for rígido, decidir entre reduzir o plano no início do piloto, voltar ao RDS ou reajustar o teto.

## 14. Questões em aberto

Estas questões não bloqueiam as etapas 0 a 5. A coluna "Responder até" indica a etapa em que precisam de resposta.

| # | Questão | Responder até |
|---|---|---|
| Q-01 | Validações do Cohere Embed Multilingual v3: (a) disponibilidade na região e preço atual por token; (b) retenção zero também para embeddings, já que a pergunta do paciente passa por eles; (c) teste de recuperação com 20 a 30 perguntas reais contra o FAQ fictício. Se (c) falhar, alternativa é o Titan Text Embeddings V2 | Etapa 8 |
| Q-02 | Permissão de BYPASSRLS para a role de worker no Supabase, ou alternativa com conexão de serviço separada | Etapa 15 |
| Q-03 | Compatibilidade do pooler do Supabase (modo transação) com `SELECT ... FOR UPDATE` e `SKIP LOCKED` | Etapa 4 (teste de concorrência) e 15 |
| Q-04 | Disponibilidade da restrição de IP de origem no plano Pro | Etapa 15 |
| Q-05 | Número de tentativas de esclarecimento antes de abrir handoff (hoje: 1) | Etapa 10 |
| Q-06 | Threshold de confiança (hoje: 0,7) | Etapa 10 |
| Q-07 | Rigor da classificação clínica: 100% LLM, 100% regra ou híbrida | Etapa 10 |
| Q-08 | Conjunto de tentativas de desvio (perguntas disfarçadas de hipotéticas, "é só curiosidade") | Etapa 10 |
| Q-09 | Revisão clínica das mensagens fixas | Etapa 20 |
| Q-10 | Teto de custo: R$600 é rígido ou reajustável | Antes do piloto |
| Q-11 | Prazo real da verificação de negócio na Meta | Etapa 17 |
| Q-12 | Valores exatos de mensagem por país na Meta | Etapa 20 |
| Q-13 | Janela de cancelamento por clínica: precisa ser maior que 1 dia para o T-1 permitir reaproveitar a vaga. Definir o padrão e o que acontece quando a clínica pede mais | Etapa 11 |
| Q-14 | Forma jurídica para o piloto pago: MEI ou ME no Simples Nacional. Depende do faturamento previsto, do número de sócios e das atividades permitidas. Consultar contador | Etapa 20 |
| Q-15 | **Metas de sucesso do piloto.** Não definidas agora. Precisam existir antes da etapa 21, com linha de base e prazo de medição | Etapa 21 |
| Q-16 | **Valores comerciais:** mensalidade e taxa de implantação. Definidos após o desenvolvimento | Após a etapa 19 |
| Q-17 | **Tecnologia e autenticação do painel.** Opções a comparar: Next.js com autenticação do próprio Supabase, ou FastAPI com templates e autenticação própria. Decidir com a etapa 13 | Etapa 13 |
| Q-18 | **Conversa no WhatsApp pessoal:** confirmar se o modelo do MVP é o de notificar a recepção e responder pelo painel (D-29), ou se a recepção precisa conversar diretamente pelo WhatsApp pessoal, o que seria outro produto | Antes da etapa 13 |

## 15. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Falso negativo em classificação clínica (mensagem clínica tratada como administrativa) | Alto: risco de saúde e reputacional | Assimetria do threshold, mensagens fixas, recall medido na suíte de avaliação, auditoria |
| Vazamento entre clínicas por erro de aplicação, inclusive no painel | Alto | RLS, role de worker separada, teste de isolamento obrigatório cobrindo o painel |
| Agendamento duplicado por concorrência | Médio | Duas travas (`SKIP LOCKED` e `FOR UPDATE`), testes de concorrência |
| Handoff sem resposta da recepção | Alto para o paciente | Notificação com template, lembrete de handoff sem resposta em X minutos (a definir), handoff registrado com quem foi avisado |
| Expectativa de que a recepção converse pelo WhatsApp pessoal | Médio: mudança de produto | Esclarecer antes da etapa 13 (Q-18) |
| Sem VPC privada no banco | Médio | TLS, allowlist de IP, credencial rotacionada, RLS |
| Credencial IAM guardada na Lightsail | Médio | Permissão mínima, rotação, sem acesso administrativo |
| Custo acima do teto | Médio | Métrica de custo por conversa, prompt caching, decisão antecipada |
| Demora na verificação da Meta | Alto para o piloto | Início durante a etapa 17 |
| Escopo crescer antes da etapa 10 | Alto | Ordem por dependência; integrações externas fora do MVP |
| Núcleo gerado por assistente em vez de escrito à mão | Médio para o aprendizado | Núcleo escrito pela pessoa; assistentes revisam e sugerem testes |
| Piloto sem metas definidas | Alto para a decisão de seguir ou parar | Q-15 é pré-requisito da etapa 21 |
| Sigilo do documento e do código | Médio | Publicar só o núcleo genérico; regras e detalhes do produto ficam privados |

## 16. Glossário

| Termo | Definição |
|---|---|
| Tenant | Uma clínica dentro do sistema compartilhado |
| RLS | Row Level Security: regra do próprio Postgres que filtra linhas por usuário ou papel |
| BYPASSRLS | Atributo de role que ignora RLS; usado só pelo worker |
| `SKIP LOCKED` | Cláusula que pula linhas já travadas por outro processo, usada na fila de jobs |
| `FOR UPDATE` | Trava de linha em transação, usada para serializar mensagens da mesma conversa |
| Job | Unidade de trabalho na tabela `jobs`, processada pelo worker |
| Handoff | Transferência da conversa para a recepção humana, com takeover pelo painel |
| `human_mode` | Indica que a conversa está com a recepção; o bot não responde nela |
| Embedding | Representação vetorial de um texto, usada na busca por similaridade |
| RAG | Retrieval-Augmented Generation: o modelo responde com base em trechos recuperados da base da clínica |
| Function calling | Mecanismo em que o modelo pede a execução de uma ferramenta definida pelo sistema |
| WABA | WhatsApp Business Account: conta que reúne números e templates |
| phone_number_id | Identificador do número da clínica, usado para rotear mensagens |
| Template | Mensagem pré-aprovada pela Meta para contato fora da janela de 24 horas |
| Janela de 24 horas | Período após a última mensagem do paciente em que o negócio pode responder livremente |
| Embedded Signup | Fluxo oficial da Meta para a clínica conectar seu número ao app |
| Business Verification | Verificação de negócio da Meta, pré-requisito para número de produção |
| Supavisor | Pooler de conexões do Supabase |
