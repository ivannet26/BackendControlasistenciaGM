from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, timetracker

app = FastAPI(title="Sistema de Asistencia / Time Tracker API")

# Permite que la página web de tu amigo (en otro dominio/puerto) pueda
# llamar a esta API desde el navegador. En producción, reemplaza "*" por
# el dominio real de la página web para mayor seguridad.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(timetracker.router)


@app.get("/")
def read_root():
    return {"message": "Bienvenido a la API de Asistencia / Time Tracker"}