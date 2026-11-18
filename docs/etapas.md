```
Papel: define as etapas do projeto, o que cada uma entrega, de onde vem sua base e quando é considerada concluída.
Entrada: docs/status.md
Relaciona-se com: status.md, estudo.md, arquitetura.md, principios.md, decisions/README.md
```

# Etapas do projeto

Este arquivo define o plano de construção, do escopo inicial até o piloto com clínicas reais. Ele é a fonte única da sequência de etapas. O estado atual de cada etapa fica somente em [status.md](./status.md).

## Regras deste arquivo

- Este arquivo define o plano. O progresso não é registrado aqui.
- As etapas seguem a ordem de dependência. Uma etapa começa quando todas as que ela depende estão concluídas.
- Cada etapa lista de quais etapas depende e em quais decisões D-xx se apoia.
- Uma etapa só é concluída com evidência salva, como saída de teste, comando executado ou arquivo gerado. A evidência é registrada no `status.md`.
- Datas não decidem progresso. Os marcos agrupam etapas, sem prazo.
- Números de etapas ou tarefas removidas não são reutilizados.
- Tarefas usam a numeração da etapa, como 2.1 e 2.2.

## Marcos

Os marcos agrupam etapas por objetivo. Eles substituem as fases A a D do plano anterior.

| Marco | Nome                                | Etapas  |
| ----- | ----------------------------------- | ------- |
| A     | Núcleo sem inteligência artificial  | 0 a 5   |
| B     | Inteligência artificial e lembretes | 6 a 12  |
| C     | Handoff e painel                    | 13 e 14 |
| D     | Migração e entrega                  | 15 a 18 |
| E     | Demo e piloto                       | 19 a 21 |

## Visão geral

| Etapa | Nome                                       | Marco | Depende de  |
| ----- | ------------------------------------------ | ----- | ----------- |
| 0     | Escopo e base fictícia                     | A     | nenhuma     |
| 1     | Repositório, Docker, health e CI           | A     | 0           |
| 2     | Schema multi-tenant, RLS e isolamento      | A     | 1           |
| 3     | Canal CLI, fila de jobs e worker           | A     | 2           |
| 4     | Motor de estados e lock por conversa       | A     | 3           |
| 5     | Agendamento e handoff determinísticos      | A     | 4           |
| 6     | LLMClient com API direta                   | B     | 4           |
| 7     | Classificação, mensagens fixas e auditoria | B     | 5 e 6       |
| 8     | RAG por clínica                            | B     | 2 e 6       |
| 9     | Function calling sobre o motor de estados  | B     | 5, 7 e 8    |
| 10    | Suíte de avaliação                         | B     | 7, 8 e 9    |
| 11    | Lembretes T-7 e T-1                        | B     | 5           |
| 12    | Endurecimento de concorrência e isolamento | B     | 10 e 11     |
| 13    | Handoff completo e notificação             | C     | 7 e 12      |
| 14    | Painel de monitoramento                    | C     | 13          |
| 15    | Migração para Supabase                     | D     | 12          |
| 16    | Migração para Bedrock                      | D     | 10 e 15     |
| 17    | WhatsAppClient                             | D     | 13          |
| 18    | Deploy na Lightsail                        | D     | 15, 16 e 17 |
| 19    | Demo gravada                               | E     | 18          |
| 20    | Pré-piloto                                 | E     | 19          |
| 21    | Piloto                                     | E     | 20          |

---

## Marco A: núcleo sem inteligência artificial

### Etapa 0: escopo e base fictícia

- **Depende de:** nenhuma.
- **Base:** D-25, D-27, Q-08 e Q-13.
- **Objetivo:** criar a clínica fictícia, as perguntas frequentes e a lista de perguntas que o agente nunca responde. Esse conteúdo é usado como corpus do RAG e como casos de teste.
- **Tarefas:**
  - 0.1 `clinica.md`, com profissionais, horários, convênios e regras de agendamento.
  - 0.2 `FAQ.md`, com cada pergunta marcada como permitido ou bloqueado.
  - 0.3 `pergs_bloqueadas.md`, preenchido pelo Caio.
