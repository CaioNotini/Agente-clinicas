"""Lock por conversa com SELECT ... FOR UPDATE (etapa 4.2).

Impede que duas mensagens da mesma conversa, identificada por
(tenant_id, contato_telefone), sejam processadas ao mesmo tempo. A segunda
transacao que tentar travar a mesma linha espera ate a primeira liberar
(FOR UPDATE, sem SKIP nem NOWAIT), entao as mensagens sao processadas em serie,
sem sobreposicao. O lock nao garante a ordem de chegada entre workers. A ordem
vem da captura no worker (docs/decisions/0005-ordem-por-conversa.md), e o lock
fica como segunda barreira contra escritas concorrentes na mesma conversa.

Conta de banco: a conversa e dado especifico de clinica, e a role worker_jobs
so tem SELECT em conversas (ver docs/decisions/0002-contas-de-banco.md). Por
isso o lock roda em sessao app_clinicas (SessionLocal), sujeita ao RLS, com
app.tenant_id definido na propria transacao. Isso tambem prepara a tarefa 4.4.

Escopo da etapa 4.2: so o lock e o buscar-ou-criar da conversa. Qual transicao
de estado aplicar depende de classificacao de intencao e entra a partir da
etapa 7 (ver docs/decisions/0003-grafo-de-transicoes.md). Aqui a conversa nova
nasce no ESTADO_INICIAL e nenhuma aresta do grafo e decidida.
"""
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import text

from app.core.estados import ESTADO_INICIAL
from app.db.database import SessionLocal

# Limite de espera pelo lock da conversa, em milissegundos. Uma segunda mensagem
# da mesma conversa espera a primeira liberar (FOR UPDATE que bloqueia), mas nao
# para sempre: passado este tempo a transacao recebe erro de lock_timeout e sai,
# em vez de prender a thread do worker. O valor fica bem abaixo do limite de
# orfao do worker (LIMITE_LOCK_SEGUNDOS = 300 s em app/jobs/worker.py): assim um
# esperante erra muito antes de o job em processing ser considerado orfao e
# recapturado, o que evitaria dois processamentos simultaneos da mesma conversa.
LOCK_TIMEOUT_MS = 5000


@dataclass(frozen=True)
class ConversaTravada:
    """Conversa cuja linha esta travada pela transacao aberta no bloco."""

    id: int
    tenant_id: str
    contato_telefone: str
    estado_conversa: str


@contextmanager
def conversa_travada(
    tenant_id,
    contato_telefone,
    session_factory=SessionLocal,
    lock_timeout_ms=LOCK_TIMEOUT_MS,
):
    """Trava a linha da conversa (tenant_id, contato_telefone) ate o fim do bloco.

    Abre uma transacao app_clinicas, define app.tenant_id, garante que a conversa
    existe (buscar-ou-criar) e trava a linha com SELECT ... FOR UPDATE. O lock e a
    transacao duram enquanto o bloco with estiver aberto: uma segunda chamada para
    a mesma conversa espera neste ponto ate a primeira sair e liberar o lock.

    Ao sair do bloco sem erro, faz commit; em excecao, faz rollback. A sessao e
    sempre fechada.
    """
    tenant_id = str(tenant_id)
    session = session_factory()
    try:
        # Tenant definido so para esta transacao (is_local=true), como a aplicacao faria
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": tenant_id},
        )

        # Limite de espera pelo lock, so para esta transacao (is_local=true). Se o
        # FOR UPDATE abaixo esperar mais que isto, o Postgres cancela com erro de
        # lock_timeout, a transacao faz rollback e a thread e liberada.
        session.execute(
            text("SELECT set_config('lock_timeout', :ms, true)"),
            {"ms": str(lock_timeout_ms)},
        )

        # Buscar-ou-criar sem corrida: se outra transacao ja criou a conversa, o
        # ON CONFLICT nao sobrescreve nada. A unicidade e (tenant_id, contato_telefone).
        session.execute(
            text(
                "INSERT INTO conversas (tenant_id, contato_telefone, estado_conversa) "
                "VALUES (:t, :tel, :estado) "
                "ON CONFLICT (tenant_id, contato_telefone) DO NOTHING"
            ),
            {"t": tenant_id, "tel": contato_telefone, "estado": ESTADO_INICIAL},
        )

        # Trava a linha. FOR UPDATE sem SKIP/NOWAIT: a segunda transacao espera aqui.
        linha = session.execute(
            text(
                "SELECT id, tenant_id, contato_telefone, estado_conversa "
                "FROM conversas "
                "WHERE tenant_id = :t AND contato_telefone = :tel "
                "FOR UPDATE"
            ),
            {"t": tenant_id, "tel": contato_telefone},
        ).first()

        travada = ConversaTravada(
            id=linha.id,
            tenant_id=str(linha.tenant_id),
            contato_telefone=linha.contato_telefone,
            estado_conversa=linha.estado_conversa,
        )

        yield travada

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
