import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine
from routers import auth as auth_router

load_dotenv()

# Crea todas las tablas en la BD si no existen
# (en producción se usa Alembic para migraciones, pero esto funciona perfecto para empezar)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Control de Asistencia GM",
    description="API REST para el sistema de control de asistencia",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Permite que el frontend (React, etc.) se comunique con esta API
# En producción cambia ["*"] por la URL real del frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
def root():
    return {"mensaje": "API Control de Asistencia GM activa", "docs": "/docs"}
