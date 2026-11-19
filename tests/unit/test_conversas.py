"""conversa_travada quando a linha da conversa nao aparece (item B12 do plano).

Depois do buscar-ou-criar, o SELECT ... FOR UPDATE deveria sempre achar a linha.
Se nao achar, a funcao levanta um erro explicito e desfaz a transacao, em vez de
falhar com AttributeError em None. Sessao falsa, sem banco.
"""
import pytest

from app.core.conversas import ConversaNaoEncontrada, conversa_travada


class _ResultadoVazio:
    def first(self):
        return None


class _SessaoSemConversa:
    def __init__(self):
        self.desfeita = False
        self.fechada = False

    def execute(self, *args, **kwargs):
        return _ResultadoVazio()

    def commit(self):
        raise AssertionError("nao deveria confirmar a transacao")

    def rollback(self):
        self.desfeita = True

    def close(self):
        self.fechada = True


def test_conversa_ausente_levanta_erro_explicito_e_desfaz():
    sessao = _SessaoSemConversa()

    with pytest.raises(ConversaNaoEncontrada):
        with conversa_travada(
            "00000000-0000-0000-0000-000000000001",
            "(00) 00000-0000",
            session_factory=lambda: sessao,
        ):
            pass

    assert sessao.desfeita
    assert sessao.fechada
