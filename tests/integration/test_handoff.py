"""Abertura de handoff da tarefa 5.4 (ADR 0009), nos dois cenarios.

abrir_handoff grava na sessao da conversa travada, sob RLS, sem commit proprio. A
conversa_travada confirma ao sair do bloco. A leitura que prova que o handoff
aparece no banco usa app_clinicas, como a aplicacao. A conta de administracao so
semeia e confere.

Destino previsto: notificado_para e notificado_canal recebem o telefone de plantao e
o canal do estudo. notificado_em fica nulo ate a etapa 13 enviar o aviso.
"""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.agenda.regras import MOTIVO_CANCELAMENTO_FORA_DA_JANELA
from app.config import DATABASE_URL
from app.core.conversas import conversa_travada
from app.handoff.abertura import (
    CANAL_ESTUDO,
    MOTIVO_CONFIGURACAO_INVALIDA,
    abrir_handoff,
)
from app.mensagens.fixas import HANDOFF_TEXTO_PACIENTE_PADRAO
from tests.cenarios_etapa5 import (
    AGORA,
    agendamento_direto,
    configurar_handoff,
    engine_admin,
    handoffs,
    limpar,
    mensagem,
    semear,
)

engine_app = create_engine(DATABASE_URL)

CONTATO = "(00) 90000-0701"
PLANTAO = "(00) 3000-0701"


@pytest.fixture
def cenarios():
    dados = semear()
    yield dados
    limpar(dados)


def _abrir(tenant, motivo=MOTIVO_CANCELAMENTO_FORA_DA_JANELA, **kwargs):
    with conversa_travada(tenant, CONTATO) as travada:
        aberto = abrir_handoff(travada, motivo, agora=AGORA, **kwargs)
        conversa_id = travada.id
    return aberto, conversa_id


def _handoffs_pela_aplicacao(tenant):
    with engine_app.connect() as conexao:
        transacao = conexao.begin()
        try:
            conexao.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant}
            )
            return conexao.execute(text("SELECT * FROM handoffs ORDER BY id")).all()
        finally:
            transacao.rollback()


def test_handoff_gravado_aparece_no_banco_com_destino_previsto(cenarios):
    """Criterio de pronto da etapa 5: um handoff gravado aparece no banco."""
    tenant = cenarios["equipe"]["tenant"]
    configurar_handoff(tenant, plantao=PLANTAO, texto="Texto da clinica.", prazo=30)

    aberto, conversa_id = _abrir(tenant)

    linhas = _handoffs_pela_aplicacao(tenant)
    assert len(linhas) == 1
    linha = linhas[0]
    texto = "Texto da clinica. O prazo de resposta é de até 30 minutos."
    assert linha.id == aberto.id
    assert (linha.conversa_id, linha.motivo) == (
        conversa_id,
        MOTIVO_CANCELAMENTO_FORA_DA_JANELA,
    )
    assert (linha.notificado_para, linha.notificado_canal) == (PLANTAO, CANAL_ESTUDO)
    assert CANAL_ESTUDO == "cli"
    assert linha.notificado_em is None
    assert linha.texto_paciente == texto == aberto.texto_paciente
    assert linha.responder_ate == AGORA + timedelta(minutes=30) == aberto.responder_ate
    assert (linha.agendamento_id, linha.mensagem_id) == (None, None)
    assert (linha.assumido_por, linha.assumido_em, linha.devolvido_em) == (
        None,
        None,
        None,
    )


def test_consultorio_sem_plantao_texto_nem_prazo(cenarios):
    tenant = cenarios["solo"]["tenant"]

    aberto, _ = _abrir(tenant, MOTIVO_CONFIGURACAO_INVALIDA)

    linha = handoffs(tenant)[0]
    assert (linha.notificado_para, linha.notificado_canal) == (None, None)
    assert linha.texto_paciente == HANDOFF_TEXTO_PACIENTE_PADRAO == aberto.texto_paciente
    assert linha.responder_ate is None
    assert linha.motivo == MOTIVO_CONFIGURACAO_INVALIDA == "configuracao_invalida"


