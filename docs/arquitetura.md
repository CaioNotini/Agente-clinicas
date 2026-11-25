```
Papel: Fonte única das decisões técnicas (D-xx), modelo de dados e questões em aberto (Q-xx).
Entrada: docs/status.md
Relaciona-se com: estudo.md, etapas.md, decisions/0001-alembic.md, decisions/0002-contas-de-banco.md, status.md
```

# Arquitetura do MVP: agente de agendamento para clínicas via WhatsApp

Outubro de 2026 · versão 2.1 · documento de referência para os sócios e para o desenvolvimento · alinhado ao plano de estudo v1.2

---

## 1. Resumo

O produto é um agente de IA que atende clínicas pelo WhatsApp. Ele agenda, remarca e cancela consultas, envia lembretes para reduzir no-show e responde dúvidas administrativas. Não faz orientação clínica.

A clínica acompanha tudo por um **painel de monitoramento**: vê a agenda, o histórico das conversas e as métricas, e assume uma conversa quando o agente encaminha o caso para o responsável pelo atendimento humano. Quando há handoff, esse responsável é avisado no WhatsApp pessoal de plantão, com link direto para a conversa no painel. O responsável é configurado pela clínica e pode ser uma recepção ou o próprio profissional, porque consultórios de um profissional só fazem parte do público-alvo ([ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md)).

A arquitetura é um backend Python (FastAPI) com um worker que processa mensagens a partir de uma fila no PostgreSQL. Cada mensagem é classificada, passa por uma máquina de estados explícita com lock por conversa, e só então aciona o modelo de IA (Claude Haiku) por meio de ferramentas determinísticas. Regras de negócio ficam em código comum e testado. A IA interpreta e redige. Um único banco PostgreSQL (Supabase no MVP) atende todas as clínicas, com `tenant_id` em toda tabela e Row Level Security.

O MVP é construído a partir do **projeto de estudo**. Os módulos, interfaces, tabelas e nomes são os mesmos nos dois. A migração troca implementações atrás das interfaces e não reescreve o núcleo. O plano de estudo é a base do MVP: a mesma sequência de etapas leva do estudo ao produto.

## 2. Premissas

| Fator                       | Situação                                                                           |
| --------------------------- | ---------------------------------------------------------------------------------- |
| Time                        | 2 desenvolvedores part-time. Um deles também está cursando duas graduações         |
| Orçamento de infraestrutura | Teto de R$600/mês enquanto não houver cliente pagante                              |
| Dado tratado                | Dado de saúde, sensível pela LGPD. Estudo, testes e demo usam apenas dado fictício |
| Cronograma                  | Tratado por ordem de dependência, sem prazo fixo                                   |
| Valores comerciais          | Mensalidade e preços serão definidos depois do desenvolvimento                     |
| Metas de sucesso            | Não definidas agora. Ficam como questão em aberto (Q-15)                           |

Princípio que guia todas as decisões: **simples o bastante para uma pessoa operar, desenhado para não precisar de reescrita ao crescer para multicliente.**

## 3. Decisões

Decisões com status **Travada** não são revisitadas sem nova versão deste documento. Decisões **Em aberto** estão na seção 13.

