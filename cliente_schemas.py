from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional, List


# ── CLIENTE ───────────────────────────────────────────────────────────────────

class ClienteCrear(BaseModel):
    nombre: str
    email: Optional[EmailStr] = None
    # Lista de hasta 3 correos en copia
    destinatarios_cc: Optional[List[EmailStr]] = []
    direccion: Optional[str] = None
    nota: Optional[str] = None
    moneda: str = "USD"

    @field_validator("destinatarios_cc")
    @classmethod
    def max_tres_cc(cls, v):
        if v and len(v) > 3:
            raise ValueError("Se permiten máximo 3 destinatarios en CC")
        return v


class ClienteEditar(BaseModel):
    nombre: Optional[str] = None
    email: Optional[EmailStr] = None
    destinatarios_cc: Optional[List[EmailStr]] = None
    direccion: Optional[str] = None
    nota: Optional[str] = None
    moneda: Optional[str] = None

    @field_validator("destinatarios_cc")
    @classmethod
    def max_tres_cc(cls, v):
        if v and len(v) > 3:
            raise ValueError("Se permiten máximo 3 destinatarios en CC")
        return v


class ClienteOut(BaseModel):
    id: int
    nombre: str
    email: Optional[str]
    # Se devuelve como lista, aunque en BD se guarda como string separado por comas
    destinatarios_cc: List[str]
    direccion: Optional[str]
    nota: Optional[str]
    moneda: str
    archivado: bool
    creado_en: datetime
    actualizado_en: Optional[datetime]

    class Config:
        from_attributes = True