- **Código:** nenhum. Os arquivos ficam em [fake_clinic/](./fake_clinic/).
- **Critério de pronto:**
  - os três arquivos existem e seguem o cabeçalho de relações.
  - cada pergunta do FAQ tem categoria.
  - a lista de perguntas bloqueadas tem ao menos uma pergunta para `clinico_bloqueado` e uma para `urgencia`, incluindo uma forma indireta.
  - nenhum dado parece real.
- **Fora do escopo:** respostas clínicas. As mensagens fixas são revisadas na etapa 20.

### Etapa 1: repositório, Docker, health e CI

- **Depende de:** etapa 0.
- **Base:** seção 4 da arquitetura.
- **Objetivo:** ter o repositório executável, com banco em Docker, rota de saúde, testes e integração contínua.
- **Tarefas:**
  - 1.1 `docker-compose.yml` com o Postgres.
  - 1.2 rota `GET /health`.
  - 1.3 testes com pytest.
  - 1.4 pipeline de CI.
- **Código:** `docker-compose.yml`, `app/main.py`, `tests/test_health.py`, `.github/workflows/ci.yml`.
- **Critério de pronto:** `/health` responde, os testes passam localmente e a pipeline passa no GitHub.
- **Fora do escopo:** banco com schema, que começa na etapa 2.

### Etapa 2: schema multi-tenant, RLS e isolamento

- **Depende de:** etapa 1.
- **Base:** D-02, D-03, D-04, D-05, D-14, D-26.
- **Objetivo:** criar todas as tabelas do modelo, com `tenant_id`, e garantir que uma clínica não lê nem altera dados de outra, mesmo com erro no código da aplicação.
- **Tarefas:**
  - 2.1 extensão pgvector, com imagem e migration.
  - 2.2 tabelas faltantes, em duas migrations.
  - 2.3 role do worker, com BYPASSRLS. Criada como `scheduler_service`, sem login, e substituída por `worker_jobs`, com login, conforme [ADR 0002](./decisions/0002-contas-de-banco.md).
  - 2.4 RLS, FORCE e policy `isolamento_tenant` em todas as tabelas com `tenant_id`.
  - 2.5 teste de isolamento com a conta da aplicação.
  - 2.6 separação de contas por papel, com a role `app_clinicas` criada por migration e a senha definida no CI a partir de secret.
- **Código:** `migrations/versions/`, `app/config.py`, `app/db/`, `tests/isolation/`.
- **Critério de pronto:**
  - cada migration sobe, desce e sobe de novo sem erro.
  - o schema tem as tabelas esperadas.
  - toda tabela com `tenant_id` tem RLS, FORCE e policy.
  - o teste de isolamento passa com a conta `app_clinicas`.
  - ao desligar o RLS de propósito, os testes de leitura e de escrita falham.
  - a pipeline passa no GitHub com a mesma imagem do Docker local.
- **Fora do escopo:** definição do tenant por rota HTTP, que começa na etapa 13.

### Etapa 3: canal CLI, fila de jobs e worker

- **Depende de:** etapa 2.
- **Base:** D-06, D-07, D-16 e seção 8.1 da arquitetura.
- **Objetivo:** receber mensagens pelo terminal, gravá-las e processá-las com um worker, sem inteligência artificial. Receber e processar são etapas separadas, ligadas pela fila no banco.
- **Tarefas:**
  - 3.1 canal CLI, implementando a interface `Channel`.
  - 3.2 gravação em `mensagens` e criação de job, com deduplicação pela chave primária.
  - 3.3 worker com `SKIP LOCKED`, controle de tentativas e status `dead`.
- **Código:** `app/channels/`, `app/jobs/`, `tests/concurrency/`.
- **Critério de pronto:**
  - teste com dois workers disputando o mesmo job, em que apenas um processa.
  - teste de mensagem duplicada, que não gera segundo processamento.
  - teste de job que vai para `dead` após as tentativas.
  - saída dos testes registrada no `status.md`.
- **Fora do escopo:** inteligência artificial (etapa 6) e WhatsApp (etapa 17).

### Etapa 4: motor de estados e lock por conversa

