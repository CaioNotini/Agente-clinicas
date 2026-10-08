"""
tests/test_health.py
Testes essenciais para health check
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:    
    def test_returns_valid_status_code(self, client):
        response = client.get("/health")
        assert response.status_code in [200, 503]
    
    def test_returns_status(self, client):
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "unhealthy"]
    
    def test_returns_database_status(self, client):
        response = client.get("/health")
        data = response.json()
        assert "database" in data