from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


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


class ResumenAsistenciaUsuario(BaseModel):
    usuario_id: int
    usuario_nombre: str
    usuario_email: str
    rol: str
    avatar_url: Optional[str] = None
    entrada: Optional[datetime] = None
    break_inicio: Optional[datetime] = None
    break_fin: Optional[datetime] = None
    salida: Optional[datetime] = None
    duracion_break_segundos: Optional[int] = None
    estado: str
    tiene_entrada: bool


class AsistenciaHoyResponse(BaseModel):
    usuario_id: int
    fecha: str
    registros: List[RegistroAsistenciaOut]
    estado: str
