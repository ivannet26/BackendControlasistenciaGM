from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

# Para registro
class UsuarioRegistro(BaseModel):
    nombre: str
    apellido: str
    email: EmailStr
    password: str

# Para login
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# Para respuesta
class UsuarioOut(BaseModel):
    id: int
    nombre: str
    apellido: str
    email: str
    rol: str
    activo: bool
    creado_en: datetime
    actualizado_en: Optional[datetime]
    
    class Config:
        from_attributes = True

# Para token
class Token(BaseModel):
    access_token: str
    token_type: str
    usuario: Optional[dict] = None