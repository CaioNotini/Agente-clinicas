```
Papel: Decisões de produto e schema da etapa 5 para duração, fuso, cancelamento fora da janela e destinatário de handoff, sem presumir recepção.
Entrada: docs/status.md
Relaciona-se com: ../arquitetura.md, ../etapas.md, 0004-conflito-de-horario.md, 0005-ordem-por-conversa.md, 0007-fks-compostas-por-tenant.md, 0008-conclusao-atomica-do-job.md, ../guias_respostas/guia_respostas.md
```

# 0009: Agendamento e handoff da etapa 5 sem presumir recepção

## Contexto

Consultórios de um profissional só, sem secretária nem recepção, fazem parte do público-alvo. O sistema não pode presumir que existe uma recepção. A etapa 5 precisa fechar Q-21 a Q-24 da seção 13 da [arquitetura](../arquitetura.md), e as regras não podem depender de um papel fixo de recepção.

## Alternativas consideradas

- Duração só por serviço: não atende clínicas que variam a duração por profissional. Descartada.
- Fuso fixo America/Sao_Paulo no código: quebra clínicas em outros fusos e esconde a conversão. Descartada.
- Cancelamento fora da janela sempre rejeitado: deixa o paciente sem saída num consultório solo. Descartada.
- Cancelamento fora da janela sempre aceito: tira da clínica a opção de revisar o caso. Descartada.
- Coluna `handoff_destinatario` na clínica: no MVP o destino do aviso é um número só, `clinicas.telefone_plantao`. Uma coluna de tipo de destinatário adianta roteamento que ainda não existe. Descartada (ver Consequências).
- Guardar quem foi notificado numa tabela de notificações agora: adianta complexidade sem necessidade na etapa 5. Adiada (ver Consequências).

## Decisão

**Q-21 duração.** A duração padrão fica em `servicos.duracao_minutos`. Um override opcional por profissional fica em `profissional_servicos.duracao_minutos` (nullable). O cálculo do fim do agendamento usa o override quando ele existir, senão a duração do serviço.

**Q-22 cancelamento fora da janela.** Política configurável por clínica, em `regras_agendamento.politica_cancelamento_fora_janela`, com dois valores protegidos por CHECK:
- `handoff` (padrão): o pedido vira handoff com motivo `cancelamento_fora_da_janela`. O agendamento só é cancelado depois da decisão humana.
- `aceitar_e_marcar`: cancela na hora e marca como cancelamento tardio, sem abrir handoff. A marca fica em `agendamentos.cancelado_fora_da_janela` (boolean, default false).

**Q-23 fuso.** Fuso por clínica em `clinicas.fuso` (nome IANA, default `America/Sao_Paulo`). As regras de antecedência, janela de cancelamento e lembretes usam o fuso da clínica. O armazenamento de `agendamentos.inicio` e `agendamentos.fim` continua em UTC (timestamptz), como no [ADR 0004](0004-conflito-de-horario.md). A conversão para o fuso da clínica fica numa função única, e o nome do fuso é validado pela aplicação antes de gravar. Estado atual: a aplicação ainda não grava `clinicas.fuso`, e a validação acontece na leitura, em `regras_da_clinica`. O pacote `tzdata` entra no `requirements.txt`, porque o Windows não traz a base de fusos do sistema.

**Q-24 quem foi notificado.** `handoffs` ganha `notificado_para` (String) e `notificado_canal` (String, com CHECK dos canais existentes), ao lado do `notificado_em` já existente. O destinatário do aviso continua sendo `clinicas.telefone_plantao`, que pode ser o da recepção ou o do próprio profissional. `notificado_para` registra quem de fato recebeu. Revisto em 2026-11-24: as duas colunas passam a ser o destino previsto, e `notificado_em` confirma o envio (ver Revisão).

**Configuração nova por clínica.** Em `clinicas`:
- `handoff_prazo_resposta_minutos` (Integer, nullable): prazo de resposta esperado. Nulo significa não informar prazo ao paciente.
- `handoff_texto_paciente` (String, nullable): texto informado ao paciente quando um handoff é aberto. Nulo significa usar um texto padrão neutro.

**Urgência não depende de handoff.** A mensagem fixa de `urgencia` orienta o paciente a procurar o serviço de emergência (192 ou pronto-socorro) de forma incondicional e imediata, sem depender de o handoff ser atendido, e nunca usa o texto de handoff da clínica. Ver seção 8.3 da arquitetura.

## Justificativa