@pytest.mark.parametrize("prazo", [0, -5])
def test_prazo_nao_positivo_e_tratado_como_nao_informado(cenarios, prazo):
    tenant = cenarios["equipe"]["tenant"]
    configurar_handoff(tenant, plantao=PLANTAO, prazo=prazo)

    aberto, _ = _abrir(tenant)

    linha = handoffs(tenant)[0]
    assert linha.responder_ate is None
    assert linha.texto_paciente == HANDOFF_TEXTO_PACIENTE_PADRAO == aberto.texto_paciente


def test_handoff_nao_muda_o_estado_da_conversa(cenarios):
    """A 5.4 so grava (etapas.md). O estado e o human_mode ficam como estavam."""
    tenant = cenarios["equipe"]["tenant"]
    with conversa_travada(tenant, CONTATO):
        pass  # cria a conversa

    def estado():
        with engine_admin.connect() as conexao:
            return tuple(
                conexao.execute(
                    text(
                        "SELECT estado_conversa, human_mode FROM conversas "
                        "WHERE tenant_id = :t AND contato_telefone = :tel"
                    ),
                    {"t": tenant, "tel": CONTATO},
                ).first()
            )

    antes = estado()
    _abrir(tenant)
    assert estado() == antes == ("idle", False)


def test_grava_agendamento_e_mensagem_de_origem(cenarios):
    equipe = cenarios["equipe"]
    inicio = AGORA + timedelta(days=1)
    ag = agendamento_direto(
        equipe["tenant"],
        equipe["prof"],
        equipe["serv"],
        CONTATO,
        inicio,
        inicio + timedelta(minutes=30),
    )
    msg = mensagem(equipe["tenant"], CONTATO)

    _abrir(equipe["tenant"], agendamento_id=ag, mensagem_id=msg)

    linha = handoffs(equipe["tenant"])[0]
    assert (linha.agendamento_id, linha.mensagem_id) == (ag, msg)


def test_agora_sem_fuso_e_recusado_sem_gravar(cenarios):
    tenant = cenarios["equipe"]["tenant"]
    with pytest.raises(ValueError):
        with conversa_travada(tenant, CONTATO) as travada:
            abrir_handoff(
                travada, MOTIVO_CONFIGURACAO_INVALIDA, agora=AGORA.replace(tzinfo=None)
            )
    assert handoffs(tenant) == []


def test_sem_commit_proprio_o_rollback_da_conversa_desfaz_o_handoff(cenarios):
    tenant = cenarios["equipe"]["tenant"]
    with pytest.raises(RuntimeError):
        with conversa_travada(tenant, CONTATO) as travada:
            abrir_handoff(travada, MOTIVO_CONFIGURACAO_INVALIDA, agora=AGORA)
            raise RuntimeError("falha depois de abrir")
    assert handoffs(tenant) == []


def test_texto_da_clinica_no_limite_com_prazo_cabe_no_registro(cenarios):
    tenant = cenarios["equipe"]["tenant"]
    configurar_handoff(tenant, texto="a" * 500, prazo=2_147_483_647)

    aberto, _ = _abrir(tenant)

    assert handoffs(tenant)[0].texto_paciente == aberto.texto_paciente
    assert aberto.texto_paciente.startswith("a" * 500)


def test_texto_da_clinica_acima_de_500_e_recusado_ao_gravar_a_configuracao(cenarios):
    """O limite vale na gravacao da configuracao, pela aplicacao (app_clinicas), e
    nao so na abertura do handoff."""
    tenant = cenarios["equipe"]["tenant"]
    with engine_app.connect() as conexao:
        transacao = conexao.begin()
        try:
            conexao.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant}
            )
            with pytest.raises(DBAPIError) as erro:
                conexao.execute(
                    text("UPDATE clinicas SET handoff_texto_paciente = :x"),
                    {"x": "a" * 501},
                )
            assert erro.value.orig.pgcode == "22001"  # string_data_right_truncation
        finally:
            transacao.rollback()
