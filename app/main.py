from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import database

app = FastAPI(
    title="Agente Clínicas",
    version="0.1.0",
)


def banco_responde() -> bool:
    """Diz se o banco responde a uma consulta simples com a conta da aplicação."""
    try:
        # SELECT 1 não toca em tabela de clínica, então não depende de app.tenant_id
        with database.engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


@app.get("/health")
def health():
    if banco_responde():
        return {"status": "healthy", "database": "healthy"}
    return JSONResponse(
        status_code=503,
        content={"status": "unhealthy", "database": "unhealthy"},
    )
