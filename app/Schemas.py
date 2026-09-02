from pydantic import BaseModel
from datetime import date, time
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str


class UsuarioActual(BaseModel):
    username: str
    rol: str
    idpracticante: int


class JornadaActual(BaseModel):
    fecha: date
    hora_entrada: Optional[time] = None
    hora_salida: Optional[time] = None


class JornadaHistorialItem(BaseModel):
    fecha: date
    hora_entrada: Optional[time] = None
    hora_salida: Optional[time] = None


class ReporteAdminItem(BaseModel):
    username: str
    hora_entrada: Optional[time] = None
    hora_salida: Optional[time] = None