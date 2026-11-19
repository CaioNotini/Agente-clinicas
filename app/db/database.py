from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL

# Limite para abrir uma conexao. Sem ele, um banco inacessivel prende a chamada
# pelo tempo padrao do sistema operacional.
CONNECT_TIMEOUT_SEGUNDOS = 5

# Engine da aplicação, conectado com a conta sujeita ao RLS
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"connect_timeout": CONNECT_TIMEOUT_SEGUNDOS},
)

# Fábrica de sessões usada pelo restante da aplicação
SessionLocal = sessionmaker(autoflush=False, bind=engine)
