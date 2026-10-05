from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditoriaProyectoOut(BaseModel):
    id: int
    proyecto_id: Optional[int]
    proyecto_nombre: str
    usuario_id: Optional[int]
    usuario_nombre: Optional[str] = None
    usuario_email: Optional[str] = None
    accion: str
    detalle: Optional[str]
    creado_en: datetime

    class Config:
        from_attributes = True