| ID   | Decisão                                                                                                                                                                                                                                                         | Status                                        | Alternativa descartada e motivo                                                                                                                                                                                |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D-01 | Backend em Python + FastAPI                                                                                                                                                                                                                                     | Travada                                       | Node/TypeScript: o time domina Python, e o estudo é em Python                                                                                                                                                  |
| D-02 | PostgreSQL com pgvector como único banco. Docker no estudo, Supabase no MVP                                                                                                                                                                                     | Travada                                       | Banco de vetor separado: mais um serviço para operar                                                                                                                                                           |
| D-03 | Banco único multi-tenant, com `tenant_id` em toda tabela desde o primeiro dia                                                                                                                                                                                   | Travada                                       | Banco ou schema por cliente: custo e operação incompatíveis com o orçamento. Revisável se um contrato exigir                                                                                                   |
| D-04 | Row Level Security ativo desde o início, no estudo e no MVP, com teste de isolamento obrigatório                                                                                                                                                                | Travada                                       | Confiar só na aplicação: um bug de filtro vazaria dado entre clínicas                                                                                                                                          |
| D-05 | Role de worker com BYPASSRLS, usada só pelo processo de jobs e pela varredura de lembretes. Nunca em código que atende requisição                                                                                                                               | Travada (validação no Supabase, Q-02)         | Worker com a role da aplicação: não enxerga jobs de todas as clínicas                                                                                                                                          |
| D-06 | Fila de jobs em tabela PostgreSQL com `SKIP LOCKED` e deduplicação por `mensagens.id`                                                                                                                                                                           | Travada                                       | Celery + Redis: mais infraestrutura. Gatilho de migração: segunda instância da aplicação                                                                                                                       |
| D-07 | Lock por conversa com `SELECT ... FOR UPDATE`                                                                                                                                                                                                                   | Travada                                       | Fila FIFO por conversa: mais complexa, sem ganho no volume de piloto                                                                                                                                           |
| D-08 | Estado explícito em `conversas.estado_conversa`, com 5 estados                                                                                                                                                                                                  | Travada                                       | Estado inferido pelo LLM a cada mensagem: custo de tokens e ambiguidade                                                                                                                                        |
| D-09 | Classificação em categoria fechada + score de confiança. Abaixo de 0,7 vira `ambiguo`                                                                                                                                                                           | Travada (threshold a calibrar, Q-06)          | Só rótulo sem confiança: não trata casos de fronteira                                                                                                                                                          |
| D-10 | `clinico_bloqueado` e `urgencia` respondem com mensagem fixa aprovada, nunca gerada                                                                                                                                                                             | Travada                                       | Resposta gerada pelo LLM: risco de recusa parcialmente clínica e de variação não auditável                                                                                                                     |
| D-11 | Ferramentas determinísticas. A lista de ferramentas é a barreira de escopo                                                                                                                                                                                      | Travada                                       | Modelo livre com regras no prompt: não é verificável                                                                                                                                                           |
| D-12 | Orquestração própria sobre a API do modelo, sem LangChain                                                                                                                                                                                                       | Travada                                       | LangChain/LangGraph: abstrações difíceis de depurar, dependências pesadas e quebras entre versões                                                                                                              |
| D-13 | Claude Haiku. No estudo via API direta da Anthropic. No MVP via AWS Bedrock, com retenção zero travada por conta/projeto. Modelo configurável por `LLM_MODEL` ([ADR 0010](./decisions/0010-llmclient.md))                                                                                                                                        | Travada                                       | API direta no MVP: retenção depende de contrato empresarial. Modelos da linha Mythos/Fable exigem compartilhamento de dados no Bedrock, portanto não são usados. Sonnet só para comparação pontual na etapa 10 |
| D-14 | Embeddings: Cohere Embed Multilingual v3 via AWS Bedrock, nos dois ambientes, dimensão 1024                                                                                                                                                                     | Travada (validações na etapa 8, Q-01)         | Modelo local via Ollama: indisponível no Bedrock, o que obrigaria reindexação na migração. Titan Text Embeddings V2: alternativa se a validação falhar                                                         |
| D-15 | WhatsApp Cloud API direto pela Meta, sem BSP                                                                                                                                                                                                                    | Travada                                       | BSP (Twilio, 360dialog, Zenvia): mensalidade de plataforma                                                                                                                                                     |
| D-16 | Canal CLI no estudo, atrás da interface `Channel`                                                                                                                                                                                                               | Travada                                       | não se aplica                                                                                                                                                                                                              |
| D-17 | Agendamento atrás de `AgendaProvider`. `AgendaPropria` é o padrão. Adaptadores externos só sob demanda de cliente real                                                                                                                                          | Travada                                       | Integração com Google Calendar, iClinic ou Feegow desde o início: esforço alto sem cliente pedindo                                                                                                             |
| D-18 | Lembretes em T-7 dias (pede confirmação e oferece remarcação) e T-1 dia (confirmação curta), com regras para consultas marcadas com menos de 7 dias (seção 8.2). Tabela `lembretes` é a fonte da verdade. Varredura a cada 15 minutos cria jobs `SEND_REMINDER` | Travada                                       | Job por lembrete no APScheduler: perde agendamentos se a aplicação reiniciar                                                                                                                                   |
| D-19 | Hospedagem da aplicação na Lightsail, instância única, container Docker                                                                                                                                                                                         | Travada                                       | Elastic Beanstalk e EC2 com Auto Scaling: mais peças AWS para um piloto de instância única                                                                                                                     |
| D-20 | Observabilidade: métricas da Lightsail (infra) e log estruturado no Postgres (produto e agente)                                                                                                                                                                 | Travada                                       | Stack dedicada de observabilidade: mais um serviço para manter                                                                                                                                                 |
| D-21 | Supabase Free na demo, Pro no piloto com dado real                                                                                                                                                                                                              | Travada                                       | Free no piloto: sem backup diário e com pausa por inatividade                                                                                                                                                  |
| D-22 | **Painel de monitoramento no MVP** (substitui a decisão anterior de não ter painel). A clínica vê agenda, conversas, handoffs e métricas, e assume conversas. Resumo diário pelo WhatsApp continua como complemento                                             | Travada (revisa a versão 2.0 deste documento) | Sem painel: o responsável pelo atendimento não teria como acompanhar nem assumir conversas                                                                                                                     |
| D-23 | Sem Multi-AZ e sem VPC privada no banco. Conexão TLS com restrição de IP de origem quando disponível                                                                                                                                                            | Travada (tradeoff aceito)                     | RDS em VPC: custo e operação que o orçamento não comporta                                                                                                                                                      |
| D-24 | Tokens da Meta no AWS Secrets Manager. Credencial IAM de permissão mínima na Lightsail, rotacionada                                                                                                                                                             | Travada                                       | Token em variável de ambiente ou planilha: risco de segurança                                                                                                                                                  |
| D-25 | Escopo clínico: o produto é atendimento administrativo. Qualquer orientação de saúde está fora                                                                                                                                                                  | Travada                                       | não se aplica                                                                                                                                                                                                              |
| D-26 | Tabelas `handoffs`, `consents` e `privacy_requests` criadas no schema inicial. `consents` e `privacy_requests` ficam vazias até o piloto                                                                                                                        | Travada                                       | Criar depois: reconstruir consentimento retroativamente não é auditável                                                                                                                                        |
| D-27 | Dado fictício em todo ambiente de estudo, testes e demo                                                                                                                                                                                                         | Travada                                       | não se aplica                                                                                                                                                                                                              |
| D-28 | Cronograma por ordem de dependência, sem prazo. Não há estimativa de semanas                                                                                                                                                                                    | Travada                                       | Calendário fixo: não reflete a disponibilidade part-time                                                                                                                                                       |
| D-29 | Handoff com notificação no WhatsApp pessoal do responsável configurado pela clínica de plantão (recepção ou o próprio profissional, [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md)). A resposta ao paciente é feita no painel, e sai pelo número oficial da clínica (ver seção 8.4)                                                | Travada                                       | Transferir a conversa para o WhatsApp pessoal: a conversa da Cloud API não pode sair do número oficial                                                                                                         |
| D-30 | Valores comerciais (mensalidade, taxa de implantação) definidos após o desenvolvimento                                                                                                                                                                          | Travada                                       | não se aplica                                                                                                                                                                                                              |
| D-31 | Metas de sucesso do piloto não definidas agora                                                                                                                                                                                                                  | Em aberto (Q-15)                              | não se aplica                                                                                                                                                                                                              |

## 4. Stack

| Camada                 | MVP                                                     | Projeto de estudo                                  | Ponto de troca                              |
| ---------------------- | ------------------------------------------------------- | -------------------------------------------------- | ------------------------------------------- |
| Backend                | Python + FastAPI                                        | Python + FastAPI                                   | não se aplica                                           |
| Banco                  | PostgreSQL + pgvector no Supabase, RLS ativo            | PostgreSQL + pgvector em Docker Compose, RLS ativo | String de conexão, migrations               |
| Fila                   | Tabela `jobs` + worker com `SKIP LOCKED`                | Igual                                              | não se aplica                                           |
| IA                     | Claude Haiku via AWS Bedrock                            | Claude Haiku via API direta da Anthropic           | `BedrockClient` substitui `AnthropicClient` |
| Embeddings             | Cohere Embed Multilingual v3 via Bedrock                | Igual                                              | não se aplica                                           |
| Canal                  | WhatsApp Cloud API                                      | CLI                                                | `WhatsAppClient` substitui `CliChannel`     |
| Painel                 | Aplicação web para a clínica (Q-17 define a tecnologia) | Painel mínimo na etapa 14, mesma tecnologia        | não se aplica                                           |
| Autenticação do painel | A definir (Q-17), com tabela `usuarios_painel`          | Igual                                              | não se aplica                                           |
| Execução               | Container Docker na Lightsail, instância única          | Docker Compose local                               | Deploy                                      |
| Segredos               | AWS Secrets Manager                                     | Arquivo `.env` fora do repositório                 | Leitura de segredos                         |
| Observabilidade        | Métricas da Lightsail + log estruturado no Postgres     | Log estruturado no Postgres                        | não se aplica                                           |
| Testes e CI            | pytest, CI, teste de isolamento entre clínicas          | pytest, CI, teste de isolamento entre clínicas     | não se aplica                                           |

