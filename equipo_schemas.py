from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class GrupoCrear(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

class GrupoEditar(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None

class GrupoOut(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str]
    creado_en: datetime
    miembros_count: int = 0                   
    miembros: List[str] = []     
    class Config:
        from_attributes = True

class EtiquetaCrear(BaseModel):
    nombre: str
    color: Optional[str] = None

class EtiquetaEditar(BaseModel):
    nombre: Optional[str] = None
    color: Optional[str] = None

class EtiquetaOut(BaseModel):
    id: int
    nombre: str
    color: Optional[str]
    archivado: bool
    creado_en: datetime

    class Config:
        from_attributes = True

class MiembroCrear(BaseModel):
    usuario_id: int
    grupo_id: Optional[int] = None
    tipo_usuario: str = "MIEMBRO"
    estado: str = "ACTIVO"
    clave_temp: Optional[str] = None

class MiembroEditar(BaseModel):
    grupo_id: Optional[int] = None
    tipo_usuario: Optional[str] = None
    estado: Optional[str] = None
    clave_temp: Optional[str] = None

class MiembroOut(BaseModel):
    id: int
    usuario_id: int
    nombre_usuario: str
    email_usuario: str
    grupo_id: Optional[int]
    nombre_grupo: Optional[str]
    tipo_usuario: str
    estado: str
    tiene_clave_temp: bool
    clave_temp_mascara: Optional[str]
    etiquetas: List[EtiquetaOut]
    creado_en: datetime
    actualizado_en: Optional[datetime]
    class Config:
        from_attributes = True

class GrupoConMiembrosOut(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str]
    miembros: List[str]
    class Config:
        from_attributes = True
