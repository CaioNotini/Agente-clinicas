"""fks compostas por tenant

Revision ID: 8b3e1f6a2c90
Revises: 5f2c8a1d9e47
Create Date: 2026-11-18 20:00:00.000000

FKs entre tabelas de clinica passam a referenciar (tenant_id, id), para o banco
recusar uma linha de uma clinica que aponte para registro de outra. A
verificacao de FK ignora o RLS, entao a FK simples sobre id nao protegia.
Ver docs/decisions/0007-fks-compostas-por-tenant.md.

Ordem: verificacao dos dados, UNIQUE (tenant_id, id) nos pais, troca das FKs.
Nenhuma policy, role ou grant muda.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8b3e1f6a2c90'
down_revision: Union[str, Sequence[str], None] = '5f2c8a1d9e47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tabelas pai que recebem UNIQUE (tenant_id, id)
PAIS = ("profissionais", "servicos", "conversas")

# (tabela filha, coluna, tabela pai)
FKS = (
    ("agendamentos", "profissional_id", "profissionais"),
    ("agendamentos", "servico_id", "servicos"),
    ("horarios_trabalho", "profissional_id", "profissionais"),
    ("profissional_servicos", "profissional_id", "profissionais"),
    ("profissional_servicos", "servico_id", "servicos"),
    ("handoffs", "conversa_id", "conversas"),
)


def upgrade() -> None:
    # 1. Para se ja existir referencia cruzada: a FK composta nao poderia ser criada,
    # e os dados precisam de correcao manual. Nada e apagado.
    for filha, coluna, pai in FKS:
        op.execute(
            f"""
            DO $$
            DECLARE cruzadas int;
            BEGIN
                SELECT count(*) INTO cruzadas
                FROM {filha} f JOIN {pai} p ON p.id = f.{coluna}
                WHERE p.tenant_id <> f.tenant_id;
                IF cruzadas > 0 THEN
                    RAISE EXCEPTION
                        '{filha}.{coluna}: % linha(s) apontam para {pai} de outra clinica: corrigir antes de migrar',
                        cruzadas;
                END IF;
            END
            $$
            """
        )

    # 2. Alvo das FKs compostas. O id ja e PK, a UNIQUE existe so para a FK.
    for pai in PAIS:
        op.create_unique_constraint(f"uq_{pai}_tenant_id_id", pai, ["tenant_id", "id"])

    # 3. Troca cada FK simples pela composta
    for filha, coluna, pai in FKS:
        op.drop_constraint(f"{filha}_{coluna}_fkey", filha, type_="foreignkey")
        op.create_foreign_key(
            f"fk_{filha}_{coluna}_tenant",
            filha,
            pai,
            ["tenant_id", coluna],
            ["tenant_id", "id"],
        )


def downgrade() -> None:
    for filha, coluna, pai in reversed(FKS):
        op.drop_constraint(f"fk_{filha}_{coluna}_tenant", filha, type_="foreignkey")
        # Recria a FK simples com o nome que o Postgres tinha dado
        op.create_foreign_key(f"{filha}_{coluna}_fkey", filha, pai, [coluna], ["id"])

    for pai in reversed(PAIS):
        op.drop_constraint(f"uq_{pai}_tenant_id_id", pai, type_="unique")