## 5. Arquitetura de componentes

```
                    ┌─────────────────────────────┐
  Paciente ──────►  │ WhatsApp (Meta Cloud API)   │ ◄── Responsável (painel)
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

| Processo                        | Credencial de banco                  | Acesso à AWS                                         |
| ------------------------------- | ------------------------------------ | ---------------------------------------------------- |
| API e painel (requisições)      | Role da aplicação, sujeita a RLS     | Bedrock e Secrets Manager, via credencial IAM mínima |
| Worker e varredura de lembretes | Role `worker_jobs` com BYPASSRLS     | Igual                                                |
| Migrations                      | Role de migração, usada só no deploy | Não usa                                              |

O worker usa `worker_jobs` só para a fila de jobs. Escritas específicas de clínica feitas pelo worker passam por sessão da role da aplicação, sujeita a RLS. Ver [ADR 0002](./decisions/0002-contas-de-banco.md).

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
│   └── db/              # modelos (migrations do Alembic ficam na raiz do repo, ver ADR 0001)
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

| Interface         | Responsabilidade                                                           | Estudo                   | MVP                      | Etapa  |
| ----------------- | -------------------------------------------------------------------------- | ------------------------ | ------------------------ | ------ |
| `Channel`         | Receber e enviar mensagem. Enviar template fora da janela de 24h           | `CliChannel`             | `WhatsAppClient`         | 3 e 17 |
| `LLMClient`       | Completar com ferramentas e saída estruturada. Registrar tokens e latência | `AnthropicClient`        | `BedrockClient`          | 6 e 16 |
| `EmbeddingClient` | Gerar embeddings e registrar o modelo usado                                | `BedrockEmbeddingClient` | `BedrockEmbeddingClient` | 8      |
| `AgendaProvider`  | Disponibilidade por expediente e ocupação, criar, cancelar, ler e listar   | `AgendaPropria`          | `AgendaPropria`          | 5      |
| `ReminderService` | Enviar lembrete e registrar resposta                                       | Igual                    | Igual                    | 11     |

O `LLMClient` normaliza o formato de resposta e de chamada de ferramenta. O restante do código não sabe qual provedor está por trás. Contrato, erros e configuração no [ADR 0010](./decisions/0010-llmclient.md).

O `AgendaProvider` é a porta de persistência da agenda e não aplica regras de negócio. A disponibilidade dele responde só o que uma agenda externa também saberia: os inícios livres segundo o expediente e a ocupação do profissional. As regras da clínica, como antecedência mínima e máxima, são aplicadas por cima pelo serviço de agendamento ([`app/agenda/servico.py`](../app/agenda/servico.py), tarefa 5.3).

## 7. Modelo de dados

Um banco, `tenant_id` em toda tabela. Nomes idênticos entre estudo e MVP.

| Tabela                                                                    | Etapa                | Conteúdo                                                                                       |
| ------------------------------------------------------------------------- | -------------------- | ---------------------------------------------------------------------------------------------- |
| `clinicas`                                                                | 2 (base) e 5 (config de fuso e handoff) | Tenant e configuração como dado (tom de voz, regras, horário, telefone de plantão, `fuso` IANA, `handoff_prazo_resposta_minutos`, `handoff_texto_paciente`). O telefone de plantão é do responsável pelo atendimento humano configurado pela clínica, recepção ou o próprio profissional ([ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md)) |
| `profissionais`, `servicos`, `profissional_servicos`, `horarios_trabalho` | 2 (base) e 5 (`profissional_servicos.duracao_minutos`) | Base da agenda. `servicos.duracao_minutos` é a duração padrão, e `profissional_servicos.duracao_minutos` é o override opcional por profissional (Q-21) |
| `regras_agendamento`                                                      | 2 (base) e 5 (política de cancelamento) | Antecedência mínima e máxima, janela de cancelamento, `politica_cancelamento_fora_janela` (`handoff` ou `aceitar_e_marcar`, Q-22) |
| `pacientes_contatos`                                                      | 2                    | Nome e telefone, sem prontuário                                                                |
| `conversas`                                                               | 2                    | `estado_conversa`, `human_mode`, `contato_telefone`                                            |
| `mensagens`                                                               | 2                    | `mensagens.id` como chave primária                                                             |
| `jobs`                                                                    | 2 (schema) e 3 (uso) | `type`, `payload`, `contato_telefone`, `status`, `run_at`, `attempts`, `locked_at`, `locked_by`, `last_error`. Ordem por conversa no [ADR 0005](./decisions/0005-ordem-por-conversa.md) |
| `agendamentos`                                                            | 5                    | `profissional_id`, `servico_id`, `contato_telefone`, `inicio`, `fim`, `status`, `cancelado_fora_da_janela` (marca de cancelamento tardio, Q-22) |
| `handoffs`                                                                | 2 (schema) e 5 (uso) | Conversa, motivo, destino previsto do aviso (`notificado_para`, `notificado_canal`) e envio confirmado (`notificado_em`, Q-24), texto informado ao paciente (`texto_paciente`), limite de resposta (`responder_ate`), agendamento e mensagem de origem (`agendamento_id`, `mensagem_id`), quem assumiu, início e devolução ao bot ([ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md)) |
| `conhecimento_clinica`                                                    | 8                    | Chunks com embedding, `categoria` (permitido/bloqueado) e modelo de embedding                  |
| `log_auditoria`                                                           | 2 (schema) e 7 (uso) | Toda mensagem `clinico_bloqueado` ou `urgencia`, com categoria e texto original                |
| `lembretes`                                                               | 11                   | `enviar_em`, `status`, resposta do paciente                                                    |
| `consents`                                                                | 2                    | Contato, tipo, data, versão do texto, canal. **Vazia até o piloto**                            |
| `privacy_requests`                                                        | 2                    | Contato, tipo de pedido, status, datas. **Vazia até o piloto**                                 |
| `usuarios_painel`                                                         | 14                   | Usuário da clínica, papel, clínica vinculada                                                   |

Índice de lembretes pendentes:

```sql
CREATE INDEX idx_lembretes_pendentes ON lembretes (enviar_em) WHERE status = 'pendente';
```

Em `agendamentos`, as colunas `inicio` e `fim` usam `timestamptz`, com os instantes gravados em UTC. As colunas de tempo com fuso no schema são `agendamentos.inicio`, `agendamentos.fim` e `handoffs.responder_ate`. As demais usam `timestamp` sem fuso. O conflito de horário entre agendamentos ativos do mesmo profissional é garantido por uma constraint `EXCLUDE` com intervalo semiaberto `[inicio, fim)`, descrita no [ADR 0004](./decisions/0004-conflito-de-horario.md).

O armazenamento é sempre em UTC, mas as regras de antecedência, janela de cancelamento e lembretes usam o fuso da clínica, definido em `clinicas.fuso` como nome IANA (default `America/Sao_Paulo`). A conversão para o fuso da clínica fica numa função única, e o nome do fuso é validado na leitura: um fuso inválido vira `ConfiguracaoInvalida`. Hoje a aplicação não grava `clinicas.fuso` (Q-23, [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md)).

**Regras de agendamento (tarefa 5.2).** São funções puras em [`app/agenda/regras.py`](../app/agenda/regras.py), aplicadas pelo serviço de agendamento antes de gravar. Cada violação levanta um erro de domínio da família `RegraViolada`. O serviço aplica as regras na ordem antecedência, expediente, duplicidade e conflito, e para na primeira violação. A duplicidade vem antes do conflito para que o contato que pede um horário sobreposto ao que ele já tem receba `AgendamentoDuplicado`, mesmo com o mesmo profissional, e não `HorarioIndisponivel` (decisão de 2026-11-23).

- **Antecedência.** Um início igual ou anterior ao momento do pedido é recusado (`HorarioNoPassado`). A mínima compara dois instantes, em horas (`AntecedenciaInsuficiente`). A máxima compara datas no fuso da clínica: a data local do início não pode passar da data local de hoje somada a `antecedencia_maxima_dias` (`AntecedenciaExcedida`).
- **Expediente.** O intervalo `[inicio, fim)`, convertido para o fuso da clínica, precisa caber inteiro numa faixa ativa de `horarios_trabalho` do profissional no mesmo dia da semana (`ForaDoExpediente`). Faixas contíguas ou sobrepostas do mesmo dia valem como uma só, então 08:00 às 12:00 e 12:00 às 18:00 aceitam uma consulta das 11:30 às 12:30. Um intervalo que atravessa a meia-noite local é recusado.
- **Duplicidade.** O mesmo contato não pode ter dois agendamentos ativos com intervalos sobrepostos, com qualquer profissional (`AgendamentoDuplicado`). Horários que não se sobrepõem são permitidos, inclusive com o mesmo profissional e o mesmo serviço, para não bloquear consultas de retorno.
- **Conflito.** Dois agendamentos ativos do mesmo profissional conflitam se os intervalos semiabertos se sobrepõem (`HorarioIndisponivel`). É a mesma semântica da constraint `EXCLUDE` do [ADR 0004](./decisions/0004-conflito-de-horario.md), que continua sendo a barreira sob concorrência.
- **Pedido repetido.** Se o contato pede exatamente o que já tem (mesmo profissional, mesmo início, agendamento ativo), o serviço devolve o agendamento existente, sem erro e sem gravar outro. Vale na verificação prévia e na corrida que chega ao banco como `23P01` ([ADR 0004](./decisions/0004-conflito-de-horario.md)). `AgendamentoDuplicado` fica só para outro horário sobreposto do mesmo contato. Na remarcação o pedido repetido não vale: se o novo início coincide com outro agendamento ativo do mesmo contato, com qualquer profissional, o serviço levanta `AgendamentoDuplicado`, na verificação prévia e no `23P01`, e o antigo continua ativo. O novo horário pode se sobrepor ao próprio antigo, porque o cancelamento do antigo vem antes, na mesma transação (decisão de 2026-11-24, item C7 do [diagnóstico da rodada 4](./diagnosticos/2026-11-24-rodada4.md)).
- **Passo da disponibilidade.** Os inícios oferecidos andam de uma duração em uma duração a partir do início de cada faixa de expediente, com as faixas contíguas juntas. A limitação é que horários quebrados não são oferecidos: com faixa às 08:00 e duração de 45 minutos, os inícios são 08:00, 08:45 e 09:30, e uma brecha que comece às 09:10 depois de um cancelamento fica de fora. Um pedido direto para esse horário continua sendo aceito, porque a criação valida o intervalo pedido, não a grade.
- **Janela de cancelamento.** Antecedência maior ou igual à janela é cancelamento normal. Fora da janela, vale a política da clínica (Q-22). Cancelar um horário que já passou é recusado (`HorarioNoPassado`).
- **Configuração nula ou ausente.** Uma coluna nula em `regras_agendamento` desliga a regra correspondente. Já a clínica sem linha em `regras_agendamento`, o profissional sem nenhuma faixa ativa de expediente, uma faixa ativa incompleta ou invertida e um valor negativo são erro de cadastro (`ConfiguracaoInvalida`). Esse erro fica fora da família `RegraViolada`, porque não deve virar resposta de horário indisponível ao paciente. O serviço de agendamento o converte em handoff com motivo `configuracao_invalida`, sem referência ao agendamento pedido, e registra um log estruturado de erro com `tenant_id` e o tipo do erro, sem dados do paciente (tarefa 5.4).
- **Segunda barreira de isolamento.** As verificações de conflito e duplicidade recusam uma lista de agendamentos com mais de uma clínica (`MisturaDeTenants`), antes de aplicar a regra. A barreira principal é o RLS na carga. Esse erro indica bug, fica fora de `RegraViolada` e de `ConfiguracaoInvalida` e nunca vira resposta ao paciente.
- **Texto ao paciente.** O que vai ao paciente vem só de mensagens fixas ([`app/mensagens/fixas.py`](../app/mensagens/fixas.py)) ou da configuração da clínica. O texto de uma exceção nunca vai ao paciente, porque pode repetir ids e falar de outra clínica.

A duplicidade não tem constraint no banco. Ela é segura sem constraint porque a ordem por conversa ([ADR 0005](./decisions/0005-ordem-por-conversa.md)) e o lock da conversa serializam todos os pedidos do mesmo contato: um pedido só é verificado depois de o anterior do mesmo contato ter sido confirmado ou desfeito. A ressalva é que essa serialização só vale para o que entra pela fila de mensagens. Entradas futuras que gravem agendamentos por outro caminho, como o painel (etapa 14) ou uma agenda externa atrás do `AgendaProvider` (D-17), não passam por ela e precisam de uma barreira própria quando existirem.

Valores fixos, iguais no estudo e no MVP:

- **Estados da conversa:** `idle`, `coletando_info`, `aguardando_confirmacao`, `escalada`, `encerrada`.
- **Status de job:** `pending`, `processing`, `done`, `dead`. O estado `failed` foi removido porque o worker não o usa, e pode voltar com ADR se o backoff exigir.
- **Status de agendamento:** `agendado` e `cancelado`.
- **Tipos de job:** `PROCESS_INBOUND_MESSAGE`, `SEND_WHATSAPP`, `SEND_REMINDER`, `NOTIFY_HANDOFF`.
- **Categorias de intenção:** `administrativo`, `agendamento`, `clinico_bloqueado`, `urgencia`, `ambiguo`.
- **Ferramentas expostas ao modelo:** `verificar_disponibilidade`, `criar_agendamento`, `cancelar`, `buscar_duvida_frequente`.

## 8. Fluxos principais

### 8.1 Mensagem recebida

```
Mensagem (WhatsApp ou CLI)
 ↓