- **Depende de:** etapa 3.
- **Base:** D-07, D-08 e seção 8.1 da arquitetura.
- **Objetivo:** controlar o estado de cada conversa com transições explícitas, e impedir que duas mensagens da mesma conversa sejam processadas ao mesmo tempo.
- **Tarefas:**
  - 4.1 estados `idle`, `coletando_info`, `aguardando_confirmacao`, `escalada` e `encerrada`, com transições determinísticas.
  - 4.2 lock por conversa com `SELECT ... FOR UPDATE`.
  - 4.3 teste de mensagens seguidas da mesma conversa.
  - 4.4 escritas específicas de clínica feitas pelo worker passam por sessão `app_clinicas` com RLS, mantendo o filtro de `tenant_id` como segunda barreira, conforme [ADR 0002](./decisions/0002-contas-de-banco.md).
- **Código:** `app/core/`, `tests/concurrency/`.
- **Critério de pronto:** transições inválidas são rejeitadas, e o teste de mensagens seguidas não gera processamento fora de ordem nem duplicidade.
- **Fora do escopo:** classificação de intenção.

### Etapa 5: agendamento e handoff determinísticos

- **Depende de:** etapa 4.
- **Base:** D-11, D-17, D-29, seções 7 e 8.4 da arquitetura, Q-20 a Q-24.
- **Objetivo:** agendar, remarcar e cancelar com regras em código, e registrar handoffs quando necessário.
- **Tarefas:**
  - 5.5 tabela `agendamentos`, executada antes da 5.1. Migration, classe no modelo, constraint EXCLUDE de conflito, policy `isolamento_tenant`, entrada em `TABELAS_TENANT` e cobertura nos testes de isolamento. Colunas e conflito no [ADR 0004](./decisions/0004-conflito-de-horario.md).
  - 5.1 interface `AgendaProvider` e implementação `AgendaPropria`.
  - 5.2 regras de conflito, duplicidade, antecedência e janela de cancelamento.
  - 5.3 criação, remarcação e cancelamento de agendamentos.
  - 5.4 abertura de handoff na tabela `handoffs`. Nesta etapa só grava, sem mudar o estado da conversa.
- **Código:** `migrations/versions/`, `app/db/models.py`, `app/agenda/`, `app/handoff/`, `tests/unit/`, `tests/integration/`, `tests/concurrency/`, `tests/isolation/`.
- **Critério de pronto:** cada regra tem teste unitário, incluindo os casos de borda, e um handoff gravado aparece no banco.
- **Fora do escopo:** notificação real à recepção, que começa na etapa 13.

---

## Marco B: inteligência artificial e lembretes

### Etapa 6: LLMClient com API direta

- **Depende de:** etapa 4.
- **Base:** D-12, D-13 e seção 6 da arquitetura.
- **Objetivo:** chamar o modelo por uma interface única, registrando tokens e latência de cada chamada.
- **Tarefas:**
  - 6.1 interface `LLMClient`.
  - 6.2 implementação `AnthropicClient` com Claude Haiku.
  - 6.3 registro de tokens e latência no log estruturado.
  - 6.4 backoff no retry de jobs, porque retry imediato com chamada de IA gera rajada de custo.
- **Código:** `app/llm/`, `tests/unit/`.
- **Critério de pronto:** o formato de resposta é testado com dublê, e uma chamada real registra tokens e latência.
- **Atenção:** chamadas reais geram custo. Elas só são feitas com autorização prévia do Caio, conforme o orçamento do estudo.
- **Fora do escopo:** Bedrock, que começa na etapa 16.

### Etapa 7: classificação, mensagens fixas e auditoria

- **Depende de:** etapas 5 e 6.
- **Base:** D-09, D-10, D-25 e seção 8.3 da arquitetura.
- **Objetivo:** classificar cada mensagem com confiança, responder a casos clínicos e de urgência com texto fixo, e registrar tudo na auditoria.
- **Tarefas:**
  - 7.1 classificação por regra, como baseline.
  - 7.2 classificação com LLM, retornando categoria e confiança.
  - 7.3 mensagens fixas para `clinico_bloqueado` e `urgencia`.
  - 7.4 registro em `log_auditoria`.
- **Código:** `app/classification/`, `app/auditoria/`, `tests/unit/`.
- **Critério de pronto:**
  - toda mensagem `clinico_bloqueado` ou `urgencia` gera registro de auditoria.
  - confiança abaixo de 0,7 resulta em `ambiguo`.
  - os casos da lista de perguntas bloqueadas são testados.
