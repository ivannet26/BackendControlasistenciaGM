from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


TIPO_JUSTIFICACION = Literal["Falta", "Tardanza", "Olvidé marcar", "Otro"]
ESTADO_JUSTIFICACION = Literal[
    "PENDIENTE",
    "ACEPTADA",
    "RECHAZADA",
    "INJUSTIFICADA",
]
ACCION_HISTORIAL = Literal["CREACION", "CAMBIO_ESTADO", "COMENTARIO"]


class JustificacionCreate(BaseModel):
    tipo: TIPO_JUSTIFICACION
    fecha: date
    asunto: str = Field(min_length=1, max_length=255)
    mensaje: str = Field(min_length=1)
    evidencia_url: Optional[str] = Field(default=None, max_length=1000)


class JustificacionUpdate(BaseModel):
    tipo: Optional[TIPO_JUSTIFICACION] = None
    fecha: Optional[date] = None
    asunto: Optional[str] = Field(default=None, min_length=1, max_length=255)
    mensaje: Optional[str] = Field(default=None, min_length=1)
    evidencia_url: Optional[str] = Field(default=None, max_length=1000)


class JustificacionResolver(BaseModel):
    estado: Literal["ACEPTADA", "RECHAZADA"]
    comentario_admin: str = Field(min_length=1)


class HistorialJustificacionOut(BaseModel):
    id: int
    justificacion_id: int
    usuario_id: int
    accion: ACCION_HISTORIAL
    detalle: Optional[str] = None
    fecha_accion: datetime

    class Config:
        from_attributes = True


class JustificacionOut(BaseModel):
    id: int
    usuario_id: int
    intento_numero: int = Field(ge=1, le=2)
    usuario_nombre: Optional[str] = None
    usuario_email: Optional[str] = None
    tipo: TIPO_JUSTIFICACION
    fecha: date
    asunto: str
    mensaje: str
    evidencia_url: Optional[str] = None
    estado: ESTADO_JUSTIFICACION
    comentario_admin: Optional[str] = None
    fecha_resolucion: Optional[datetime] = None
    creado_en: datetime
    historial: List[HistorialJustificacionOut] = []

    class Config:
        from_attributes = True