Channel.receive → grava em mensagens (mensagens.id é a chave primária, com o identificador da mensagem na Meta. Duplicada é ignorada)
 ↓
Cria job PROCESS_INBOUND_MESSAGE (pending) e confirma recebimento

[worker]
 ↓
SELECT ... FROM jobs ... FOR UPDATE SKIP LOCKED                  trava do job, sem job anterior pendente da conversa (ADR 0005)
 ↓
SELECT estado_conversa FROM conversas WHERE id = ... FOR UPDATE  trava da conversa
 ↓
Se human_mode = true → não responde. A mensagem aparece no painel
 ↓
Classificação (categoria + confiança)
 ├─ administrativo / agendamento  → RAG / function calling. Sem informação na base → oferece handoff ou seguir no automático
 ├─ clinico_bloqueado             → mensagem fixa + handoff + log_auditoria
 ├─ urgencia                      → mensagem de segurança fixa (192 ou pronto-socorro, incondicional, e CVV 188) + log_auditoria. O handoff é secundário e não é a via de resposta prometida ao paciente
 └─ ambiguo, ou confiança < 0,7   → 1 esclarecimento → handoff se persistir
 ↓
Channel.send_text(...)
 ↓
UPDATE estado_conversa; COMMIT; job = done
```

As duas travas resolvem problemas diferentes. `SKIP LOCKED` impede que dois workers peguem o mesmo job. `FOR UPDATE` na conversa impede que duas mensagens da mesma conversa sejam processadas ao mesmo tempo.

Um job que falha volta para `pending` até `max_attempts`. A exceção é o erro permanente (`ErroPermanente`, em [`app/core/erros.py`](../app/core/erros.py)), como `ConfiguracaoInvalida` e `MisturaDeTenants`. Uma nova tentativa falharia igual e só atrasaria as mensagens seguintes da conversa. O job vai para `dead` na primeira falha, e o worker registra um log estruturado de erro com `tenant_id`, o id do job e o tipo do erro (tarefa 5.4).

O retry que volta para `pending` tem backoff (tarefa 6.4): o `run_at` do job é adiado por um atraso exponencial com teto, com a fórmula e os valores no [ADR 0010](./decisions/0010-llmclient.md). Sem isso, o retry seria imediato e, com a chamada de IA no processamento, geraria rajada de custo. O backoff atua só no retry. O caminho de `dead` e o de `done` não mexem no `run_at`. Pela ordem por conversa do [ADR 0005](./decisions/0005-ordem-por-conversa.md), um `run_at` futuro do job anterior continua bloqueando as mensagens seguintes da conversa, porque a regra de ordem olha o status e não o `run_at`. O efeito prático também está no ADR 0010.

Nas etapas 3 a 5 não há classificação de intenção. A IA entra a partir da etapa 6, por cima do motor de estados que já funciona. A classificação entra na etapa 7, primeiro por regra, como baseline, e depois com LLM. A sequência está em [`etapas.md`](./etapas.md).

### 8.2 Lembretes

Regra de antecedência, aplicada quando o agendamento é confirmado:

| Momento              | Quando se aplica                                                    | Conteúdo                                     | Ação esperada do paciente       |
| -------------------- | ------------------------------------------------------------------- | -------------------------------------------- | ------------------------------- |
| T-7 dias             | Consulta marcada com 7 dias ou mais de antecedência                 | Pede confirmação e oferece remarcação        | Confirmar, remarcar ou cancelar |
| T-1 dia              | Consulta marcada com mais de 1 dia de antecedência (com ou sem T-7) | Confirmação curta                            | Confirmar, remarcar ou cancelar |
| Confirmação imediata | Consulta marcada com menos de 1 dia de antecedência                 | Confirma o horário no momento do agendamento | Não há lembrete futuro          |

Fluxo:

```
Agendamento confirmado → aplica a regra de antecedência e cria registros em lembretes

