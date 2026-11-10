from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class RegistroAsistenciaOut(BaseModel):
    id: int
    usuario_id: int
    tipo: str
    hora: datetime
    notas: Optional[str] = None

    class Config:
        from_attributes = True


class RegistroAsistenciaCrear(BaseModel):
    notas: Optional[str] = None


class JustificacionFalta(BaseModel):
    asunto: Optional[str] = None
    mensaje: Optional[str] = None


class ResumenAsistenciaUsuario(BaseModel):
    usuario_id: int
    usuario_nombre: str
    usuario_email: str
    rol: str
    horas_acumuladas: float = 0.0
    avatar_url: Optional[str] = None
    entrada: Optional[datetime] = None
    break_inicio: Optional[datetime] = None
    break_fin: Optional[datetime] = None
    salida: Optional[datetime] = None
    duracion_break_segundos: Optional[int] = None
    estado: str
    tiene_entrada: bool
    justificacion_aceptada: Optional[bool] = False
    comentario_admin: Optional[str] = None
    justificacion_asunto: Optional[str] = None
    justificacion_mensaje: Optional[str] = None
    justificacion_evidencia_url: Optional[str] = None


class AsistenciaHoyResponse(BaseModel):
    usuario_id: int
    fecha: str
    registros: List[RegistroAsistenciaOut]
    estado: str
    justificacion_falta: Optional[JustificacionFalta] = None


class HistorialManualCrear(BaseModel):
    usuario_id: int = Field(gt=0)
    horas_acumuladas: float = Field(ge=0)


class HistorialManualOut(BaseModel):
    usuario_id: int
    horas_acumuladas: float
    actualizado_en: datetime
