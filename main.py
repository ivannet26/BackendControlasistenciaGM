import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import usuarios as usuarios_router 
from database import Base, engine
from routers import auth as auth_router
from routers import equipo as equipo_router
from routers import rastreador as rastreador_router
from routers import cliente as cliente_router
from routers import etiqueta as etiqueta_router
from routers import proyecto as proyecto_router
from routers import panel as panel_router
from routers import informes as informes_router
from routers import auditoria as auditoria_router
import auditoria_models  # noqa: F401
import rastreador_models  # noqa: F401
import equipo_models  # noqa: F401
import cliente_models  # noqa: F401
import proyecto_models  # noqa: F401
import proyecto_auditoria_models  # noqa: F401





load_dotenv()

# Crea todas las tablas en la BD si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Control de Asistencia GM",
    description="API REST para el sistema de control de asistencia",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Desarrollo local
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        # Producción (Render)
        "https://frontendcontrolasistenciagm.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router)
app.include_router(rastreador_router.router)
app.include_router(usuarios_router.router)
app.include_router(equipo_router.router)
app.include_router(cliente_router.router)
app.include_router(etiqueta_router.router)
app.include_router(proyecto_router.router)
app.include_router(panel_router.router)
app.include_router(informes_router.router)
app.include_router(auditoria_router.router)



# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
def root():
    return {"mensaje": "API Control de Asistencia GM activa", "docs": "/docs"}
