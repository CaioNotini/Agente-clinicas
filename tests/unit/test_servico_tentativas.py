"""Nova tentativa no 40P01 e traducao do 23P01 na insercao (ADR 0004, tarefa 5.3).

O 40P01 esgotado e o 55P03 viram ConcorrenciaNaAgenda (ADR 0011).

Sessao e agenda falsas: o teste controla qual erro do banco cada tentativa recebe,
o que nao da para forcar de forma deterministica num banco real.
"""
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.agenda import servico
from app.agenda.regras import ConcorrenciaNaAgenda
from app.core.erros import ErroPermanente


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


def test_40p01_em_todas_as_tentativas_vira_concorrencia_na_agenda():
    sessao = _Sessao()
    agenda = _Agenda(*[_erro("40P01") for _ in range(servico.TENTATIVAS_DEADLOCK)])
    with pytest.raises(ConcorrenciaNaAgenda) as exc:
        servico._inserir_com_savepoint(sessao, agenda, {})
    assert agenda.chamadas == servico.TENTATIVAS_DEADLOCK
    assert sessao.registro.count("rollback") == servico.TENTATIVAS_DEADLOCK
    # Transitorio: o job tenta de novo. Sem o texto do erro do banco.
    assert not isinstance(exc.value, ErroPermanente)
    assert str(exc.value) == "agenda do profissional ocupada (SQLSTATE 40P01)"
    assert isinstance(exc.value.__cause__, OperationalError)


def test_55p03_na_espera_do_lock_vira_concorrencia_sem_nova_tentativa():
    sessao, agenda = _Sessao(), _Agenda(_erro("55P03"))
    with pytest.raises(ConcorrenciaNaAgenda) as exc:
        servico._inserir_com_savepoint(sessao, agenda, {})
    assert agenda.chamadas == 1
    assert sessao.registro == ["savepoint", "rollback"]
    assert not isinstance(exc.value, ErroPermanente)
    assert "55P03" in str(exc.value)


def test_23p01_desfaz_o_savepoint_e_devolve_none_para_reler():
    sessao, agenda = _Sessao(), _Agenda(_erro("23P01"))
    assert servico._inserir_com_savepoint(sessao, agenda, {}) is None
    assert agenda.chamadas == 1
    assert sessao.registro == ["savepoint", "rollback"]


def test_23p01_depois_de_40p01_tambem_devolve_none():
    sessao, agenda = _Sessao(), _Agenda(_erro("40P01"), _erro("23P01"))
    assert servico._inserir_com_savepoint(sessao, agenda, {}) is None
    assert agenda.chamadas == 2


@pytest.mark.parametrize("pgcode", ["23505", None])
def test_outro_erro_do_banco_desfaz_e_sobe(pgcode):
    sessao, agenda = _Sessao(), _Agenda(_erro(pgcode))
    with pytest.raises(OperationalError):
        servico._inserir_com_savepoint(sessao, agenda, {})
    assert agenda.chamadas == 1
    assert sessao.registro == ["savepoint", "rollback"]
