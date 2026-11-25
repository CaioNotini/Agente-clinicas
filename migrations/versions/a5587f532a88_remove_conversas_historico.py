"""remove conversas.historico

C6 da rodada 3, decidido em 2026-11-25: remover a coluna conversas.historico.
Ela nunca foi lida nem escrita. O contexto do LLM da etapa 7 vem das ultimas
mensagens do contato, direto de mensagens (contato_telefone, conteudo, direcao,
criada_em por tenant), entao historico so duplicaria o dado, com risco de
divergencia e mais um ponto a apagar na exclusao do titular (LGPD). Um resumo de
conversas longas, se preciso na etapa 7, sera coluna nova com contrato e ADR.

A coluna e nullable e sem uso, entao o drop nao perde dado de aplicacao. O
downgrade a recria igual (JSON, nullable), como estava no schema inicial. Nenhuma
policy, role ou grant muda: conversas continua com a policy isolamento_tenant.

Revision ID: a5587f532a88
Revises: c3d8e5a1f297
Create Date: 2026-11-25 15:04:40.384963

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5587f532a88'
down_revision: Union[str, Sequence[str], None] = 'c3d8e5a1f297'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('conversas', 'historico')


def downgrade() -> None:
    op.add_column('conversas', sa.Column('historico', sa.JSON(), nullable=True))
