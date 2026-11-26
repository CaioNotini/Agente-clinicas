```
Papel: índice do guia de respostas do agente, a planilha que descreve o comportamento esperado por situação, por categoria e por perfil de clínica.
Entrada: docs/status.md
Relaciona-se com: ./guia_respostas.xlsx, ../etapas.md (etapas 0, 7, 9, 10 e 11), ../arquitetura.md (seções 7, 8.1, 8.3 e 8.4), ../fake_clinic/clinica.md, ../fake_clinic/FAQ.md, ../fake_clinic/pergs_bloqueadas.md, ../decisions/0009-agendamento-handoff-etapa5.md
```

# Guia de respostas do agente

A planilha [`guia_respostas.xlsx`](./guia_respostas.xlsx) reúne, para cada situação de conversa, o que o paciente escreve, o que o agente responde, o que ele deve e o que não deve fazer. Ela é editada pelo desenvolvedor. Todos os dados são fictícios.

## Para que serve

| Uso | Etapa | Como |
| --- | ----- | ---- |
| Exemplos no prompt | 7 | Algumas linhas variadas viram exemplos few-shot da classificação. Não a planilha inteira, para o modelo não copiar as frases. |
| Fluxos com estado | 9 | As linhas por estado e a aba Conversas descrevem o que cada ferramenta pode fazer em cada estado. |
| Suíte de avaliação | 10 | Todas as linhas e variações viram casos de teste. A avaliação confere `deve_fazer` e `nao_deve_fazer`, não o texto exato. |
| Lembretes | 11 | As linhas de prefixo CI descrevem as respostas ao lembrete. |
| Onboarding de clínicas | MVP | A aba Configuração da clínica é o roteiro do que decidir com cada clínica. |

## Abas

| Aba | Conteúdo |
| --- | -------- |
| Legenda | O que cada coluna significa, os prefixos de `id` e os cuidados de uso. É a referência para preencher a planilha. |
| Perfis de clínica | Os quatro perfis (P1 a P4), a clínica fictícia de teste de cada um e o que muda no agente. |
| Configuração da clínica | O que cada clínica decide, as opções e onde o dado fica no banco. |
| Guia de respostas | Uma linha por situação. É a aba principal. |
| Mensagens fixas | Cópia de referência das mensagens de `urgencia` e `clinico_bloqueado`. |
| Conversas | Fluxos com vários turnos. Cada turno aponta para a linha do guia que ele exercita. |

## Fonte da verdade

- Os textos padrão das mensagens fixas valem como estão em `app/mensagens/fixas.py`, e cada clínica pode definir o próprio texto (decisão 26). A aba Mensagens fixas é só uma cópia de referência e não altera o agente.
- Regras de negócio, como antecedência, janela de cancelamento e destinatário do handoff, ficam no código e no banco. A planilha descreve o comportamento esperado, não o define (regra 4 do [CLAUDE.md](../../CLAUDE.md)).
- A coluna `fonte` aponta para onde o dado fica no produto. No estudo, os dados da clínica P1 vêm de [`clinica.md`](../fake_clinic/clinica.md).
- O perfil de uma clínica não é um campo no banco. Ele resulta dos dados dela: quantas especialidades tem, quantos profissionais fazem cada serviço e quem recebe o handoff.
- Quando as abas Perfis e Configuração forem registradas em ADR, o ADR passa a ser a fonte, e a planilha passa a apontar para ele.
- Hoje a planilha é a fonte das situações e respostas esperadas. Quando a suíte da etapa 10 passar a lê-la, cada aba será exportada para CSV nesta pasta, e será decidido se a fonte passa a ser o CSV ou se o CSV é gerado a partir da planilha. As duas cópias não ficam editáveis ao mesmo tempo.

## Decisões aprovadas registradas na planilha

Decididas pelo desenvolvedor em novembro de 2026. As que mudam o código ainda não foram implementadas e estão nas pendências do [status.md](../status.md).

