"""Nova tentativa no 40P01 e traducao do 23P01 na insercao (ADR 0004, tarefa 5.3).

Sessao e agenda falsas: o teste controla qual erro do banco cada tentativa recebe,
o que nao da para forcar de forma deterministica num banco real.
"""
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.agenda import servico


class _Orig(Exception):
    def __init__(self, pgcode):
        super().__init__(pgcode)
        self.pgcode = pgcode


def _erro(pgcode):
    classe = IntegrityError if pgcode == "23P01" else OperationalError
    return classe("INSERT INTO agendamentos ...", {}, _Orig(pgcode))


class _Savepoint:
    def __init__(self, registro):
        self.registro = registro

    def commit(self):
        self.registro.append("commit")

    def rollback(self):
        self.registro.append("rollback")


class _Sessao:
    def __init__(self):
        self.registro = []

    def begin_nested(self):
        self.registro.append("savepoint")
        return _Savepoint(self.registro)


class _Agenda:
    """criar levanta, em ordem, os erros dados. Depois deles, devolve 'novo'."""

    def __init__(self, *erros):
        self.erros = list(erros)
        self.chamadas = 0

    def criar(self, session, **campos):
        self.chamadas += 1
        if self.erros:
            raise self.erros.pop(0)
        return "novo"


def test_sem_erro_grava_na_primeira():
    sessao, agenda = _Sessao(), _Agenda()
    assert servico._inserir_com_savepoint(sessao, agenda, {}) == "novo"
    assert sessao.registro == ["savepoint", "commit"]


def test_40p01_tenta_de_novo_ate_gravar():
    sessao, agenda = _Sessao(), _Agenda(_erro("40P01"), _erro("40P01"))
    assert servico._inserir_com_savepoint(sessao, agenda, {}) == "novo"
    assert agenda.chamadas == servico.TENTATIVAS_DEADLOCK == 3
    assert sessao.registro == [
        "savepoint",
        "rollback",
        "savepoint",
        "rollback",
        "savepoint",
        "commit",
    ]


def test_40p01_em_todas_as_tentativas_sobe_o_erro():
    sessao = _Sessao()
    agenda = _Agenda(*[_erro("40P01") for _ in range(servico.TENTATIVAS_DEADLOCK)])
    with pytest.raises(OperationalError):
        servico._inserir_com_savepoint(sessao, agenda, {})
    assert agenda.chamadas == servico.TENTATIVAS_DEADLOCK
    assert sessao.registro.count("rollback") == servico.TENTATIVAS_DEADLOCK


def test_23p01_desfaz_o_savepoint_e_devolve_none_para_reler():
    sessao, agenda = _Sessao(), _Agenda(_erro("23P01"))
    assert servico._inserir_com_savepoint(sessao, agenda, {}) is None
    assert agenda.chamadas == 1
    assert sessao.registro == ["savepoint", "rollback"]


def test_23p01_depois_de_40p01_tambem_devolve_none():
    sessao, agenda = _Sessao(), _Agenda(_erro("40P01"), _erro("23P01"))
    assert servico._inserir_com_savepoint(sessao, agenda, {}) is None
    assert agenda.chamadas == 2


@pytest.mark.parametrize("pgcode", ["23505", "55P03", None])
def test_outro_erro_do_banco_desfaz_e_sobe(pgcode):
    sessao, agenda = _Sessao(), _Agenda(_erro(pgcode))
    with pytest.raises(OperationalError):
        servico._inserir_com_savepoint(sessao, agenda, {})
    assert agenda.chamadas == 1
    assert sessao.registro == ["savepoint", "rollback"]
