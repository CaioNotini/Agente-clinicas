from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL

# Engine da aplicação, conectado com a conta sujeita ao RLS
engine = create_engine(DATABASE_URL, echo=False)

# Fábrica de sessões usada pelo restante da aplicação
SessionLocal = sessionmaker(autoflush=False, bind=engine)
