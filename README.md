# Agente Clínicas

Agente de IA que vai atender clínicas pelo WhatsApp: agendar, remarcar e cancelar consultas, enviar lembretes e responder dúvidas administrativas. Hoje é um projeto de estudo de baixo custo, com canal de terminal (CLI) e banco local, construído em etapas atrás das mesmas interfaces que o MVP vai usar.

**Status:** o estado real de cada etapa, as pendências e as evidências de teste ficam em [`docs/status.md`](docs/status.md). A sequência completa das etapas está em [`docs/etapas.md`](docs/etapas.md).

O que já funciona:

- schema multi-tenant com RLS por clínica,
- canal CLI que grava a mensagem e enfileira um job,
- worker que consome a fila na ordem de cada conversa,
- máquina de estados da conversa e lock por conversa,
- tabela de agendamentos com bloqueio de conflito de horário.

## Requisitos

- Python 3.12
- Docker com Docker Compose v2 (`docker compose`)
- Git

## Setup do zero

Os comandos abaixo rodam na raiz do repositório. Onde o comando muda entre sistemas, as duas formas aparecem.

1. Clone o repositório e entre na pasta.

   ```bash
   git clone <url-do-repositorio> Agente-clinicas
   cd Agente-clinicas
   ```

2. Crie e ative o ambiente virtual.

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Linux e macOS
   source .venv/Scripts/activate    # Windows, Git Bash
   .venv\Scripts\Activate.ps1       # Windows, PowerShell
   ```

3. Instale as dependências.

   ```bash
   pip install -r requirements-dev.txt
   ```

4. Crie o `.env` a partir do exemplo, se ele ainda não existir. Os valores do exemplo são fictícios e servem para o ambiente local. Troque as senhas se quiser. O `.env` nunca vai para o Git.

   ```bash
   cp .env.example .env
   ```

5. Suba o banco e espere ele ficar saudável.

   ```bash
   docker compose up -d --wait
   ```

   O container cria o superusuário `DB_USER` e o banco `DB_NAME` só na primeira subida, com o volume vazio. Se mudar `DB_USER` ou `DB_PASSWORD` depois, recrie o volume com `docker compose down -v`.

6. Crie o schema e as roles.

   ```bash
   alembic upgrade head
   ```

7. Defina as senhas de `app_clinicas` e `worker_jobs` a partir do `.env`. As migrations criam essas roles sem senha. O comando pode ser repetido a qualquer momento.

   ```bash
   python -m scripts.definir_senhas
   ```

8. Instale os hooks de formatação do pre-commit (opcional, mas recomendado).

   ```bash
   pre-commit install
   ```

9. Rode os testes.

   ```bash
   pytest
   ```

## Como rodar

**Testes.** `pytest` roda a suíte inteira contra o banco do Docker. Para um diretório só, use `pytest tests/isolation`. Os testes de `tests/concurrency/` apagam os jobs `pending` e `processing` do banco antes de cada teste, então um job enfileirado à mão pelo CLI some quando a suíte roda.

**Saúde da API.** A API tem só a rota `/health`, que responde 200 quando o banco responde e 503 quando não responde.

```bash
uvicorn app.main:app --reload
# em outro terminal: curl http://localhost:8000/health
```

**Worker.** Consome a fila de jobs até ser interrompido com Ctrl+C. Hoje o processamento só garante a conversa da mensagem e a trava enquanto o job roda.

```bash
python -m app.jobs.worker
```

**Formatação (pre-commit).** O [`.pre-commit-config.yaml`](.pre-commit-config.yaml) roda black e isort (`--profile black`) sobre `app/` antes de cada commit, com as mesmas versões da CI (black `23.12.0` e isort `5.13.2`). Depois de `pre-commit install`, o commit que tocar em `app/` é formatado e barrado se o código estava fora do padrão. Para rodar à mão em tudo, use `pre-commit run --all-files`. A CI continua conferindo o mesmo com `black --check` e `isort --check-only`, então o pre-commit é a primeira barreira, não a única.

**CLI.** Lê mensagens da entrada padrão, grava cada uma e enfileira o job. A clínica precisa existir. Para criar uma clínica fictícia, use o superusuário do `.env` (`DB_USER` e `DB_NAME`). Dentro do container o `psql` não pede senha.

```bash
docker compose exec postgres psql -U dev_admin -d agente_estudo -c "INSERT INTO clinicas (tenant_id, nome, ativo) VALUES (gen_random_uuid(), 'Clinica Ficticia', true) RETURNING tenant_id"

