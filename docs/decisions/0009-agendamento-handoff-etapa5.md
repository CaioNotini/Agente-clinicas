```
Papel: Decisões de produto e schema da etapa 5 para duração, fuso, cancelamento fora da janela e destinatário de handoff, sem presumir recepção.
Entrada: docs/status.md
Relaciona-se com: ../arquitetura.md, ../etapas.md, 0004-conflito-de-horario.md, 0007-fks-compostas-por-tenant.md
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

**Q-23 fuso.** Fuso por clínica em `clinicas.fuso` (nome IANA, default `America/Sao_Paulo`). As regras de antecedência, janela de cancelamento e lembretes usam o fuso da clínica. O armazenamento de `agendamentos.inicio` e `agendamentos.fim` continua em UTC (timestamptz), como no [ADR 0004](0004-conflito-de-horario.md). A conversão para o fuso da clínica fica numa função única, e o nome do fuso é validado pela aplicação antes de gravar. O pacote `tzdata` entra no `requirements.txt`, porque o Windows não traz a base de fusos do sistema.

**Q-24 quem foi notificado.** `handoffs` ganha `notificado_para` (String) e `notificado_canal` (String, com CHECK dos canais existentes), ao lado do `notificado_em` já existente. O destinatário do aviso continua sendo `clinicas.telefone_plantao`, que pode ser o da recepção ou o do próprio profissional. `notificado_para` registra quem de fato recebeu.

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

## Status

Aceita
