"""ordem por conversa em jobs e restricoes de jobs, conversas e mensagens

Revision ID: 5f2c8a1d9e47
Revises: 7e9ab495716d
Create Date: 2026-11-18 12:00:00.000000

Ver docs/decisions/0005-ordem-por-conversa.md. A coluna jobs.contato_telefone
identifica a conversa do job, e o indice parcial atende a verificacao de job
anterior pendente na captura. As restricoes (NOT NULL, server_default e CHECK)
impedem jobs que nunca seriam capturados e valores fora do dominio.

Ordem do upgrade: coluna nova, verificacao dos dados sem conversao segura,
preenchimento dos dados existentes, e so entao NOT NULL, CHECK e indice.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f2c8a1d9e47'
down_revision: Union[str, Sequence[str], None] = '7e9ab495716d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_JOB = "('pending', 'processing', 'done', 'dead')"
ESTADOS_CONVERSA = "('idle', 'coletando_info', 'aguardando_confirmacao', 'escalada', 'encerrada')"
DIRECOES = "('entrada', 'saida')"


def upgrade() -> None:
    op.add_column('jobs', sa.Column('contato_telefone', sa.String(length=20), nullable=True))

    # Dados sem conversao segura param a migration, sem apagar nada
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM jobs WHERE type = 'PROCESS_INBOUND_MESSAGE'
                AND (payload IS NULL OR payload->>'contato_telefone' IS NULL)
            ) THEN
                RAISE EXCEPTION 'jobs PROCESS_INBOUND_MESSAGE sem contato_telefone no payload: corrigir antes de migrar';
            END IF;
            IF EXISTS (SELECT 1 FROM jobs WHERE status NOT IN {STATUS_JOB}) THEN
                RAISE EXCEPTION 'jobs com status desconhecido: corrigir antes de migrar';
            END IF;
            IF EXISTS (SELECT 1 FROM conversas WHERE estado_conversa NOT IN {ESTADOS_CONVERSA}) THEN
                RAISE EXCEPTION 'conversas com estado desconhecido: corrigir antes de migrar';
            END IF;
            IF EXISTS (SELECT 1 FROM mensagens WHERE direcao NOT IN ('entrada', 'saida', 'in', 'out')) THEN
                RAISE EXCEPTION 'mensagens com direcao desconhecida: corrigir antes de migrar';
            END IF;
        END $$;
    """)

    # Preenchimento dos dados existentes. A migration roda como superusuario,
    # que nao e afetado pelo RLS, entao alcanca todos os tenants.
    op.execute(
        "UPDATE jobs SET contato_telefone = payload->>'contato_telefone' "
        "WHERE type = 'PROCESS_INBOUND_MESSAGE'"
    )
    op.execute("UPDATE jobs SET status = 'pending' WHERE status IS NULL")
    op.execute("UPDATE jobs SET run_at = coalesce(criada_em, now()) WHERE run_at IS NULL")
    op.execute("UPDATE jobs SET attempts = 0 WHERE attempts IS NULL")
    op.execute("UPDATE jobs SET max_attempts = 3 WHERE max_attempts IS NULL")
    op.execute("UPDATE conversas SET estado_conversa = 'idle' WHERE estado_conversa IS NULL")
    op.execute("UPDATE conversas SET human_mode = false WHERE human_mode IS NULL")
    op.execute("UPDATE mensagens SET direcao = 'entrada' WHERE direcao = 'in'")
    op.execute("UPDATE mensagens SET direcao = 'saida' WHERE direcao = 'out'")

    # jobs
    op.alter_column('jobs', 'status', nullable=False, server_default=sa.text("'pending'"))
    op.alter_column('jobs', 'run_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('jobs', 'attempts', nullable=False, server_default=sa.text('0'))
    op.alter_column('jobs', 'max_attempts', nullable=False, server_default=sa.text('3'))
    op.create_check_constraint('ck_jobs_status', 'jobs', f"status IN {STATUS_JOB}")
    op.create_check_constraint(
        'ck_jobs_mensagem_tem_conversa', 'jobs',
        "type <> 'PROCESS_INBOUND_MESSAGE' OR contato_telefone IS NOT NULL",
    )
    op.create_index(
        'idx_jobs_conversa_pendentes', 'jobs', ['tenant_id', 'contato_telefone', 'id'],
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
    )

    # conversas
    op.alter_column('conversas', 'estado_conversa', nullable=False, server_default=sa.text("'idle'"))
    op.alter_column('conversas', 'human_mode', nullable=False, server_default=sa.text('false'))
    op.create_check_constraint('ck_conversas_estado', 'conversas', f"estado_conversa IN {ESTADOS_CONVERSA}")

    # mensagens: direcao continua aceitando NULL
    op.create_check_constraint('ck_mensagens_direcao', 'mensagens', f"direcao IN {DIRECOES}")


def downgrade() -> None:
    # Desfaz o schema. Os dados preenchidos no upgrade (nulos e 'in'/'out')
    # nao voltam ao valor anterior, que nao foi guardado e e valido no schema antigo.
    op.drop_constraint('ck_mensagens_direcao', 'mensagens', type_='check')

    op.drop_constraint('ck_conversas_estado', 'conversas', type_='check')
    op.alter_column('conversas', 'human_mode', nullable=True, server_default=None)
    op.alter_column('conversas', 'estado_conversa', nullable=True, server_default=None)

    op.drop_index('idx_jobs_conversa_pendentes', table_name='jobs')
    op.drop_constraint('ck_jobs_mensagem_tem_conversa', 'jobs', type_='check')
    op.drop_constraint('ck_jobs_status', 'jobs', type_='check')
    op.alter_column('jobs', 'max_attempts', nullable=True, server_default=None)
    op.alter_column('jobs', 'attempts', nullable=True, server_default=None)
    op.alter_column('jobs', 'run_at', nullable=True, server_default=None)
    op.alter_column('jobs', 'status', nullable=True, server_default=None)
    op.drop_column('jobs', 'contato_telefone')