- **Fora do escopo:** revisão clínica das mensagens fixas, que acontece na etapa 20.

### Etapa 8: RAG por clínica

- **Depende de:** etapas 2 e 6.
- **Base:** D-14, seção 8.3 da arquitetura e Q-01.
- **Objetivo:** responder dúvidas administrativas com base no conteúdo da própria clínica.
- **Tarefas:**
  - 8.1 `BedrockEmbeddingClient` com Cohere Embed Multilingual v3.
  - 8.2 chunking e tabela `conhecimento_clinica`, com `categoria`.
  - 8.3 busca filtrada por `tenant_id` e por categoria permitida.
  - 8.4 teste de recuperação com 20 a 30 perguntas reais.
- **Código:** `app/embeddings/`, `app/rag/`, `tests/isolation/`.
- **Critério de pronto:**
  - a busca nunca retorna trecho de outro tenant, verificado pelo teste de isolamento.
  - trechos marcados como bloqueado nunca são retornados.
  - a taxa de recuperação do teste de 20 a 30 perguntas é registrada.
- **Fora do escopo:** o downgrade da extensão `vector` precisa ser revisto nesta etapa, porque a tabela com coluna `vector` impede o `DROP EXTENSION`.

### Etapa 9: function calling sobre o motor de estados

- **Depende de:** etapas 5, 7 e 8.
- **Base:** D-11, seção 7 da arquitetura.
- **Objetivo:** permitir que o modelo execute ações apenas por meio das quatro ferramentas aprovadas.
- **Tarefas:**
  - 9.1 definição das ferramentas `verificar_disponibilidade`, `criar_agendamento`, `cancelar` e `buscar_duvida_frequente`.
  - 9.2 ligação das ferramentas ao motor de estados.
  - 9.3 prompt reduzido nos estados `coletando_info` e `aguardando_confirmacao`.
- **Código:** `app/tools/`, `tests/unit/`.
- **Critério de pronto:** uma chamada fora da lista de ferramentas é rejeitada, e os fluxos de agendamento passam nos testes.
- **Fora do escopo:** novas ferramentas sem atualização desta lista.

### Etapa 10: suíte de avaliação

- **Depende de:** etapas 7, 8 e 9.
- **Base:** seção 9.3 da arquitetura, Q-05, Q-06, Q-07 e Q-08.
- **Objetivo:** medir a qualidade do agente com um conjunto fixo de conversas, para tomar decisões com dado.
- **Tarefas:**
  - 10.1 conversas simuladas em `eval/`.
  - 10.2 conjunto de tentativas de desvio.
  - 10.3 script `run_eval.py` com as métricas.
  - 10.4 comparação pontual com Sonnet.
- **Código:** `eval/`.
- **Critério de pronto:**
  - o script roda com um comando e registra os resultados com data.
  - o recall de `clinico_bloqueado` e `urgencia` é registrado.
  - Q-05, Q-06 e Q-07 são decididas com base nos resultados.

### Etapa 11: lembretes T-7 e T-1

- **Depende de:** etapa 5.
- **Base:** D-18, seção 8.2 da arquitetura e Q-13.
- **Objetivo:** enviar lembretes com a regra de antecedência, tratar remarcação e cancelamento, e escalar quando não houver resposta.
- **Tarefas:**
  - 11.1 regra de antecedência para consultas com 7 dias ou mais, entre 1 e 7 dias e com menos de 1 dia.
  - 11.2 tabela `lembretes` com índice de pendentes.
  - 11.3 varredura a cada 15 minutos, criando jobs `SEND_REMINDER`.
  - 11.4 remarcação recalcula os lembretes, e cancelamento os remove.
  - 11.5 abertura de handoff quando não há resposta ao T-1.
- **Código:** `app/reminders/`, `tests/unit/`, `tests/concurrency/`.
- **Critério de pronto:** testes dos casos de borda (7 dias exatos, 1 dia exato e menos de 1 dia), de remarcação e de escalonamento passam.
- **Atenção:** o valor da janela de cancelamento precisa ser maior que 1 dia para o T-1 ter utilidade (Q-13).

