"""A regra dos prazos dos testes de concorrencia (tests/concurrency/prazos.py).

Sem banco. Confere que o limite padrao bate com o pytest.ini e que nenhum teste da
pasta usa prazo escrito a mao, fora de prazos.py.
"""
import re
from pathlib import Path

from tests.concurrency import prazos

PASTA = Path(__file__).resolve().parent
ISENTOS = {"prazos.py", "test_prazos.py"}

# Prazo escrito a mao num argumento (timeout=5, prazo=8.0) e join por thread, que
# soma os prazos. Os testes usam as constantes e juntar de prazos.py.
PROIBIDOS = {
    "prazo numerico em argumento": re.compile(r"\b(timeout|prazo)=\d"),
    "join por thread em vez de juntar": re.compile(r"\.join\("),
}


def test_limite_padrao_igual_ao_do_pytest_ini(pytestconfig):
    assert float(pytestconfig.getini("timeout")) == prazos.LIMITE_PYTEST_PADRAO


def test_espera_de_sinal_cabe_no_limite_padrao():
    assert prazos.ESPERA_SINAL + prazos.MARGEM < prazos.LIMITE_PYTEST_PADRAO


def test_limite_do_teste_cobre_prazo_e_margem():
    assert prazos.limite_pytest(1.0) == prazos.LIMITE_PYTEST_PADRAO
    prazo_longo = prazos.LIMITE_PYTEST_PADRAO + 5.5
    assert prazos.limite_pytest(prazo_longo) >= prazo_longo + prazos.MARGEM


def test_nenhum_prazo_escrito_a_mao_nos_testes_de_concorrencia():
    achados = []
    for arquivo in sorted(PASTA.glob("*.py")):
        if arquivo.name in ISENTOS:
            continue
        for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            for motivo, padrao in PROIBIDOS.items():
                if padrao.search(linha):
                    achados.append(f"{arquivo.name}:{numero} {motivo}: {linha.strip()}")

    assert not achados, "\n".join(achados)
