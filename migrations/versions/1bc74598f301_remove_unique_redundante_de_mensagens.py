"""remove unique redundante de mensagens

Revision ID: 1bc74598f301
Revises: c77398abee4a
Create Date: 2026-11-15 18:00:00.000000

Correcao de 2026-11-18: o titulo e a premissa original estao errados.

A premissa era que mensagens tinha uma PK (mensagens_pkey) e uma UNIQUE
redundante (pk_mensagens). Na verdade a migration inicial declarou PK e UNIQUE
sobre a mesma coluna, e o Postgres manteve uma constraint so: a PRIMARY KEY,
com o nome da UNIQUE (uq_mensagens_message_id). A d109eb356688 renomeou essa PK
para pk_mensagens. Nao existia mensagens_pkey.

Por isso esta migration remove a unica PK de mensagens. O type_='unique' nao
muda o SQL no Postgres (ALTER TABLE ... DROP CONSTRAINT pk_mensagens). A PK
volta com a 7e9ab495716d. A cadeia ja aplicada foi mantida, e so o downgrade
foi corrigido. Detalhes na secao 0 de
docs/diagnosticos/2026-11-18-plano-rodada3.md.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '1bc74598f301'
down_revision: Union[str, Sequence[str], None] = 'c77398abee4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove pk_mensagens, que e a unica PK de mensagens (ver docstring). Mantido
    # como foi aplicado: o type_ nao altera o SQL gerado.
    op.drop_constraint('pk_mensagens', 'mensagens', type_='unique')


def downgrade() -> None:
    # Recria a PK com o nome que a d109eb356688 deixou, que era o estado original
    op.create_primary_key('pk_mensagens', 'mensagens', ['id'])