Override por profissional é nullable, então a clínica que não precisa nunca preenche. Fuso na clínica mantém UTC no banco e concentra a conversão num ponto só. A política de cancelamento por clínica atende tanto o consultório solo, que pode preferir `aceitar_e_marcar`, quanto a clínica com equipe, que pode preferir revisar via handoff. A config de handoff fica em `clinicas` porque segue o padrão de configuração como dado já usado para `telefone_plantao`. A regra de cancelamento mora em `regras_agendamento` porque é uma regra de agendamento. Não criar `handoff_destinatario` evita modelar um roteamento que o MVP não faz.

## Consequências

- `agendamentos.cancelado_fora_da_janela` permite distinguir um cancelamento tardio sem mudar a constraint EXCLUDE, que já ignora linhas canceladas (where status = 'agendado').
- `regras_agendamento` passa a ter a política de cancelamento, além de antecedência e janela.
- O motivo `cancelamento_fora_da_janela` em `handoffs.motivo` não exige constraint, pois não há CHECK de motivo.
- `profissional_servicos`, `clinicas`, `regras_agendamento` e `agendamentos` têm `tenant_id` e já estão em `TABELAS_TENANT` com a policy `isolamento_tenant`. As colunas novas não mudam o isolamento, e os testes de isolamento continuam cobrindo as tabelas.
- Evolução prevista, fora da etapa 5:
  - Roteamento por profissional, por exemplo uma dúvida clínica ir para o profissional do paciente, e não para um número único de plantão. Quando isso existir, volta a fazer sentido um destinatário configurável no lugar de um número só.
  - Se surgirem múltiplos destinatários, reenvio ou escalonamento, `notificado_para` e `notificado_canal` em `handoffs` deixam de bastar, e o registro de notificações vira uma tabela própria, com uma linha por tentativa de notificação.
- A conversão de fuso para exibição ao paciente entra quando houver canal que exiba horário, não nesta etapa.

## Revisão de 2026-11-24 (tarefa 5.4)

### Contexto

A 5.4 grava o handoff, mas o aviso ao responsável só é enviado a partir da etapa 13 ([`etapas.md`](../etapas.md)). Com a leitura anterior de Q-24, preencher `notificado_para` sem enviar nada registraria algo que não aconteceu. A tabela também não guardava o que foi dito ao paciente, o prazo prometido, o agendamento envolvido nem a mensagem que originou o pedido.

### Decisão

- **Destino previsto.** Na abertura, `notificado_para` recebe `clinicas.telefone_plantao` e `notificado_canal` recebe o canal do estudo (`cli`). Sem `telefone_plantao`, as duas ficam nulas. `notificado_em` fica nulo até o envio real, e é ele que confirma que o aviso saiu.
- **Colunas novas em `handoffs`**, numa migration só (`c3d8e5a1f297`):
  - `texto_paciente`: cópia do texto que o bot informou ao paciente na abertura, montado pela configuração da clínica ou pelo padrão neutro. Nunca o conteúdo da mensagem do paciente.
  - `responder_ate` (timestamptz): instante limite, calculado na abertura como o momento do pedido somado a `handoff_prazo_resposta_minutos`. Nulo quando a clínica não informa prazo. Um prazo nulo ou não positivo conta como não informado, para um cadastro ruim do prazo não impedir o handoff.
  - `agendamento_id`: o agendamento envolvido, quando ele já foi validado como do contato. FK composta para `agendamentos (tenant_id, id)`, com a regra de exclusão das outras FKs (`NO ACTION`).
  - `mensagem_id`: só a referência da mensagem de origem, nunca o conteúdo. FK composta para `mensagens (tenant_id, id)` com `ON DELETE SET NULL (mensagem_id)`. O pedido de exclusão do titular (LGPD) apaga a mensagem e mantém o handoff, sem a referência. A lista de colunas faz o Postgres 15 zerar só `mensagem_id`. Sem ela, zeraria também `tenant_id`, que é NOT NULL, e a exclusão falharia.
- **UNIQUE `(tenant_id, id)`** em `agendamentos` e `mensagens`, alvo das FKs compostas, pela regra de tabelas novas do [ADR 0007](./0007-fks-compostas-por-tenant.md).
- **Motivos gravados na etapa 5.** `cancelamento_fora_da_janela`, com o agendamento, e `configuracao_invalida`, no lugar da `ConfiguracaoInvalida` do serviço. Este não referencia o agendamento pedido, porque o id pode não ser do contato e a falha pode ter vindo antes dessa verificação.
- **Sem mudança de estado.** O handoff não muda `estado_conversa` nem `human_mode`. Por isso a 5.4 não é a primeira etapa em que o processamento altera o estado da conversa, e a conduta depois de uma mensagem morta continua com prazo na etapa 9 ([ADR 0005](./0005-ordem-por-conversa.md)).
- **Confirmação junto com o job.** O handoff é gravado na sessão da conversa travada, sem commit próprio, e é confirmado ou desfeito com a conclusão do job ([ADR 0008](./0008-conclusao-atomica-do-job.md)).

