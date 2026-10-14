from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class BloqueHorario(BaseModel):
    dia_semana: int = Field(ge=1, le=7)
    hora_inicio: int = Field(ge=6, le=22)


class HorarioGuardar(BaseModel):
    bloques: List[BloqueHorario]


class HorarioOut(BaseModel):
    bloques: List[BloqueHorario]
    imagen_url: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
