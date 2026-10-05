from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SesionOut(BaseModel):
    id: int
    usuario_id: int
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    creado_en: datetime
    expira_en: datetime
    ultimo_uso: datetime
    activa: bool
    cerrada_en: Optional[datetime] = None
    motivo_cierre: Optional[str] = None
    es_actual: bool = False

    class Config:
        from_attributes = True