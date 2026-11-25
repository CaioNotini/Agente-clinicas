```
Papel: registra o contrato do LLMClient da etapa 6, a versão do SDK e da API da Anthropic, a hierarquia de erros e a configuração do modelo.
Entrada: docs/status.md
Relaciona-se com: ../arquitetura.md (D-13 e seção 6, Interfaces), ../etapas.md (etapa 6), 0005-ordem-por-conversa.md, 0008-conclusao-atomica-do-job.md, ../../app/core/erros.py, ../../app/config.py, ../../app/llm/fabrica.py, ../../.env.example, ../../pytest.ini
```

# 0010: Contrato do LLMClient e SDK da Anthropic na versão 2026-10-21 da API

## Contexto

A etapa 6 ([etapas.md](../etapas.md)) cria a interface `LLMClient` e a implementação `AnthropicClient`, prevista na tabela de interfaces da seção 6 da [arquitetura](../arquitetura.md). A decisão D-13 fixa o Claude Haiku pela API direta no estudo e pelo Bedrock no MVP. O `BedrockClient` da etapa 16 vai ter de cumprir o mesmo contrato, por isso ele fica registrado antes do primeiro código.

Pontos que motivaram a decisão:

- O projeto fixava `anthropic==0.25.7`, sem nenhuma chamada ao SDK no código.
- A versão 2.0.0 do SDK Python é a primeira que envia a versão `2026-10-21` da API por padrão. A 1.x ainda envia `2023-06-01`.
- O SDK repete sozinho as requisições que falham com 408, 409, 429, 5xx e erro de conexão (`max_retries` padrão 2). O worker também repete o job que falha ([ADR 0005](./0005-ordem-por-conversa.md)). As duas camadas juntas multiplicariam as chamadas e o custo.
- O desenvolvedor tem um projeto próprio de cliente LLM ([LLM-Client](https://github.com/CaioNotini/LLM-Client)), lido antes desta decisão para aproveitar o que serve aqui.

## Alternativas consideradas

- **SDK 1.x (1.17.0), na versão `2023-06-01` da API.** Descartada. O cliente seria escrito já preso à versão antiga, com uma migração garantida no meio das etapas 7 a 9, quando o código já chamaria o modelo.
- **Manter o SDK 0.25.7.** Descartada pelo mesmo motivo, e por depender de pacotes antigos (`tokenizers`, `huggingface_hub`) sem uso aqui.
- **Deixar a nova tentativa com o SDK e tirar o retry do job para as chamadas de IA.** Descartada. O retry do SDK acontece dentro do processamento, segura o lock da conversa e não conta em `attempts`. O backoff do job já é a regra para toda falha que volta para `pending`.
- **`LLM_MODEL` na lista `variaveis_obrigatorias` do `config.py`.** Descartada. Toda importação de `app.config` passaria a exigir a variável, inclusive a suíte do banco e a CI, que não chamam o modelo.
- **Identificador do modelo como valor padrão no código.** Descartada. A troca de modelo passaria por mudança de código, e o identificador ficaria espalhado.

## Decisão

O `LLMClient` é uma interface com um método `completar`, implementada pelo `AnthropicClient` sobre o SDK `anthropic==2.14.0`, que envia a versão `2026-10-21` da API. O SDK roda com `max_retries=0` e timeout de 60 s, com 5 s para a conexão. Os dois valores são fixados no código, na única função que cria o SDK, e cobertos por teste. O modelo vem da variável obrigatória `LLM_MODEL`, validada só quando o cliente é criado.

### Contrato

```python
completar(*, tenant_id, system, mensagens, ferramentas=None, esquema_saida=None) -> RespostaLLM
```

Os argumentos sao keyword-only para nenhum call site trocar a ordem sem perceber.

- `tenant_id`: clínica da operação. Serve só ao log estruturado e nunca vai à API.
- `system`: texto do prompt de sistema.
- `mensagens`: lista de mensagens no formato do projeto, cada uma com papel e conteúdo.
- `ferramentas`: definições de ferramentas, opcional.
- `esquema_saida`: esquema JSON da saída estruturada, opcional.

A resposta normalizada `RespostaLLM` tem:

| Campo | Conteúdo |
| ----- | -------- |
| `texto` | Texto da resposta |
| `chamadas_ferramenta` | Chamadas de ferramenta pedidas pelo modelo, com id, nome e entrada |
| `motivo_parada` | Motivo de parada devolvido pelo provedor |
| `tokens_entrada`, `tokens_saida` | Uso de tokens da chamada |
| `latencia_ms` | Tempo da chamada medido pelo cliente |
| `modelo` | Modelo que respondeu |
| `id_requisicao` | Id da requisição no provedor |

O suporte a ferramentas e a saída estruturada entra na interface agora, porque a arquitetura o prevê. O primeiro uso real fica para as etapas 7 e 9.

### Organização

- `app/llm/base.py`: a interface `LLMClient`, com ABC.
- `app/llm/anthropic_client.py`: o `AnthropicClient`, que recebe o cliente do SDK por injeção. Os testes passam um dublê.

### Erros

O `AnthropicClient` traduz os erros do SDK para uma hierarquia própria:

| Erro | Casos | Tratamento no worker |
| ---- | ----- | -------------------- |
| Base dos erros de LLM | Raiz da hierarquia | Não é levantada sozinha |
| Erro transitório | Conexão, timeout, 408, 409, 429, 5xx e 529 | Volta para `pending` com o backoff da tarefa 6.4 |
| Erro permanente, subclasse de `ErroPermanente` ([`erros.py`](../../app/core/erros.py)) | 400, 401, 403, 404 e 422 | Vai direto para `dead`, sem nova tentativa |

A mensagem do erro leva só o tipo, o status HTTP e o id da requisição. O texto do erro do provedor (`str(e)`) não entra, porque pode repetir dados da requisição, e o worker grava a mensagem em `jobs.last_error`. O mapeamento completo e os testes de cada status ficam na tarefa 6.2.

### Configuração

- Uma dataclass guarda `modelo`, `max_tokens` e `esforco`. A chave da API não entra nela. Também não entram `temperature`, `top_p` e `top_k`, que a versão `2026-10-21` recusa.
- O campo `esforco` fica `None` por padrão, e isso não desliga o raciocínio. O modelo do estudo, `claude-haiku-5-5`, tem raciocínio adaptativo sempre ligado, com esforço padrão `medium`, e os tokens de raciocínio contam como saída, dentro de `max_tokens` (verificado na documentação do modelo em 2026-11-25). `None` só significa que o cliente não envia `effort` nem `thinking`, então o modelo usa o próprio padrão. Enviar o esforço à API ou remover o campo fica para a etapa 7.
- `LLM_MODEL` não tem valor padrão no código. O identificador do modelo aparece só no [`.env.example`](../../.env.example).
- Uma função de configuração do LLM no [`config.py`](../../app/config.py) lê `LLM_MODEL` e `ANTHROPIC_API_KEY` e levanta `RuntimeError` listando as que faltam, no mesmo padrão de `variaveis_obrigatorias`. Ela roda só quando o cliente é criado. Essa é a única checagem da chave, sem segunda checagem no construtor.
- A chave é passada ao SDK explicitamente, como `api_key`.

### Onde o cliente é criado

Onde a função mora e onde ela é chamada são coisas diferentes.

- **Onde mora:** em [`app/llm/fabrica.py`](../../app/llm/fabrica.py). `criar_sdk_anthropic` é o único ponto de `app/` que cria o SDK, com o timeout e o `max_retries` fixos. `criar_cliente_llm` lê a configuração com `ler_config_llm` e devolve o `AnthropicClient`. O módulo de jobs não importa o SDK, então a troca de provedor (Bedrock, etapa 16) fica restrita a `app/llm/`. Um teste em [`test_cliente_llm.py`](../../tests/unit/test_cliente_llm.py) varre `app/` e falha se outro arquivo criar `Anthropic` ou `AsyncAnthropic`.
- **Onde é chamada:** uma vez, no `main()` do worker, e o cliente é injetado no processamento. Se faltar a chave ou o modelo, o `RuntimeError` impede o worker de subir e nenhum job é consumido. Os testes que chamam o processamento direto recebem um dublê e nunca dependem de `LLM_MODEL` nem de `ANTHROPIC_API_KEY`. A CI continua sem essas variáveis.

A ligação no worker não é feita na etapa 6, porque nada no processamento usa o LLM ainda. Criar o cliente na subida faria o worker exigir as duas variáveis sem usá-las. A ligação no `main()` entra na tarefa 7.2, quando o processamento passar a chamar o modelo. O teste real (`llm_real`) também cria o SDK por `criar_sdk_anthropic`.

### Timeout e nova tentativa do SDK

Decidido em 2026-11-25, antes da tarefa 7.1 (achado A8 da [rodada 5](../diagnosticos/2026-11-25-rodada5.md)).

- **`max_retries=0`.** A nova tentativa fica numa camada só, a do job, contada em `attempts` e com backoff. O retry do SDK aconteceria dentro do lock da conversa e fora de `attempts`.
- **Timeout de 60 s, com 5 s para a conexão.** O timeout precisa ser menor que `LIMITE_LOCK_SEGUNDOS` (300 s, em [`worker.py`](../../app/jobs/worker.py)). Assim, uma chamada travada termina antes de o job virar órfão. Sem isso, outro worker recapturaria o job e faria uma segunda chamada paga. O ADR 0008 evita o efeito duplicado no banco, mas não o custo. O padrão do SDK 2.14.0 é de 600 s.
- **O limite vale por fase do httpx, não no total.** As fases são conexão, envio, leitura e espera por conexão. A conexão de 5 s reduz o pior caso somado para cerca de 185 s. Na chamada sem streaming, a leitura espera a resposta inteira, então o limite prático de uma chamada fica perto dos 60 s.
- **O limite é por chamada, não por job.** Se um job fizer várias chamadas, como a classificação e o function calling da etapa 9, a soma pode passar de 300 s. Isso precisa ser revisto na etapa 9.
- O teste unitário confere `max_retries == 0`, os valores de cada fase e que cada fase é menor que `LIMITE_LOCK_SEGUNDOS`. Subir o timeout para 300 s ou mais derruba o teste.

### Log

Cada chamada gera um evento no log estruturado (structlog). O sucesso emite `llm_chamada` com `tenant_id`, modelo, tokens de entrada e saída, latência, motivo de parada e id da requisição. A falha emite `llm_chamada_falhou` antes de levantar o erro de domínio, com `tenant_id`, modelo, latência, tipo do erro de domínio (transitório ou permanente), status HTTP quando houver e id da requisição quando houver, sem tokens. O conteúdo das mensagens, o prompt, o telefone do contato e o texto da exceção do SDK nunca entram no log. O id da requisição é o que o suporte da Anthropic pede. A persistência em tabela fica para a etapa 10.

### Teste real

A chamada real à API tem o marcador `llm_real`, registrado no [`pytest.ini`](../../pytest.ini) e excluído por padrão com `-m "not llm_real"`. Só o desenvolvedor roda, com `pytest -m llm_real`, e a CI nunca roda.

### Restrições da versão 2026-10-21 que afetam o contrato

Fonte: [guia de migração para a versão 2026-10-21](https://platform.claude.com/docs/en/api/migration-2026-10-21).

| Restrição | Efeito no `LLMClient` |
| --------- | --------------------- |
| `temperature`, `top_p` e `top_k` dão erro 400, mesmo no valor padrão | Não entram na dataclass nem em `completar` |
| Um bloco `document` direto numa mensagem `assistant` dá erro 400 | Documentos vão só em mensagens `user`. Vale para o RAG e para a montagem do histórico |
| Um bloco `text` com `citations` preenchido numa mensagem `user` dá erro 400 | Uma resposta do modelo que volta como entrada de usuário vai sem `citations` |
| No SDK 2.x, `MessageParam` é uma união com um tipo por papel | As mensagens são montadas como dicionário, um papel de cada vez, sem chamar `MessageParam(...)` |
| A chave vai em `Authorization: Bearer`, e cada cliente guarda uma credencial só | Nenhuma mudança, porque não há proxy e o cliente recebe só a `api_key` |
| No Bedrock, a versão 2026-10-21 só vale para modelos Claude 4.7 em diante | Conferir o modelo do `BedrockClient` na etapa 16 |

### Aproveitado do LLM-Client

- O mapeamento dos erros do SDK, por classe, para uma hierarquia de exceções própria. Mudam duas coisas: 5xx e 529 viram erro transitório, e a mensagem não leva `str(e)`.
- A separação entre a interface (ABC) e a implementação.
- A configuração do modelo numa dataclass, sem a chave.

Não aproveitado: o retry com sleep, o `rate_limit`, o `log_execution` com print (registra parte do prompt e da resposta, o que aqui seria dado de paciente), o registro de providers por string e o `temperature` da dataclass. O `tests/test_client.py` de lá é um script de chamada real, e a ideia vira o teste com o marcador `llm_real`.

## Justificativa

A versão 2.x põe o cliente na versão atual da API desde a primeira linha de código, e a troca custa pouco agora, sem chamadas ao SDK. Com `max_retries=0`, a nova tentativa fica numa camada só, contada em `attempts` e com backoff. A hierarquia de erros separa o que adianta tentar de novo do que só atrasaria a conversa, e reaproveita o caminho de `ErroPermanente` que o worker já tem. A validação na criação do cliente segue o padrão de falhar quando falta variável sem obrigar a suíte e a CI a conhecer o modelo.

## Consequências

- O SDK 2.x exige `anyio>=4.1`, e o FastAPI 0.104.1 exigia `anyio<4`. O FastAPI passou para 0.108.0, a primeira versão sem esse teto, e com ele o Starlette foi de 0.27 para 0.32. A suíte passou com 448 testes nessa combinação. O `TestClient` do Starlette 0.32 emite um aviso de descontinuação do `anyio.abc.BlockingPortal`, sem falha.
- O SDK 2.x traz o `httpx2`. O pin `httpx==0.25.2` continua, porque o `TestClient` do FastAPI usa o `httpx`.
- Os pacotes `tokenizers` e `huggingface_hub`, trazidos pelo SDK 0.25.7, deixam de ser instalados.
- O SDK 2.x está sob a licença Apache 2.0. As versões anteriores eram MIT.
- O retry do job passa a ser a única nova tentativa de uma chamada de IA. A conversa inteira espera durante o backoff, pela ordem por conversa. Essa consequência é registrada no [ADR 0005](./0005-ordem-por-conversa.md) na tarefa 6.4.
- O backoff da tarefa 6.4 usa `run_at = now() + min(base * 2 ** (tentativas - 1), teto)`, com `base` de 60 s e `teto` de 1800 s (constantes em [`worker.py`](../../app/jobs/worker.py)). Com `max_attempts = 3`, há atraso só na 1ª falha (60 s) e na 2ª (120 s), e a conversa fica parada cerca de 3 minutos antes de o job ir para `dead`. O teto de 1800 s não vincula nesse caso e só passa a ter efeito se o número de tentativas aumentar. O backoff atua só no retry que volta para `pending`. O caminho de `dead` e o de `done` não mexem no `run_at`.
- Trocar de modelo é trocar `LLM_MODEL`, sem mudança de código.
- Um status HTTP que a tabela de erros não lista é decidido na tarefa 6.2, com teste.

## Status

Aceita
