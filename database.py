import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

DB_HOST     = os.getenv("DB_HOST")
DB_PORT     = os.getenv("DB_PORT")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME     = os.getenv("DB_NAME")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# El engine es la conexión real a MySQL
engine = create_engine(DATABASE_URL)

# Cada petición HTTP obtiene su propia sesión de BD y la cierra al terminar
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para que los modelos hereden de aquí
Base = declarative_base()


# Dependencia de FastAPI: abre sesión → entrega → cierra (aunque haya error)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
