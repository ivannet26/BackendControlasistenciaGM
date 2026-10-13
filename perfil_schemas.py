from datetime import date
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class PerfilOut(BaseModel):
    usuario_id: int
    nombre: str
    apellido: str
    email: EmailStr
    rol: str
    telefono: Optional[str] = None
    dni: Optional[str] = None
    direccion: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    puesto: Optional[str] = None
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class PerfilEditar(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    apellido: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = Field(None, max_length=150)
    telefono: Optional[str] = Field(None, max_length=30)
    dni: Optional[str] = Field(None, max_length=20)
    direccion: Optional[str] = Field(None, max_length=255)
    fecha_nacimiento: Optional[date] = None
    puesto: Optional[str] = Field(None, max_length=100)
    avatar_url: Optional[str] = Field(None, max_length=500)


class CambiarPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str = Field(..., min_length=6)