### Alternativas consideradas

- Deixar `notificado_para` e `notificado_canal` nulos até a etapa 13. Descartada pelo desenvolvedor: o destino previsto já é útil para quem lê o registro, e `notificado_em` separa o previsto do enviado.
- Não gravar texto nem prazo e devolver só o texto montado. Descartada: a configuração da clínica pode mudar depois, e o registro perderia o que foi prometido.
- `mensagem_id` sem FK. Descartada: um handoff de uma clínica poderia apontar para a mensagem de outra sem o banco recusar.
- `mensagem_id` com `NO ACTION`. Descartada: impediria apagar a mensagem num pedido de exclusão do titular.

### Consequências

- `handoffs` já tem a policy `isolamento_tenant` e está em `TABELAS_TENANT`. Nenhuma policy, role ou grant muda.
- O teste de catálogo das FKs cobre as duas FKs novas, e [`test_fk_tenant.py`](../../tests/isolation/test_fk_tenant.py) prova a recusa da referência de outra clínica e a exclusão da mensagem.
- Um agendamento referenciado por handoff não pode ser apagado. Hoje nenhum caminho apaga agendamentos, que só mudam de status. Um pedido de exclusão do titular (LGPD) que precise apagar agendamentos vai ter de tratar antes os handoffs que apontam para eles. A conduta fica para quando esse pedido for implementado.
- A FK de `mensagem_id` garante a mesma clínica, mas não o mesmo contato. Hoje só código interno passa o id. Quando o processamento passar a chamar o serviço (etapa 7), o `mensagem_id` deve vir do job, e não de um dado da mensagem.
- `handoff_texto_paciente` continua `varchar(500)`, então o banco recusa um texto maior já na gravação da configuração. `texto_paciente` tem 600 caracteres para caber o texto da clínica com a frase do prazo.
- Cada pedido grava uma linha, sem deduplicação. A nova tentativa de um job não duplica, pela atomicidade do ADR 0008. Não abrir um handoff novo quando já houver um aberto para a mesma conversa, motivo e agendamento fica para a etapa 13, registrado em [`status.md`](../status.md).

## Revisão de 2026-11-26 (decisões 5 e 12 do guia de respostas)

### Contexto

O [guia de respostas](../guias_respostas/guia_respostas.md) registra duas decisões sobre o destinatário do handoff. Pela decisão 5, nas clínicas sem secretaria, o handoff vai para o profissional da consulta do paciente, ou para aquele com quem ele quer marcar. Pela decisão 12, quando o paciente não tem consulta nem preferência de profissional, o handoff vai para um destinatário padrão definido previamente pela clínica. É o roteamento por profissional que as Consequências deste ADR já previam como evolução.

### Decisão

- O destino do aviso deixa de ser sempre `clinicas.telefone_plantao`.
- Sem recepção nem secretaria, o destino é o profissional da consulta do paciente, ou aquele com quem ele quer marcar.
- Sem consulta nem preferência de profissional, o destino é o destinatário padrão definido pela clínica.
- Com recepção ou secretaria, o destino segue a configuração da clínica.
- `notificado_para` e `notificado_canal` continuam registrando o destino previsto, agora escolhido por essas regras.

### Alternativas consideradas

- Manter um número único de plantão para todo handoff. Descartada: numa clínica com mais de um profissional e sem secretaria, o aviso chegaria a quem não atende o paciente.
- Escolher um profissional qualquer quando o paciente não tem consulta nem preferência. Descartada: o aviso poderia ir para quem não conhece o caso. A linha HU-01c do guia manda perguntar ao paciente antes e usar o destinatário padrão quando ele não souber.

### Consequências

- O destinatário configurável, descartado na decisão original por adiantar um roteamento que não existia, volta a fazer sentido. O formato no banco, com o telefone por profissional e o destinatário padrão, fica para o ADR de configuração da clínica, previsto antes da etapa 8 em [`status.md`](../status.md).
- O código não muda nesta revisão. [`app/handoff/abertura.py`](../../app/handoff/abertura.py) continua gravando `clinicas.telefone_plantao` como destino previsto. A mudança é pendência antes da etapa 9.
- Se um handoff passar a avisar mais de um destinatário, vale a consequência já registrada acima: o registro de notificações vira uma tabela própria.
- A urgência continua sem depender do handoff.

## Status

Aceita. Revista em 2026-11-24 (tarefa 5.4) e em 2026-11-26 (decisões 5 e 12 do guia de respostas)