[varredura, a cada 15 min, role worker_jobs]
 ↓
ReminderService.buscar_pendentes() → lembretes com enviar_em <= agora e status 'pendente'
 ↓
Para cada um: cria job SEND_REMINDER (run_at = agora) e marca como 'enfileirado'
 ↓
[worker] ReminderService.send_reminder(...) → Channel.send_template(...)
 ↓
Resposta do paciente → classificação restrita (confirmar / cancelar / remarcar / dúvida)
 ↓
Sem resposta ao T-7 → nenhum lembrete adicional. O próximo passo é o T-1
Sem resposta ao T-1 → handoff para o responsável configurado pela clínica (seção 8.4)
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
3. **Mensagens fixas.** `clinico_bloqueado` e `urgencia` respondem com texto aprovado previamente, idealmente revisado por alguém com formação clínica antes do piloto.

A de `clinico_bloqueado` não cita recepção e não promete resposta imediata, porque num consultório solo pode não haver ninguém monitorando o handoff na hora. Exemplo:

> "Essa é uma pergunta que só a equipe de [nome da clínica] pode responder com segurança. Vou registrar seu contato para que o responsável pelo atendimento retorne."

A de `urgencia` orienta o paciente a procurar o serviço de emergência de forma incondicional e imediata, e nunca depende do handoff nem usa o texto de handoff da clínica ([ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md)). Exemplo:

> "Se isto for uma emergência, ligue 192 (SAMU) ou procure o pronto-socorro mais próximo agora. Se você está pensando em se machucar, ligue 188 (CVV), a qualquer hora. Este canal não faz atendimento de urgência."