1. Cancelar e remarcar pedem confirmação do paciente, citando data, hora e profissional, antes de executar.
2. Pergunta administrativa sem informação na base não abre handoff direto. O agente oferece o encaminhamento e o paciente escolhe. Isso não vale para `clinico_bloqueado` e `urgencia`, que continuam incondicionais.
3. O agente só pergunta o profissional quando mais de um faz o serviço, e só pergunta a especialidade quando a clínica tem mais de uma.
4. Perguntar qual especialidade procurar a partir de um sintoma é agendamento, não `clinico_bloqueado`. O agente apresenta as especialidades com a descrição da clínica e não deduz a especialidade pelo sintoma.
5. Nas clínicas sem secretaria, o handoff vai para o profissional da consulta do paciente, ou para aquele com quem ele quer marcar.
6. Janela de cancelamento, antecedência mínima e máxima e o que fazer fora delas (o agente executa ou abre handoff) são decididos com cada clínica.
7. Os dados pedidos na primeira consulta e o que fazer quando o paciente não informa um dado são decididos com cada clínica.
8. Menor de idade é atendido acompanhado de um responsável, e o agente avisa isso ao agendar. A clínica configura se atende menores.
9. Áudios são transcritos e seguem o fluxo normal, passando pela mesma classificação que o texto, inclusive a de urgência.
10. Mensagens seguidas do mesmo contato são agrupadas e tratadas como uma só.
11. A confirmação de uma ação pendente (agendar, cancelar, remarcar ou abrir handoff) expira em 15 minutos. Depois disso, o agente pede a confirmação de novo.
12. Quando o paciente não tem consulta nem preferência de profissional, o handoff vai para um destinatário padrão definido previamente pela clínica.
13. Depois de uma urgência, a conversa vai para `escalada` e a ação pendente é descartada. A classificação de urgência é verificada antes do `human_mode`, então a mensagem fixa sai mesmo numa conversa já assumida por um humano.
14. O agrupamento de mensagens seguidas espera 4 segundos, renovados a cada mensagem nova, com teto de 12 segundos. Mensagem com palavra de urgência não espera. A espera usa o `run_at` do job e mantém a ordem do [ADR 0005](../decisions/0005-ordem-por-conversa.md). Os valores são iniciais e serão ajustados com dados da etapa 10 e do piloto.
15. A transcrição usa Whisper local no estudo e Amazon Transcribe no MVP. No MVP, a política de opt-out do AWS Organizations precisa estar ativa antes do primeiro áudio de paciente. O áudio é apagado logo depois da transcrição, e a transcrição é tratada como dado de saúde.
16. Quando a transcrição falha, o agente pede que o paciente escreva a mensagem, de preferência, ou que reenvie o áudio.
17. Imagens enviadas pelo paciente não são guardadas.
18. Se o paciente não responde ao lembrete até o fim do tempo de espera, o agente envia um segundo lembrete. Depois dele, não há lembrete novo.
19. Sem vaga no período pedido, o agente oferece, na mesma mensagem, primeiro os próximos horários do profissional de interesse e depois a opção de outro profissional, sem citar os horários dele.
20. Duração e preço da primeira consulta e do retorno são configurados pela clínica.
21. Saudação e pedido de humano não viram categorias próprias.
22. Dentro de `clinico_bloqueado`, a pergunta que espera uma resposta clínica ("posso tomar esse remédio?") recebe a mensagem fixa e abre o handoff. O sintoma de quem espera atendimento ("estou com dor nas costas") recebe a oferta de atendimento: o paciente escolhe entre o handoff para o profissional e seguir com o agendamento.
23. A classificação devolve uma lista de intenções, e o agente responde a todas. Se houver `urgencia` ou `clinico_bloqueado` entre elas, essa intenção vence e é tratada primeiro.
24. Na terceira repetição da mesma intenção sem solução, o agente oferece o handoff. A contagem é feita pelo código.
25. Sintomas odontológicos como inchaço com febre recebem a oferta de atendimento, não a mensagem de urgência, para a urgência não ser acionada em excesso. Dificuldade para respirar continua sendo urgência pela regra geral.
26. Os textos das mensagens fixas podem ser definidos por cada clínica. Quando ela não definir, vale um texto padrão por tipo. Os detalhes serão definidos mais adiante.

## Questões pendentes

- Como cada clínica define os textos das mensagens fixas, e quais são os textos padrão.
- A validação clínica das linhas OD-02, OD-02b e CB-03, prevista para a etapa 20.

## O que a planilha mostra que ainda não existe no schema

A coluna `fonte` marca esses itens com "(a criar)". Filtrar a coluna por esse texto lista todos. Os principais são a ação pendente da conversa com expiração, o horário de funcionamento da clínica, os convênios, a configuração de cadastro, a configuração de atendimento a menores, a política fora da antecedência, o telefone de handoff por profissional, o destinatário padrão do handoff, o paciente separado do contato que escreve e a transcrição de áudio.
