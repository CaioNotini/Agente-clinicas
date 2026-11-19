```
Papel: registra como o banco impede que uma linha de uma clínica aponte para registro de outra.
Entrada: docs/status.md
Relaciona-se com: 0002-contas-de-banco.md, 0004-conflito-de-horario.md, ../arquitetura.md (seção 7), ../../app/db/models.py, ../../tests/isolation/test_fk_tenant.py, ../../tests/isolation/test_isolation_rls.py
```

# 0007: FKs compostas com tenant_id

## Contexto

O item A1 do [plano de 2026-11-18](../diagnosticos/2026-11-18-plano-rodada3.md) apontou que as FKs entre tabelas de clínica referenciam só o `id` do registro pai. A verificação de FK do Postgres ignora o RLS. Então uma sessão `app_clinicas` da clínica A grava uma linha que aponta para um registro da clínica B, desde que o `id` exista, mesmo invisível para A.

Isso foi confirmado em 2026-11-18 por [`test_fk_tenant.py`](../../tests/isolation/test_fk_tenant.py). As 6 inserções e as 6 alterações com o registro pai de outra clínica passaram, e os 6 controles com registros da própria clínica também. FKs afetadas:

- `agendamentos.profissional_id` e `agendamentos.servico_id`
- `horarios_trabalho.profissional_id`
- `profissional_servicos.profissional_id` e `profissional_servicos.servico_id`
- `handoffs.conversa_id`

Os ids são sequenciais, então adivinhar um id de outra clínica é fácil. O efeito seria, por exemplo, um agendamento de A com o profissional de B, que entra na constraint EXCLUDE do [ADR 0004](./0004-conflito-de-horario.md) com o `tenant_id` de A e não conflita com a agenda real de B. A regra 6 do CLAUDE.md pede isolamento também nos relacionamentos.

## Alternativas consideradas

- **Validar no código antes de gravar.** Descartada: a validação seria só a segunda barreira, dependeria de todo caminho de escrita lembrar dela, e não vale para SQL manual nem para o painel futuro.
- **Trigger que compara o `tenant_id` da linha filha com o do pai.** Descartada: faz o mesmo que a FK composta com código procedural, que precisa ser escrito e testado para cada par de tabelas, e não aparece no catálogo como restrição de integridade.
- **Chave primária composta `(tenant_id, id)` nas tabelas pai.** Descartada: troca a PK de tabelas que já existem e muda todas as referências e o ORM. A UNIQUE extra chega ao mesmo resultado sem mexer na PK.
- **Tirar `tenant_id` das tabelas filhas e derivar do pai.** Descartada: a policy `isolamento_tenant` e os testes de isolamento dependem de `tenant_id` em cada tabela.
- **FK composta, com UNIQUE `(tenant_id, id)` nas tabelas pai.** Escolhida.

## Decisão

Toda FK de uma tabela de clínica para outra tabela de clínica referencia `(tenant_id, id)`, e não só `id`. As tabelas pai `profissionais`, `servicos` e `conversas` ganham UNIQUE `(tenant_id, id)`. As 6 FKs da lista passam a ser compostas e substituem as FKs simples.

## Justificativa

A FK composta faz o próprio banco recusar a referência cruzada, em qualquer caminho de escrita e para qualquer role. Como a linha filha já precisa ter o `tenant_id` da sessão pela policy, o pai referenciado precisa ser da mesma clínica. É uma restrição declarativa, visível no catálogo e verificável por teste automático. Ela não depende de código procedural.

## Consequências

**Schema.**

- UNIQUE nova em `profissionais`, `servicos` e `conversas`, com os nomes `uq_<tabela>_tenant_id_id`. O `id` já é PK, então a UNIQUE é redundante como unicidade e existe só como alvo da FK. Custo: um índice a mais por tabela pai.
- As 6 FKs simples são removidas e entram as compostas, com os nomes `fk_<tabela>_<coluna>_tenant`. O comportamento de exclusão continua o atual (`NO ACTION`).
- As colunas envolvidas já são `NOT NULL`, então a FK composta vale sempre, sem o caso de `MATCH SIMPLE` com coluna nula.
- A FK composta também impede trocar o `tenant_id` de um registro pai que tem filhos.
- `app/db/models.py` passa a declarar as UNIQUEs e as FKs compostas, para o `alembic check` continuar sem diferença.
- Índices nas colunas filhas das FKs continuam no item C1 do plano, fora desta decisão.

**Migration.**

- Ordem do upgrade: verificação dos dados, UNIQUEs nos pais, remoção das FKs simples e criação das compostas.
- Antes de qualquer alteração, a migration para com erro explícito se existir uma linha filha cujo pai é de outra clínica. A mensagem diz a FK e a quantidade de linhas, sem apagar nada. A correção desses dados fica a cargo do desenvolvedor.
- O downgrade desfaz tudo na ordem inversa e recria as FKs simples com os nomes atuais (`<tabela>_<coluna>_fkey`).
- Nenhuma policy, role ou grant muda.

**Testes.**

- Os 12 testes de [`test_fk_tenant.py`](../../tests/isolation/test_fk_tenant.py) que falham hoje devem passar, com o código `23503`. Os 6 controles continuam passando.
- O teste de cobertura do catálogo em [`test_isolation_rls.py`](../../tests/isolation/test_isolation_rls.py) ganha uma verificação: falha se alguma FK de uma tabela com `tenant_id` para outra tabela com `tenant_id` não incluir `tenant_id` nos dois lados, exceto a FK para `clinicas.tenant_id`. Assim uma tabela nova com FK simples é detectada sem depender de lembrar de escrever o teste.
- O ciclo de migrations da CI cobre o upgrade e o downgrade.

**Regra para tabelas novas.** Uma tabela nova com `tenant_id` que referencia outra tabela de clínica usa FK composta. Isso entra no critério da regra 20 do CLAUDE.md, verificado pelo teste do catálogo.

## Status

Aceita em 2026-11-18.
