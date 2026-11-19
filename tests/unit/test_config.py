"""Montagem das URLs do banco com senhas de caracteres especiais. Senhas ficticias."""
import pytest
from sqlalchemy.engine import make_url

from app.config import _monta_url

SENHAS = [
    "com espaco",
    "mais+sinal",
    "abc@def:gh/ij",
    "p%40ss#1?x",
    "aspas'e\"duplas",
    "dolar$x",
    "acento-ção",
    "chave{}[]!&*",
]


@pytest.mark.parametrize("senha", SENHAS)
def test_senha_volta_igual_depois_de_montar_a_url(senha):
    lida = make_url(_monta_url("usuario", senha)).password
    # Comparacao sem mostrar valores numa falha
    igual = lida == senha
    assert igual, "a senha lida da URL difere da original"
