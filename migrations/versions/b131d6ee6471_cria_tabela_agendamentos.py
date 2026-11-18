"""cria tabela agendamentos

Revision ID: b131d6ee6471
Revises: c77398abee4a
Create Date: 2026-10-29

Cria a tabela agendamentos (etapa 5.5). Decisoes:
- inicio e fim sao timestamptz (com fuso, gravados em UTC), excecao as demais
  tabelas, que usam timestamp sem fuso. Ver ADR 0004 e arquitetura secao 7.
- status assume so 'agendado' (ativo) e 'cancelado', garantido por CHECK.
- conflito de horario garantido por constraint EXCLUDE gist, com intervalo
  semiaberto tstzrange(inicio, fim), restrita a status 'agendado'. Precisa da
  extensao btree_gist para os operadores de igualdade de tenant_id (uuid) e
  profissional_id (integer). Ver ADR 0004.
- RLS, FORCE e policy isolamento_tenant, como as demais tabelas com tenant_id.
- grants: app_clinicas recebe SELECT/INSERT/UPDATE/DELETE pela ALTER DEFAULT
  PRIVILEGES da migration 21bc40ab245c. worker_jobs nao tem default privilege,
  entao nao recebe grant nenhum nesta tabela. Nenhum grant explicito aqui.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b131d6ee6471'
down_revision: Union[str, Sequence[str], None] = 'c77398abee4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Operadores de igualdade (tenant_id uuid, profissional_id integer) dentro do
    # indice gist da constraint EXCLUDE. Idempotente, para ambiente local e CI.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        'agendamentos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('profissional_id', sa.Integer(), nullable=False),
        sa.Column('servico_id', sa.Integer(), nullable=False),
        sa.Column('contato_telefone', sa.String(length=20), nullable=False),
        sa.Column('inicio', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fim', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), server_default=sa.text("'agendado'"), nullable=False),
        sa.Column('criada_em', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['clinicas.tenant_id'], ),
        sa.ForeignKeyConstraint(['profissional_id'], ['profissionais.id'], ),
        sa.ForeignKeyConstraint(['servico_id'], ['servicos.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('fim > inicio', name='ck_agendamentos_intervalo'),
        sa.CheckConstraint("status IN ('agendado', 'cancelado')", name='ck_agendamentos_status'),
    )
    op.create_index('idx_agendamentos_tenant', 'agendamentos', ['tenant_id'], unique=False)

    # Constraint EXCLUDE: nenhum par de agendamentos ativos do mesmo profissional da
    # mesma clinica com intervalos sobrepostos. Semiaberto, entao adjacentes nao
    # conflitam. Criada por SQL porque o Alembic nao a gera por autogenerate.
    op.execute(
        "ALTER TABLE agendamentos ADD CONSTRAINT ex_agendamentos_conflito "
        "EXCLUDE USING gist ("
        "tenant_id WITH =, profissional_id WITH =, tstzrange(inicio, fim) WITH &&"
        ") WHERE (status = 'agendado')"
    )

    # Isolamento por tenant, igual as demais tabelas (ver migration e69c546938b3)
    op.execute("ALTER TABLE agendamentos ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agendamentos FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY isolamento_tenant ON agendamentos "
        "USING (tenant_id = current_setting('app.tenant_id')::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)"
    )


def downgrade() -> None:
    # Remove na ordem inversa: policy, depois RLS, depois a tabela (que leva junto a
    # constraint EXCLUDE e o indice), e por fim a extensao, que nenhuma outra usa.
    op.execute("DROP POLICY IF EXISTS isolamento_tenant ON agendamentos")
    op.execute("ALTER TABLE agendamentos NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agendamentos DISABLE ROW LEVEL SECURITY")
    op.drop_index('idx_agendamentos_tenant', table_name='agendamentos')
    op.drop_table('agendamentos')
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
