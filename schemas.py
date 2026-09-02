from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


# ── Rol ──────────────────────────────────────────────────────────────────────

class RolBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

class RolOut(RolBase):
    id: int

    class Config:
        from_attributes = True  # Lee objetos SQLAlchemy como dicts


# ── Usuario ───────────────────────────────────────────────────────────────────

class UsuarioRegistro(BaseModel):
    """Lo que el cliente manda al registrarse."""
    nombre:   str
    apellido: str
    email:    EmailStr
    password: str          # Texto plano, lo hasheamos en el router
    rol_id:   Optional[int] = 3  # Por defecto: alumno


class UsuarioOut(BaseModel):
    """Lo que devolvemos al cliente (NUNCA el password_hash)."""
    id:        int
    nombre:    str
    apellido:  str
    email:     str
    activo:    bool
    creado_en: Optional[datetime] = None
    rol:       Optional[RolOut] = None

    class Config:
        from_attributes = True


# ── Login / Token ─────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Credenciales para hacer login."""
    email:    EmailStr
    password: str


class Token(BaseModel):
    """Respuesta del endpoint /login."""
    access_token: str
    token_type:   str = "bearer"


class TokenData(BaseModel):
    """Datos que guardamos dentro del JWT."""
    email:    Optional[str] = None
    rol:      Optional[str] = None
    usuario_id: Optional[int] = None
