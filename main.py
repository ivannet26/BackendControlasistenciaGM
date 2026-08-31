import os
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine

# Cargar variables del .env
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Crear conexión a MySQL
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as connection:
        print("¡Conexión exitosa a la base de datos de Aiven Cloud!")
        df = pd.read_sql("SHOW TABLES;", connection)
        print("\nTablas encontradas:")
        print(df)
except Exception as e:
    print("Error al conectar:", e)