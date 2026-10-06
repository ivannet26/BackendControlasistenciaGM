# auditoria_schemas.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AuditoriaOut(BaseModel):
    id: int
    origen: Optional[str] = None
    usuario_id: Optional[int] = None
    usuario_nombre: Optional[str] = None
    usuario_email: Optional[str] = None
    accion: str
    entidad: str
    entidad_id: Optional[int] = None
    entidad_nombre: Optional[str] = None
    proyecto_id: Optional[int] = None
    proyecto_nombre: Optional[str] = None
    detalle: Optional[str] = None
    datos_anteriores: Optional[str] = None
    datos_nuevos: Optional[str] = None
    fecha: datetime

    class Config:
        from_attributes = True


class AuditoriaResumen(BaseModel):
    total: int
    por_accion: dict
    por_entidad: dict
    usuarios_activos: int