echo "quero marcar uma consulta" | python -m app.channels.cli --tenant <tenant_id> --telefone "(11) 90000-0000"
```

Com o worker rodando em outro terminal, o job enfileirado é processado.

## Estrutura de pastas

- `app/`: código da aplicação (canal, fila e worker, núcleo da conversa, agenda e banco).
- `migrations/`: migrations do Alembic, que criam o schema, as roles e o RLS.
- `scripts/`: comandos de setup e verificação usados pelo README e pela CI.
- `tests/`: testes de integração, concorrência e isolamento entre clínicas.
- `docs/`: documentação canônica, ADRs e diagnósticos. A entrada é [`docs/status.md`](docs/status.md).

## Decisões de arquitetura

A arquitetura está em [`docs/arquitetura.md`](docs/arquitetura.md). As decisões tomadas durante a implementação ficam nos ADRs:

- [0001: Alembic na raiz do repositório](docs/decisions/0001-alembic.md)
- [0002: Contas de banco](docs/decisions/0002-contas-de-banco.md)
- [0003: Grafo de transições entre estados da conversa](docs/decisions/0003-grafo-de-transicoes.md)
- [0004: Conflito de horário de agendamentos](docs/decisions/0004-conflito-de-horario.md)
- [0005: Ordem de processamento por conversa](docs/decisions/0005-ordem-por-conversa.md)
- [0006: Provisionamento das roles automatizadas](docs/decisions/0006-provisionamento-de-roles.md)

## Variáveis de ambiente

Todas são obrigatórias. O `app/config.py` para com erro se faltar alguma. Os exemplos são fictícios.

Use `DB_HOST=127.0.0.1`, e não `localhost`. Em muitas máquinas `localhost` resolve primeiro para `::1` (IPv6). Se o container publicar a porta só em `127.0.0.1`, cada conexão espera o IPv6 cair antes de tentar o IPv4, o que trava a conexão e estoura o `connect_timeout`.

| Nome                 | Para que serve                                                                 | Exemplo fictício           |
| -------------------- | ------------------------------------------------------------------------------ | -------------------------- |
| `DB_HOST`            | Host do Postgres. Use `127.0.0.1`, não `localhost` (ver nota abaixo)           | `127.0.0.1`                |
| `DB_PORT`            | Porta do Postgres no host. O container expõe a 5432 nessa porta                | `5434`                     |
| `DB_NAME`            | Nome do banco                                                                  | `agente_estudo`            |
| `DB_USER`            | Superusuário criado pelo container. Usado só pelas migrations e pela administração | `dev_admin`            |
| `DB_PASSWORD`        | Senha de `DB_USER`                                                             | `senha-ficticia-admin`     |
| `APP_DB_USER`        | Conta da aplicação, sujeita ao RLS. Precisa ser exatamente `app_clinicas`      | `app_clinicas`             |
| `APP_DB_PASSWORD`    | Senha de `app_clinicas`, aplicada por `scripts/definir_senhas.py`              | `senha-ficticia-app`       |
| `WORKER_DB_USER`     | Conta do worker de jobs. Precisa ser exatamente `worker_jobs`                  | `worker_jobs`              |
| `WORKER_DB_PASSWORD` | Senha de `worker_jobs`, aplicada por `scripts/definir_senhas.py`               | `senha-ficticia-worker`    |

As senhas podem ter qualquer caractere, inclusive espaço. No `.env`, coloque entre aspas simples a senha que tiver `$` ou `#`, como `DB_PASSWORD='abc$def'`. Sem as aspas, o Docker Compose lê `$def` como variável, e um `#` depois de espaço vira comentário.

Os nomes `app_clinicas` e `worker_jobs` são os das roles criadas nas migrations. O script de senhas recusa outros valores. Detalhes no [ADR 0002](docs/decisions/0002-contas-de-banco.md) e no [ADR 0006](docs/decisions/0006-provisionamento-de-roles.md).

## Suíte de avaliação

A preencher na etapa 10.

## Diagrama do fluxo

A preencher na etapa 12.

## Decisões e tradeoffs

A preencher na etapa 12.

## Como evoluir para produção

A preencher na etapa 12.