Existe uma única mensagem fixa de `urgencia`. Ela cobre todo risco imediato à vida, inclusive o pensamento de autolesão, e sempre traz o 192 ou o pronto-socorro de forma incondicional e o CVV (188). Não há subcategoria de urgência. Uma subcategoria exigiria que o classificador acertasse também o subtipo, e um erro ali deixaria a pessoa sem o CVV. O texto final é escrito na tarefa 7.3 e revisado na etapa 20.

**Linha de corte:** se a resposta muda conforme o estado de saúde da pessoa, é fora do escopo. Se é igual para qualquer paciente, é administrativo.

**Perguntas administrativas.** Perguntas administrativas e informativas, como valor da consulta particular, reembolso, convênios aceitos, horários, endereço e documentos necessários, são da categoria `administrativo` e nunca `clinico_bloqueado`. O agente responde quando a clínica fornece a informação na configuração ou na base de conhecimento. Quando a informação não existe, o agente não inventa resposta. Ele diz que não tem a informação e oferece ao paciente a escolha entre falar com o responsável pelo atendimento (handoff) ou seguir no atendimento automático. Os casos de teste estão no [FAQ](./fake_clinic/FAQ.md).

**Conteúdo de RAG.** Cada chunk de `conhecimento_clinica` tem `categoria`. A busca filtra por `tenant_id` e por categoria permitida antes da similaridade, para que um FAQ mal escrito pela clínica não vire fonte de resposta clínica.

### 8.4 Handoff e painel

Um handoff é aberto quando: a mensagem é `clinico_bloqueado` ou `urgencia`, a conversa cai em `escalada`, o paciente não é entendido após o esclarecimento, ou o paciente escolhe falar com uma pessoa depois de uma pergunta administrativa sem informação na base (seção 8.3).

O responsável pelo atendimento humano é configurado pela clínica e pode ser uma recepção ou o próprio profissional. O aviso vai para `clinicas.telefone_plantao`, seja de quem for ([ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md)).

```
Handoff aberto → grava em handoffs e muda estado_conversa para 'escalada' (na etapa 5 só grava, ver abaixo)
 ↓
Job NOTIFY_HANDOFF → envia template ao WhatsApp pessoal do responsável de plantão
 (número em clinicas.telefone_plantao. Inclui motivo e link para a conversa no painel)
 ↓
Responsável abre o painel e lê o histórico
 ↓
"Assumir conversa" → human_mode = true. O bot para de responder nesta conversa.
 ↓
Responsável responde pelo painel → sai pelo número oficial da clínica
 ↓
"Devolver ao bot" ou encerramento → human_mode = false. Registra fim no handoff
```

Pontos que precisam ficar claros:

- **A conversa não sai do número oficial.** A conversa do paciente continua no número da Cloud API, e o responsável responde pelo painel. O WhatsApp pessoal serve só para avisar e levar ao painel. Se a intenção for que o responsável converse diretamente pelo WhatsApp pessoal, isso é outro produto, fora do MVP (Q-18).
- **Janela de 24 horas.** Se o responsável responder depois de 24 horas da última mensagem do paciente, a resposta só é aceita com template aprovado pela Meta. O painel precisa avisar isso.
- **Notificação com template.** O aviso ao WhatsApp pessoal do responsável também é um template aprovado, porque é mensagem iniciada pelo negócio.
- **Cada tentativa de handoff é registrada** em `handoffs`, incluindo o destino previsto do aviso (`notificado_para` e `notificado_canal`), quando ele foi de fato enviado (`notificado_em`), e quem assumiu.
- **Na etapa 5 o handoff só é gravado** ([`app/handoff/abertura.py`](../app/handoff/abertura.py)). O estado da conversa e o `human_mode` não mudam, e o aviso ao responsável não é enviado. `notificado_em` fica nulo até a etapa 13. Os motivos gravados nesta etapa são `cancelamento_fora_da_janela` e `configuracao_invalida`. Detalhes no [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md).

## 9. Ambientes, deploy e testes

### 9.1 Ambientes

| Ambiente              | Banco                                    | Canal                           | IA e embeddings                            | Hospedagem    | Dado                               |
| --------------------- | ---------------------------------------- | ------------------------------- | ------------------------------------------ | ------------- | ---------------------------------- |
| Desenvolvimento local | Postgres + pgvector em Docker, RLS ativo | CLI                             | LLM via API direta. Embeddings via Bedrock | Máquina local | Fictício                           |
| Demo (vídeo)          | Supabase Free                            | Número de teste da Meta         | Bedrock                                    | Lightsail     | Fictício                           |
| Piloto                | Supabase Pro                             | Número real via Embedded Signup | Bedrock                                    | Lightsail     | Real, com controles de LGPD ativos |

A troca entre ambientes é feita por configuração, sem mudança de código, porque as implementações são trocadas atrás das interfaces.

O ambiente local precisa de credencial IAM de permissão mínima, com acesso ao modelo de embeddings e ao Haiku no Bedrock. Essa credencial não é a do usuário root.

### 9.2 Deploy

1. Cada commit na branch principal gera uma imagem Docker com tag do hash do commit.
2. A pipeline roda os testes. Falha bloqueia o deploy.
3. Migrations rodam antes da troca da imagem, com a role de migração.
4. A imagem nova sobe na Lightsail por script (SSH + `docker compose`).
5. Rollback: subir novamente a tag anterior. No piloto, é feito snapshot da instância antes de cada deploy.

### 9.3 Testes

| Tipo            | O que cobre                                                                                                                                                                                                           | Quando roda                                                                               |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Unitários       | Regras de agendamento (conflito, duplicidade, antecedência, janela de cancelamento), regras de lembrete (T-7, T-1, consultas com menos de 7 dias, remarcação), transições de estado                                   | Toda mudança                                                                              |
| Integração      | Fila, `SKIP LOCKED`, deduplicação, persistência, handoff                                                                                                                                                              | Toda mudança                                                                              |
| Concorrência    | Dois workers no mesmo job. Mensagens seguidas da mesma conversa sem agendamento duplicado                                                                                                                             | CI                                                                                        |
| Isolamento      | Consulta de uma clínica nunca retorna dado de outra, com RLS ativo, em todas as tabelas com `tenant_id`, inclusive pelo painel                                                                                        | CI. Obrigatório antes de qualquer piloto                                                  |
| Painel          | Usuário de uma clínica não vê conversas, agenda nem handoffs de outra                                                                                                                                                 | CI                                                                                        |
| Avaliação de IA | 30 a 50 conversas simuladas e conjunto de tentativas de desvio. Métricas: acerto de intenção, recall de `clinico_bloqueado` e `urgencia` (falso negativo é o erro mais caro), escalonamento correto, custo e latência | Sob demanda e antes de mudar prompt ou modelo. Reexecutada após a migração para o Bedrock |

