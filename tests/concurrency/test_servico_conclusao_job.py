"""Servico de agendamento com a conclusao atomica do job (ADR 0008, tarefa 5.3).

O processamento cria ou remarca pelo servico e conclui o job na mesma sessao da
conversa travada, antes do commit. Os testes provam que o agendamento so existe se
o job foi concluido por quem ainda e dono dele.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.agenda import servico
from app.channels.base import MensagemEntrada
from app.core.conversas import conversa_travada
from app.jobs import worker
from app.jobs.queue import concluir_job, gravar_e_enfileirar
from tests.cenarios_etapa5 import (
    AGORA,
    agendamentos,
    engine_admin,
    handoffs,
    limpar,
    semear,
)

UTC = timezone.utc
CONTATO = "(00) 90000-0901"
INICIO = datetime(2027, 3, 5, 13, tzinfo=UTC)  # sexta 10:00 em Sao Paulo


@pytest.fixture
def equipe():
    dados = semear()
    yield dados["equipe"]
    limpar(dados)


def _enfileirar(tenant):
    mensagem = MensagemEntrada(
        id=uuid.uuid4().hex, tenant_id=tenant, contato_telefone=CONTATO, conteudo="oi"
    )
    return gravar_e_enfileirar(mensagem).job_id


def _job(job_id):
    with engine_admin.connect() as conexao:
        return conexao.execute(
            text("SELECT status, locked_by FROM jobs WHERE id = :id"), {"id": job_id}
        ).first()


def _outro_worker_assume(job):
    with engine_admin.begin() as conexao:
        conexao.execute(
            text("UPDATE jobs SET locked_by = 'worker-outro' WHERE id = :id"),
            {"id": job.id},
        )


def _processamento(equipe, operacao, antes_de_concluir=None):
    def processar(conexao, job):
        with conversa_travada(
            job.tenant_id, job.payload["contato_telefone"]
        ) as travada:
            operacao(travada)
            if antes_de_concluir is not None:
                antes_de_concluir(job)
            concluir_job(travada.session, job)

    return processar


def _criacao(equipe, inicio=INICIO):
    def operacao(travada):
        servico.criar(
            travada,
            profissional_id=equipe["prof"],
            servico_id=equipe["serv"],
            inicio=inicio,
            agora=AGORA,
        )

    return operacao


def test_caminho_feliz_cria_e_conclui(equipe):
    job_id = _enfileirar(equipe["tenant"])
    worker.processar_um(
        "worker-a", processamento=_processamento(equipe, _criacao(equipe))
    )

    assert len(agendamentos(equipe["tenant"], status="agendado")) == 1
    assert tuple(_job(job_id)) == ("done", "worker-a")


def test_worker_que_perdeu_o_job_desfaz_o_agendamento(equipe):
    job_id = _enfileirar(equipe["tenant"])
    worker.processar_um(
        "worker-a",
        processamento=_processamento(
            equipe, _criacao(equipe), antes_de_concluir=_outro_worker_assume
        ),
    )

    assert agendamentos(equipe["tenant"]) == []
    assert tuple(_job(job_id)) == ("processing", "worker-outro")


def test_queda_depois_da_conclusao_nao_duplica(equipe, monkeypatch):
    job_id = _enfileirar(equipe["tenant"])

    def queda(*args, **kwargs):
        raise RuntimeError("queda simulada")

    monkeypatch.setattr(worker, "finalizar_job", queda)
    with pytest.raises(RuntimeError):
        worker.processar_um(
            "worker-a", processamento=_processamento(equipe, _criacao(equipe))
        )
    monkeypatch.undo()
    worker.processar_um(
        "worker-b",
        processamento=_processamento(equipe, _criacao(equipe)),
        limite_segundos=0,
    )

    assert len(agendamentos(equipe["tenant"])) == 1
    assert _job(job_id).status == "done"


def test_remarcacao_de_worker_que_perdeu_o_job_mantem_o_antigo(equipe):
    with conversa_travada(equipe["tenant"], CONTATO) as travada:
        antigo = servico.criar(
            travada,
            profissional_id=equipe["prof"],
            servico_id=equipe["serv"],
            inicio=INICIO,
            agora=AGORA,
        ).agendamento

    def remarcacao(travada):
        servico.remarcar(
            travada, antigo.id, novo_inicio=INICIO + timedelta(hours=1), agora=AGORA
        )

    _enfileirar(equipe["tenant"])
    worker.processar_um(
        "worker-a",
        processamento=_processamento(
            equipe, remarcacao, antes_de_concluir=_outro_worker_assume
        ),
    )

    linhas = agendamentos(equipe["tenant"])
    assert [(linha.id, linha.status) for linha in linhas] == [(antigo.id, "agendado")]


# --- handoff da 5.4 com a conclusao do job ---------------------------------------


def _cancelamento_fora_da_janela(antigo_id):
    def operacao(travada):
        # 10 h antes do inicio, fora da janela de 48 h da equipe (politica handoff)
        servico.cancelar(travada, antigo_id, agora=INICIO - timedelta(hours=10))

    return operacao


def _agendamento(equipe):
    with conversa_travada(equipe["tenant"], CONTATO) as travada:
        return servico.criar(
            travada,
            profissional_id=equipe["prof"],
            servico_id=equipe["serv"],
            inicio=INICIO,
            agora=AGORA,
        ).agendamento


def test_handoff_e_confirmado_junto_com_o_job(equipe):
    antigo = _agendamento(equipe)
    job_id = _enfileirar(equipe["tenant"])
    worker.processar_um(
        "worker-a",
        processamento=_processamento(equipe, _cancelamento_fora_da_janela(antigo.id)),
    )

    assert [linha.agendamento_id for linha in handoffs(equipe["tenant"])] == [antigo.id]
    assert tuple(_job(job_id)) == ("done", "worker-a")


def test_worker_que_perdeu_o_job_desfaz_o_handoff(equipe):
    antigo = _agendamento(equipe)
    job_id = _enfileirar(equipe["tenant"])
    worker.processar_um(
        "worker-a",
        processamento=_processamento(
            equipe,
            _cancelamento_fora_da_janela(antigo.id),
            antes_de_concluir=_outro_worker_assume,
        ),
    )

    assert handoffs(equipe["tenant"]) == []
    assert tuple(_job(job_id)) == ("processing", "worker-outro")
