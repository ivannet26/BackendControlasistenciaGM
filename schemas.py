from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from typing import Optional, List


# Para registro
class UsuarioRegistro(BaseModel):
    nombre: str
    apellido: str
    email: EmailStr
    password: str

# Para login
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# Para respuesta
class UsuarioOut(BaseModel):
    id: int
    nombre: str
    apellido: str
    email: str
    rol: str
    activo: bool
    creado_en: datetime
    actualizado_en: Optional[datetime]
    
    class Config:
        from_attributes = True

# Para token
class Token(BaseModel):
    access_token: str
    token_type: str
    usuario: Optional[dict] = None

class EtiquetaSimple(BaseModel):
    id: int
    nombre: str
    color: Optional[str]
    class Config:
        from_attributes = True
    

# ============================================================
# RASTREADOR DE TAREAS
# ============================================================

class TareaCreate(BaseModel):

    titulo: str

    proyecto_id: int
    
    descripcion: Optional[str] = None

    estado: str = "PENDIENTE"

    prioridad: str = "MEDIA"

    fecha_limite: Optional[date] = None

    horas: Optional[float] = 0.0

    etiqueta_ids: Optional[List[int]] = []


class TareaUpdate(BaseModel):

    titulo: Optional[str] = None

    descripcion: Optional[str] = None

    estado: Optional[str] = None

    prioridad: Optional[str] = None

    fecha_limite: Optional[date] = None

    horas: Optional[float] = None

    proyecto_id: Optional[int] = None 

    etiqueta_ids: Optional[List[int]] = None


class TareaOut(BaseModel):

    id: int

    titulo: str

    descripcion: Optional[str]

    estado: str

    prioridad: str

    fecha_limite: Optional[date]

    horas: float = 0.0

    proyecto_id: Optional[int] = None  

    nombre_proyecto: Optional[str] = None

    color_proyecto: Optional[str] = None

    etiquetas: List[EtiquetaSimple] = []

    class Config:
        
        from_attributes = True


class RastreadorResumen(BaseModel):

    total: int

    completadas: int

    en_progreso: int

    pendientes: int

    vencidas: int

    avance_porcentaje: float


class EnlaceOut(BaseModel):

    token: str

    url: str


class RastreadorPublico(RastreadorResumen):

    nombre: str

    tareas: list[TareaOut]


# ============================================================
# TEMPORIZADOR / TIME TRACKER
# ============================================================

class TiempoIniciar(BaseModel):

    proyecto_id: int

    tarea_id: Optional[int] = None

    descripcion: Optional[str] = None


class TiempoRegistroOut(BaseModel):

    id: int

    proyecto_id: int

    nombre_proyecto: Optional[str] = None

    color_proyecto: Optional[str] = None

    tarea_id: Optional[int] = None

    titulo_tarea: Optional[str] = None

    descripcion: Optional[str] = None

    inicio: datetime

    fin: Optional[datetime] = None

    duracion_segundos: int

    class Config:
        
        from_attributes = True