**Prazos dos testes de concorrência.** Toda espera interna de um teste de concorrência (`Barrier`, `Event`, cadeia de tentativas e espera das threads) termina antes do limite do pytest, com margem. O prazo vem do pior caso que o próprio código garante, como o `lock_timeout` vezes as tentativas, e o limite do pytest do teste é esse prazo mais a margem. Assim o teste falha pela própria asserção, com o resultado de cada thread, e a limpeza roda. Os valores e a regra ficam em [`tests/concurrency/prazos.py`](../tests/concurrency/prazos.py), e um teste da pasta recusa prazo escrito à mão.

## 10. Escopo do MVP

| Dentro do MVP                                                          | Fora do MVP                                                                                                     |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Atendimento via WhatsApp com agente de IA                              | Adaptadores de Google Calendar, iClinic e Feegow                                                                |
| Agendamento, remarcação e cancelamento                                 | Celery e Redis                                                                                                  |
| Lembretes T-7 e T-1 com regras de borda                                | Multi-AZ e VPC privada                                                                                          |
| RAG por clínica com filtro de categoria                                | Conversa transferida para o WhatsApp pessoal do responsável                                                     |
| Handoff com notificação e takeover pelo painel                         | Deploy em containers gerenciados e autoscaling                                                                  |
| **Painel de monitoramento** com agenda, conversas, handoffs e métricas | Observabilidade dedicada (Langfuse etc.)                                                                        |
| Login do painel, com acesso restrito à própria clínica                 | Fluxo self-service de conexão de WhatsApp                                                                       |
| Resumo diário pelo WhatsApp do responsável                             | Tela de consentimento, wording jurídico e atendimento automatizado de pedidos de privacidade (depois do piloto) |
| Configuração por clínica como dado                                     | Valores comerciais (definidos depois do desenvolvimento)                                                        |
| Schema de consentimento e direitos do titular, ainda vazio             | MCP e prompt caching como requisitos (são opcionais)                                                            |
| Teste de isolamento entre clínicas                                     |                                                                                                                 |

## 11. Plano de construção

Fonte única das etapas 0 a 21, suas entregas e dependências: [`etapas.md`](./etapas.md).
Qualquer decisão técnica (D-xx) ou questão em aberto (Q-xx) citada nas entregas continua definida aqui, na seção 3 e na seção 13.

## 12. Operação, segurança e LGPD

**Fundação técnica (agora).** Criptografia em trânsito e em repouso, isolamento por tenant com RLS, minimização de dado (sem prontuário), log de auditoria, controle de acesso, retenção zero na IA, segredos fora do código.

**Formalização (com o piloto real).** Contrato de tratamento de dados com cada clínica, com a lista de subprocessadores (Meta, AWS e Supabase). Política de privacidade. Encarregado de dados. Fluxo formal de consentimento, que preenche a tabela `consents`. Procedimento para pedidos de privacidade, que usa `privacy_requests`.

**Credenciais.** Tokens da Meta ficam no Secrets Manager, por clínica, obtidos pelo fluxo oficial de autorização. Existe um processo mínimo de reconexão para quando um token expirar ou for revogado. A credencial IAM da aplicação tem permissão mínima e é rotacionada, porque a Lightsail não assume roles IAM.

**Acesso ao painel.** Cada usuário pertence a uma clínica e só enxerga os dados dela. O acesso é protegido por login, e o papel do usuário define o que ele pode fazer (por exemplo, ver ou também assumir conversas).

**Conta e titularidade.** A conta AWS é dedicada ao projeto, com um e-mail operacional, não pessoal, controlado pelos dois sócios. O mesmo endereço é usado no Business Manager da Meta, no Supabase e na Lightsail. O usuário root tem MFA e não é usado no dia a dia. Alertas de cobrança (AWS Budgets) vão para esse endereço. Um CNPJ não é necessário para desenvolvimento e demo, mas passa a ser necessário antes do piloto pago (Q-14).

**Backup.** Plano Pro do Supabase, com backup diário e retenção de 7 dias. A restauração é testada antes do piloto.

**Multicliente.** Cada clínica tem o próprio número de WhatsApp, sob o mesmo Business Manager na Meta. Um único webhook atende todas as clínicas, identificando a clínica pelo `phone_number_id`. A clínica é dona do número e do histórico. O time é operador autorizado.

**Monitoramento.** Métricas da Lightsail para infraestrutura. Log estruturado para produto: taxa de confirmação de lembrete, taxa de agendamento concluído pelo agente, taxa de handoff, latência média e custo médio por conversa. Essas métricas aparecem no painel da clínica.

## 13. Questões em aberto

As questões Q-01 a Q-19 não bloqueiam as etapas 0 a 5. As questões Q-20 a Q-24 eram da especificação da etapa 5 e estão resolvidas: Q-20 pela tarefa 5.5 e Q-21 a Q-24 pelo [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md). A coluna "Responder até" indica a etapa em que precisam de resposta.

