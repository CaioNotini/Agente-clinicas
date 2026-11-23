Papel: segundo tenant fictício, consultório de um profissional só, sem recepção, para testar as regras da etapa 5 nos dois cenários.
Entrada: docs/status.md
Relaciona-se com: ../etapas.md (etapa 5), ./clinica.md (cenário com equipe e recepção), ../decisions/0009-agendamento-handoff-etapa5.md (decisões que este cenário exercita).

# Consultório Fictício Solo: um profissional só, sem recepção

**Versão:** 1.0
**Última revisão:** novembro de 2026
**Papel no projeto:** representar o público-alvo de consultórios sem secretária nem recepção, em que o próprio profissional recebe os handoffs.

Este documento é dado fictício de teste. Ele não traz FAQ nem corpus de RAG, porque serve para exercitar as regras determinísticas da etapa 5, não a recuperação de dúvidas. O corpus completo fica na [clínica com equipe](./clinica.md).

---

## 1. Identificação

- **Nome fantasia:** Consultório Fictício Solo
- **CNPJ:** 00.000.000/0002-00 (número fictício)
- **Endereço:** Avenida Fictícia, 200, bairro fictício, Manaus, AM
- **Telefone de contato:** (00) 0000-0002
- **Telefone de plantão:** (00) 0000-0003 (o do próprio profissional, não há recepção)
- **E-mail institucional:** contato@solo.invalid
- **Especialidade atendida:** Nutrição

---

## 2. Quem atende

Um profissional só, sem secretária nem recepção. O próprio profissional recebe os avisos de handoff no WhatsApp pessoal de plantão. Não existe um papel separado de recepção neste consultório.

- **Profissional:** Profissional Solo Fictício, nutrição.

---

## 3. Configuração que este cenário exercita

As decisões do [ADR 0009](../decisions/0009-agendamento-handoff-etapa5.md) são testadas aqui com valores diferentes dos da clínica com equipe, para que as regras valham nos dois cenários.

- **Fuso (Q-23):** `America/Manaus`, UTC-4 sem horário de verão. Diferente do default `America/Sao_Paulo` de propósito, para a conversão de fuso ser exercida com outro offset.
- **Duração (Q-21):** a duração padrão da consulta vem do serviço, e este profissional usa um override em `profissional_servicos.duracao_minutos`, diferente da duração do serviço, para o cálculo do fim usar o override.
- **Cancelamento fora da janela (Q-22):** política `aceitar_e_marcar`. Como não há ninguém monitorando handoff na hora, um cancelamento tardio é aceito e marcado, sem abrir handoff.
- **Antecedência mínima para agendar:** 24 horas.
- **Antecedência máxima para agendar:** 30 dias.
- **Janela de cancelamento:** 24 horas.
- **Horário de atendimento:** segunda a sexta, 09:00 às 17:00, sem pausa. Sábado e domingo fechado.
- **Handoff (Q-24):** o destinatário do aviso é o telefone de plantão acima, que é o do próprio profissional. `notificado_para` registra quem de fato recebeu.

---

## 4. Atendimento de urgência

Este consultório não faz atendimento de urgência nem de emergência. Em caso de emergência, o paciente deve ligar 192 ou procurar o pronto-socorro mais próximo. A mensagem fixa de urgência não depende de o handoff ser atendido.
