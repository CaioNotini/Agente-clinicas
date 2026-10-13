Papel: perguntas administrativas fictícias, usadas como corpus do RAG (etapa 8) e como casos de teste (etapa 10).
Entrada: docs/status.md
Relaciona-se com: ../estudo.md (etapas 0, 8 e 10), ../arquitetura.md (seção 6-A e tabela conhecimento_clinica), ./clinica.md (dados de referência), ./perguntas_bloqueadas.md (fronteira com o que não é respondido).

# Perguntas frequentes: Clínica Fictícia

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

- Resposta: Essa pergunta é respondida pela recepção.
- Categoria: `bloqueado`
- Fonte: [./perguntas_bloqueadas.md](./perguntas_bloqueadas.md)

### Vocês fazem reembolso do convênio?

- Resposta: Essa pergunta é respondida pela recepção.
- Categoria: `bloqueado`
- Fonte: [./perguntas_bloqueadas.md](./perguntas_bloqueadas.md)

### Nota final

Este documento foi gerado por inteligência artificial (IA). Todos os nomes, números, registros, endereços e dados são fictícios e não correspondem a nenhuma clínica, profissional, convênio ou pessoa real.
