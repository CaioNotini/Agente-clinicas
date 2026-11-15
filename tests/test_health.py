"""
tests/test_health.py
Testes essenciais para health check
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.db import database
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def banco_fora(monkeypatch):
    """Troca o engine da aplicação por um que aponta para uma porta sem banco."""
    # Credenciais fictícias: a conexão é recusada antes de qualquer autenticação
    engine_sem_banco = create_engine(
        "postgresql://ficticio:ficticio@127.0.0.1:1/ficticio",
        connect_args={"connect_timeout": 2},
    )
    monkeypatch.setattr(database, "engine", engine_sem_banco)


class TestHealth:
    def test_banco_no_ar_retorna_200_e_healthy(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "database": "healthy"}

    def test_banco_fora_retorna_503_e_unhealthy(self, client, banco_fora):
        """Controle: com o retorno fixo antigo, este teste falha (viria 200)."""
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "unhealthy", "database": "unhealthy"}

    def test_volta_a_healthy_depois_da_falha(self, client):
        """A falha simulada no teste anterior não deixa o engine real trocado."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["database"] == "healthy"