| #    | Questão                                                                                                                                                                                                                                                                                                                                         | Responder até                           |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| Q-01 | Validações do Cohere Embed Multilingual v3: (a) disponibilidade na região e preço atual por token, (b) retenção zero também para embeddings, já que a pergunta do paciente passa por eles, (c) teste de recuperação com 20 a 30 perguntas reais contra o FAQ fictício. Se (c) falhar, alternativa é o Titan Text Embeddings V2                  | Etapa 8                                 |
| Q-02 | Permissão de BYPASSRLS para a role de worker no Supabase, ou alternativa com conexão de serviço separada                                                                                                                                                                                                                                        | Etapa 15                                |
| Q-03 | Compatibilidade do pooler do Supabase (modo transação) com `SELECT ... FOR UPDATE` e `SKIP LOCKED`                                                                                                                                                                                                                                              | Etapa 15 (migração para o Supabase)     |
| Q-04 | Disponibilidade da restrição de IP de origem no plano Pro                                                                                                                                                                                                                                                                                       | Etapa 15                                |
| Q-05 | Número de tentativas de esclarecimento antes de abrir handoff (hoje: 1)                                                                                                                                                                                                                                                                         | Etapa 10                                |
| Q-06 | Threshold de confiança (hoje: 0,7)                                                                                                                                                                                                                                                                                                              | Etapa 10                                |
| Q-07 | Rigor da classificação clínica: 100% LLM, 100% regra ou híbrida                                                                                                                                                                                                                                                                                 | Etapa 10                                |
| Q-08 | Conjunto de tentativas de desvio (perguntas disfarçadas de hipotéticas, "é só curiosidade")                                                                                                                                                                                                                                                     | Etapa 10                                |
| Q-09 | Revisão clínica das mensagens fixas                                                                                                                                                                                                                                                                                                             | Etapa 20                                |
| Q-10 | Teto de custo: R$600 é rígido ou reajustável                                                                                                                                                                                                                                                                                                    | Antes do piloto                         |
| Q-11 | Prazo real da verificação de negócio na Meta                                                                                                                                                                                                                                                                                                    | Etapa 17                                |
| Q-12 | Valores exatos de mensagem por país na Meta                                                                                                                                                                                                                                                                                                     | Etapa 20                                |
| Q-13 | Janela de cancelamento por clínica: precisa ser maior que 1 dia para o T-1 permitir reaproveitar a vaga. Definir o padrão e o que acontece quando a clínica pede mais                                                                                                                                                                           | Etapa 11                                |
| Q-14 | Forma jurídica para o piloto pago: MEI ou ME no Simples Nacional. Depende do faturamento previsto, do número de sócios e das atividades permitidas. Consultar contador                                                                                                                                                                          | Etapa 20                                |
| Q-15 | **Metas de sucesso do piloto.** Não definidas agora. Precisam existir antes da etapa 21, com linha de base e prazo de medição                                                                                                                                                                                                                   | Etapa 21                                |
| Q-16 | **Valores comerciais:** mensalidade e taxa de implantação. Definidos após o desenvolvimento                                                                                                                                                                                                                                                     | Após a etapa 19                         |
| Q-17 | **Tecnologia e autenticação do painel.** Opções a comparar: Next.js com autenticação do próprio Supabase, ou FastAPI com templates e autenticação própria. Decidir com a etapa 13                                                                                                                                                               | Etapa 13                                |
| Q-18 | **Conversa no WhatsApp pessoal:** confirmar se o modelo do MVP é o de notificar a recepção e responder pelo painel (D-29), ou se a recepção precisa conversar diretamente pelo WhatsApp pessoal, o que seria outro produto                                                                                                                      | Antes da etapa 13                       |
| Q-19 | **Dedupe de mensagens por `(tenant_id, id)`.** A chave primária de `mensagens` é global, e hoje uma colisão de id entre clínicas levanta `ColisaoIdEntreTenants`. Avaliar quando o id passar a vir da Meta                                                                                                                                      | Etapa 17                                |
| Q-20 | **Paciente no agendamento.** Resolvida pela tarefa 5.5: `agendamentos` guarda `contato_telefone` (seção 7), a mesma chave de `conversas` e de `pacientes_contatos` dentro da clínica                                                                                                                                              | Etapa 5                                 |
| Q-21 | **Duração da consulta.** Resolvida pelo [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md): `servicos.duracao_minutos` é a duração padrão, e `profissional_servicos.duracao_minutos` é o override opcional por profissional. O fim do agendamento usa o override quando ele existe                                                       | Etapa 5 (resolvida)                     |
| Q-22 | **Cancelamento fora da janela.** Resolvida pelo [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md): política configurável por clínica em `regras_agendamento.politica_cancelamento_fora_janela`. `handoff` (padrão) abre handoff e só cancela após decisão humana. `aceitar_e_marcar` cancela na hora e marca `agendamentos.cancelado_fora_da_janela` | Etapa 5 (resolvida)                     |
| Q-23 | **Fuso horário.** Resolvida pelo [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md): fuso por clínica em `clinicas.fuso` (nome IANA, default `America/Sao_Paulo`). As regras de antecedência, janela de cancelamento e lembretes usam o fuso da clínica. O armazenamento continua em UTC, e a conversão fica numa função única. A conversão para exibição ao paciente entra quando houver canal que exiba horário | Etapa 5 (resolvida)                     |
| Q-24 | **Quem foi notificado no handoff.** Resolvida pelo [ADR 0009](./decisions/0009-agendamento-handoff-etapa5.md): `handoffs` ganha `notificado_para` e `notificado_canal`, ao lado de `notificado_em`. O destinatário continua sendo `clinicas.telefone_plantao`                                                                                   | Etapa 5 (resolvida)                     |

## 14. Riscos

| Risco                                                                                  | Impacto                                | Mitigação                                                                                                                    |
| -------------------------------------------------------------------------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Falso negativo em classificação clínica (mensagem clínica tratada como administrativa) | Alto: risco de saúde e reputacional    | Assimetria do threshold, mensagens fixas, recall medido na suíte de avaliação, auditoria                                     |
| Vazamento entre clínicas por erro de aplicação, inclusive no painel                    | Alto                                   | RLS, role de worker separada, teste de isolamento obrigatório cobrindo o painel                                              |
| Agendamento duplicado por concorrência                                                 | Médio                                  | Duas travas (`SKIP LOCKED` e `FOR UPDATE`), testes de concorrência                                                           |
| Handoff sem resposta do responsável                                                    | Alto para o paciente                   | Notificação com template, lembrete de handoff sem resposta em X minutos (a definir), handoff registrado com quem foi avisado. A urgência não depende do handoff (ADR 0009) |
| Expectativa de que o responsável converse pelo WhatsApp pessoal                        | Médio: mudança de produto              | Esclarecer antes da etapa 13 (Q-18)                                                                                          |
| Sem VPC privada no banco                                                               | Médio                                  | TLS, allowlist de IP, credencial rotacionada, RLS                                                                            |
| Credencial IAM guardada na Lightsail                                                   | Médio                                  | Permissão mínima, rotação, sem acesso administrativo                                                                         |
| Custo acima do teto                                                                    | Médio                                  | Métrica de custo por conversa, prompt caching, decisão antecipada                                                            |
| Demora na verificação da Meta                                                          | Alto para o piloto                     | Início durante a etapa 17                                                                                                    |
| Escopo crescer antes da etapa 10                                                       | Alto                                   | Ordem por dependência. Integrações externas fora do MVP                                                                      |
| Piloto sem metas definidas                                                             | Alto para a decisão de seguir ou parar | Q-15 é pré-requisito da etapa 21                                                                                             |
| Sigilo do documento e do código                                                        | Médio                                  | Publicar só o núcleo genérico. Regras e detalhes do produto ficam privados                                                   |
