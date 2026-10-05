from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel

class ProyectoAuditoriaOut(BaseModel):
    id: int
    proyecto_id: Optional[int] = None
    proyecto_nombre: Optional[str] = None
    usuario_id: Optional[int] = None
    usuario_nombre: Optional[str] = None
    accion: str
    detalle: Optional[str] = None
    datos_anteriores: Optional[dict[str, Any]] = None
    datos_nuevos: Optional[dict[str, Any]] = None
    fecha: datetime

    class Config:
        from_attributes = True

class ProyectoCrear(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    cliente_id: Optional[int] = None
    estado: str = "ACTIVO"
    color: Optional[str] = None


class ProyectoEditar(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    cliente_id: Optional[int] = None
    estado: Optional[str] = None
    color: Optional[str] = None


class ProyectoOut(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str]
    cliente_id: Optional[int]
    nombre_cliente: Optional[str]
    estado: str
    color: Optional[str]
    archivado: bool
    horas_registradas: float = 0.0
    segundos_registrados: int = 0     
    creado_en: datetime
    actualizado_en: Optional[datetime]

    class Config:
        from_attributes = True