### Etapa 12: endurecimento de concorrência e isolamento

- **Depende de:** etapas 10 e 11.
- **Base:** D-04, D-05, D-06, D-07 e seção 9.3 da arquitetura.
- **Objetivo:** consolidar os testes que protegem o sistema contra falhas de concorrência e de isolamento, incluindo tarefas assíncronas.
- **Tarefas:**
  - 12.1 testes de concorrência reunidos e executados no CI.
  - 12.2 isolamento verificado também para jobs e lembretes.
  - 12.3 prompt caching, somente se o ganho for medido.
- **Código:** `tests/concurrency/`, `tests/isolation/`.
- **Critério de pronto:** os testes de concorrência e isolamento passam no CI, qualquer ganho de prompt caching fica registrado com medição, e os itens de "Estudo pronto" em [estudo.md, seção 9](./estudo.md#9-critério-de-pronto-e-readme) estão atendidos.

---

## Marco C: handoff e painel

### Etapa 13: handoff completo e notificação

- **Depende de:** etapas 7 e 12.
- **Base:** D-29, seção 8.4 da arquitetura e Q-18.
- **Objetivo:** abrir handoffs com motivo, notificar a recepção, pausar o bot na conversa e devolvê-la ao bot quando a recepção terminar.
- **Tarefas:**
  - 13.1 abertura de handoff com motivo. Inclui a transição da conversa para `escalada`, validada pelo grafo de [`decisions/0003-grafo-de-transicoes.md`](./decisions/0003-grafo-de-transicoes.md). A etapa 5 só grava o handoff, sem mudar o estado.
  - 13.2 job `NOTIFY_HANDOFF`, com canal simulado no estudo.
  - 13.3 `human_mode` e devolução ao bot.
- **Código:** `app/handoff/`, `tests/unit/`.
- **Critério de pronto:**
  - um handoff aberto cria o job de notificação.
  - uma conversa com `human_mode` ativo não recebe resposta do bot, verificado por teste.
  - a devolução ao bot registra o fim do handoff.

### Etapa 14: painel de monitoramento

- **Depende de:** etapa 13 e a decisão de Q-17.
- **Base:** D-22, seção 5 e seção 12 da arquitetura.
- **Objetivo:** permitir que a clínica veja agenda, conversas, handoffs e métricas, e assuma conversas.
- **Tarefas:**
  - 14.1 registro da tecnologia do painel em ADR.
  - 14.2 login e tabela `usuarios_painel`.
  - 14.3 telas de agenda, conversas, handoffs e métricas.
  - 14.4 teste de isolamento para o painel.
- **Código:** `app/painel/`, `app/auth/`, `tests/isolation/`.
- **Critério de pronto:** um usuário de uma clínica não vê dados de outra pela interface, verificado por teste, e um handoff pode ser assumido pelo painel.

---

## Marco D: migração e entrega

### Etapa 15: migração para Supabase

- **Depende de:** etapa 12.
- **Base:** D-02, D-21, D-23, D-24 e seção 8 da arquitetura.
- **Objetivo:** mover o banco para o Supabase sem alterar o schema nem as regras de isolamento.
- **Tarefas:**
  - 15.1 projeto Supabase no plano Free para testes.
  - 15.2 aplicação das migrations.
  - 15.3 validação de BYPASSRLS para `worker_jobs` (Q-02).
  - 15.4 validação do pooler em modo transação com os locks (Q-03).
  - 15.5 teste de restauração de backup.
- **Critério de pronto:** as migrations sobem no Supabase, a suíte de isolamento passa contra ele, os testes de lock passam e a restauração é registrada.
- **Atenção:** o plano Pro só é contratado no piloto (D-21).

### Etapa 16: migração para Bedrock

- **Depende de:** etapas 10 e 15.
- **Base:** D-13, D-14 e Q-01.
- **Objetivo:** trocar o provedor do modelo para o Bedrock, mantendo a mesma suíte de avaliação.
- **Tarefas:**
  - 16.1 `BedrockClient` com o identificador exato do modelo.
  - 16.2 validação de retenção zero também para embeddings (Q-01, item b).
  - 16.3 reexecução da suíte de avaliação.
  - 16.4 comparação com o resultado do estudo.
- **Código:** `app/llm/bedrock_client.py`.
- **Critério de pronto:** a suíte roda no Bedrock, e o recall de `clinico_bloqueado` e `urgencia` não cai em relação ao estudo.

### Etapa 17: WhatsAppClient

- **Depende de:** etapa 13.
- **Base:** D-15, seções 4 e 12 da arquitetura.
- **Objetivo:** receber e enviar mensagens pela Cloud API da Meta, usando o fluxo já construído.
- **Tarefas:**
  - 17.1 envio e recebimento pela Cloud API.
  - 17.2 validação da assinatura `X-Hub-Signature-256`.
  - 17.3 submissão dos templates de lembrete e de notificação.
  - 17.4 teste com o número de teste da Meta.
  - 17.5 avaliar dedupe de mensagens por `(tenant_id, id)` (Q-19), quando o id passa a vir da Meta.
- **Código:** `app/channels/whatsapp.py`, `tests/unit/`.
- **Critério de pronto:** uma mensagem recebida pelo webhook percorre o fluxo da etapa 3, uma assinatura inválida é rejeitada em teste, e os templates estão submetidos.
- **Atenção:** o processo de Business Verification começa nesta etapa, porque depende da fila da Meta (Q-11).

### Etapa 18: deploy na Lightsail

- **Depende de:** etapas 15, 16 e 17.
- **Base:** D-19, D-20 e seção 9.2 da arquitetura.
- **Objetivo:** colocar a aplicação em produção em uma instância única, com rollback testado.
- **Tarefas:**
  - 18.1 Dockerfile e imagem com tag do commit.
  - 18.2 script de deploy por SSH.
  - 18.3 snapshot da instância antes de cada deploy.
  - 18.4 teste de rollback para a tag anterior.
- **Critério de pronto:** a aplicação sobe na Lightsail, e o rollback foi executado e registrado.

---

## Marco E: demo e piloto

### Etapa 19: demo gravada

- **Depende de:** etapa 18.
- **Base:** D-27.
- **Objetivo:** gravar o vídeo que apresenta o produto às clínicas.
- **Tarefas:**
  - 19.1 roteiro com as quatro cenas: agendamento, lembrete T-7 com confirmação, dúvida respondida e resumo diário.
  - 19.2 dados fictícios.
  - 19.3 gravação.
- **Critério de pronto:** o vídeo contém as quatro cenas, sem dado real.

### Etapa 20: pré-piloto

- **Depende de:** etapa 19.
- **Base:** seções 12 e 14 da arquitetura.
- **Objetivo:** cumprir os pré-requisitos legais, técnicos e clínicos antes de qualquer dado real.
- **Tarefas:**
  - 20.1 Business Verification concluída (Q-11).
  - 20.2 templates aprovados pela Meta.
  - 20.3 Embedded Signup assistido.
  - 20.4 forma jurídica definida (Q-14).
  - 20.5 revisão clínica das mensagens fixas (Q-09).
  - 20.6 plano Pro do Supabase e Secrets Manager configurado.
  - 20.7 contrato de tratamento de dados com a lista de subprocessadores.
- **Critério de pronto:** as tarefas 20.1 a 20.7 estão completas, com evidência, e a revisão clínica está registrada.

### Etapa 21: piloto

- **Depende de:** etapa 20 e as metas de Q-15.
- **Base:** Q-15, Q-16 e seção 12 da arquitetura.
- **Objetivo:** operar com a primeira clínica real e medir o resultado.
- **Tarefas:**
  - 21.1 definição das metas, com linha de base.
  - 21.2 entrada da primeira clínica.
  - 21.3 medição das métricas, com o período definido em Q-15.
- **Critério de pronto:** as metas foram definidas antes do início, as métricas estão registradas e a decisão de seguir ou parar está em ADR.

---

## Fora do escopo do MVP

A lista completa do que fica fora do MVP está na seção 10 de [arquitetura.md](./arquitetura.md). Este arquivo não repete essa lista.

## Questões em aberto

As questões Q-xx ficam em [arquitetura.md](./arquitetura.md), seção 13. Cada etapa indica quais questões precisa responder, mas o texto das questões não é copiado aqui.
