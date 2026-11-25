Papel: perguntas administrativas fictícias, usadas como corpus do RAG (etapa 8) e como casos de teste (etapa 10).
Entrada: docs/status.md
Relaciona-se com: ../etapas.md (etapas 0, 8 e 10), ../arquitetura.md (seção 8.3 e tabela conhecimento_clinica), ./clinica.md (dados de referência), ./pergs_bloqueadas.md (fronteira com o que não é respondido).

# Perguntas frequentes: Clínica Fictícia

Cada pergunta tem uma categoria. `permitido`: a resposta está na base da clínica e o agente responde. `sem_informacao`: a pergunta é administrativa, mas a base não tem a resposta. O agente não inventa e oferece ao paciente a escolha entre falar com o responsável pelo atendimento (handoff) ou seguir no atendimento automático. Essa categoria serve para testar esse caminho e não entra no corpus do RAG. Nenhuma das duas é `clinico_bloqueado`, que fica em [pergs_bloqueadas.md](./pergs_bloqueadas.md). A regra está na seção 8.3 da [arquitetura](../arquitetura.md#83-escopo-clínico).

### Qual é o horário de funcionamento?

- Resposta: A clínica funciona de segunda a quinta, das 08:00 às 12:00 e das 13:30 às 18:00. Na sexta, funciona das 08:00 às 12:00 e das 13:30 às 17:00. No sábado, funciona das 08:00 às 12:00. No domingo, a clínica fica fechada.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 6

### Onde fica a clínica?

- Resposta: A clínica fica na Rua Fictícia, 100, bairro fictício, Belo Horizonte, MG.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seções 1 e 15

### Quais convênios vocês atendem?

- Resposta: A clínica atende o Convênio Fictícia Saúde, o Plano Fictício Vida e o Convênio Modelo Med. Atendimento particular também disponível.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 7

### Como faço para cancelar minha consulta?

- Resposta: Avise a clínica com pelo menos 48 horas de antecedência. Cancelamentos feitos dentro desse prazo precisam ser confirmados pela recepção pelo telefone de plantão.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 10

### Como faço para remarcar minha consulta?

- Resposta: Envie uma mensagem no WhatsApp da clínica com o dia e o horário desejados. O agente verifica a agenda e confirma a nova data.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 10

### Preciso chegar antes do horário da consulta?

- Resposta: Chegue com antecedência para fazer o cadastro ou a atualização dos seus dados na recepção. Pacientes que chegam com atraso podem ter a consulta reagendada, conforme a agenda do dia.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seções 11 e 14

### Quais documentos preciso levar na consulta?

- Resposta: Leve documento de identidade com foto. Se a consulta for pelo convênio, leve também a carteirinha do convênio. Quando o convênio exigir, leve o pedido médico ou o encaminhamento.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 9

### Com quanta antecedência posso marcar uma consulta?

- Resposta: O agendamento precisa ser feito com pelo menos 2 horas de antecedência.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 8

### Até quando posso marcar uma consulta?

- Resposta: É possível agendar uma consulta com até 60 dias de antecedência.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 8

### Quais especialidades a clínica atende?

- Resposta: A clínica atende Clínica Geral, Dermatologia e Ortopedia.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 1

### A clínica atende emergências?

- Resposta: Não. A clínica atende apenas consultas com hora marcada. Em caso de emergência, procure um serviço de pronto atendimento.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 3

### O que acontece se eu faltar à consulta sem avisar?

- Resposta: A clínica registra a falta. Em caso de dúvida, a recepção pode ajudar a encontrar outro horário.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 10

### Quanto custa a consulta particular?

- Resposta: A consulta particular custa R$ 250,00 em qualquer especialidade.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 7

### Vocês fazem reembolso do convênio?

- Resposta: A clínica não faz reembolso nem intermedia o pedido junto ao convênio. Na consulta particular, a recepção entrega o recibo no dia, e você pede o reembolso direto ao seu plano.
- Categoria: `permitido`
- Fonte: [./clinica.md](./clinica.md), seção 7

### Vocês têm estacionamento?

- Comportamento esperado: o agente informa que não tem essa informação, sem inventar resposta, e pergunta se o paciente quer falar com o responsável pelo atendimento ou seguir no atendimento automático. O handoff só é aberto se o paciente escolher falar com uma pessoa.
- Categoria: `sem_informacao`
- Fonte: nenhuma. [./clinica.md](./clinica.md) não fala de estacionamento (seção 12)

### Nota final

Este documento foi gerado por inteligência artificial (IA). Todos os nomes, números, registros, endereços e dados são fictícios e não correspondem a nenhuma clínica, profissional, convênio ou pessoa real.
