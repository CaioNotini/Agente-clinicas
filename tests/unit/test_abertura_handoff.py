"""Abertura de handoff sem banco, e erros permanentes do job (tarefa 5.4).

A sessao falsa cobre o caso que o banco real nao produz com uma conversa travada:
a clinica da sessao nao aparecer na leitura da configuracao.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.agenda.regras import ConfiguracaoInvalida, MisturaDeTenants, RegraViolada
from app.core.erros import ErroPermanente
from app.handoff.abertura import MOTIVO_CONFIGURACAO_INVALIDA, abrir_handoff
from app.jobs.queue import ColisaoIdEntreTenants, JobPerdido

AGORA = datetime(2027, 3, 1, 12, tzinfo=timezone.utc)


class _Resultado:
    def first(self):
        return None


class _SessaoSemClinica:
    def __init__(self):
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append(str(sql))
        return _Resultado()


@dataclass
class _Travada:
    session: object
    id: int = 1


def test_clinica_nao_encontrada_e_configuracao_invalida_sem_gravar():
    sessao = _SessaoSemClinica()
    with pytest.raises(ConfiguracaoInvalida):
        abrir_handoff(_Travada(sessao), MOTIVO_CONFIGURACAO_INVALIDA, agora=AGORA)
    assert not any("INSERT" in sql for sql in sessao.sql)


def test_agora_sem_fuso_e_recusado_antes_de_ler_o_banco():
    sessao = _SessaoSemClinica()
    with pytest.raises(ValueError):
        abrir_handoff(
            _Travada(sessao),
            MOTIVO_CONFIGURACAO_INVALIDA,
            agora=AGORA.replace(tzinfo=None),
        )
    assert sessao.sql == []


@pytest.mark.parametrize("erro", [ConfiguracaoInvalida, MisturaDeTenants])
def test_configuracao_invalida_e_mistura_de_tenants_sao_permanentes(erro):
    assert issubclass(erro, ErroPermanente)
    assert not issubclass(erro, RegraViolada)


@pytest.mark.parametrize("erro", [RegraViolada, JobPerdido, ColisaoIdEntreTenants])
def test_outros_erros_nao_sao_permanentes(erro):
    assert not issubclass(erro, ErroPermanente)
