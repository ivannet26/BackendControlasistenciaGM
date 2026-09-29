
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
    Request
)
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
import json
from database import get_db
from models import Usuario
from cliente_models import Cliente
from proyecto_models import Proyecto
from proyecto_auditoria_models import ProyectoAuditoria
from rastreador_models import TiempoRegistro
from proyecto_schemas import (
    ProyectoCrear,
    ProyectoEditar,
    ProyectoOut,
    ProyectoAuditoriaOut,
)

from security import (
    get_usuario_actual,
    requiere_admin,
    requiere_auditoria
)

router = APIRouter(
    prefix="/proyectos",
    tags=["Proyectos"]
)

# ============================================================
# AUDITORÍA DE PROYECTOS
# ============================================================

def _snapshot_proyecto(proyecto: Proyecto) -> dict:

    return {
        "id": proyecto.id,
        "nombre": proyecto.nombre,
        "descripcion": proyecto.descripcion,
        "cliente_id": proyecto.cliente_id,
        "estado": proyecto.estado,
        "color": proyecto.color,
        "archivado": proyecto.archivado,
    }


def registrar_auditoria(
    db: Session,
    usuario: Usuario,
    proyecto: Proyecto,
    accion: str,
    detalle: str,
    datos_anteriores: Optional[dict] = None,
    datos_nuevos: Optional[dict] = None,
):

    usuario_nombre = (
        f"{usuario.nombre} {usuario.apellido}"
    ).strip()

    registro = ProyectoAuditoria(

        proyecto_id=proyecto.id,

        proyecto_nombre=proyecto.nombre,

        usuario_id=usuario.id,

        usuario_nombre=usuario_nombre,

        accion=accion,

        detalle=detalle,

        datos_anteriores=(
            json.dumps(
                datos_anteriores,
                ensure_ascii=False,
                default=str
            )
            if datos_anteriores is not None
            else None
        ),

        datos_nuevos=(
            json.dumps(
                datos_nuevos,
                ensure_ascii=False,
                default=str
            )
            if datos_nuevos is not None
            else None
        ),
    )

    db.add(registro)


def _parse_auditoria(
    registro: ProyectoAuditoria
) -> dict:

    def cargar(valor):

        if not valor:
            return None

        try:
            return json.loads(valor)

        except (
            TypeError,
            json.JSONDecodeError
        ):
            return None

    return {

        "id": registro.id,

        "proyecto_id": registro.proyecto_id,
        "proyecto_nombre": registro.proyecto_nombre,
        "usuario_id": registro.usuario_id,
        "usuario_nombre": registro.usuario_nombre,
        "accion": registro.accion,
        "detalle": registro.detalle,
        "datos_anteriores": cargar(
            registro.datos_anteriores
        ),

        "datos_nuevos": cargar(
            registro.datos_nuevos
        ),

        "fecha": registro.fecha,
    }

# ============================================================
# FUNCIÓN AUXILIAR
# ============================================================

def construir_proyecto_out(proyecto: Proyecto, db: Session) -> dict:
    """
    Construye la respuesta de un proyecto incluyendo:
    - horas_registradas: float (para compatibilidad)
    - segundos_registrados: int (valor exacto, sin redondeo)
    """

    # Suma exacta de segundos de todas las actividades terminadas
    total_segundos = (
        db.query(func.coalesce(func.sum(TiempoRegistro.duracion_segundos), 0))
        .filter(
            TiempoRegistro.proyecto_id == proyecto.id,
            TiempoRegistro.fin.is_not(None)
        )
        .scalar()
    )

    total_segundos = int(total_segundos)
    horas_registradas = round(total_segundos / 3600, 2)

    return {
        "id": proyecto.id,
        "nombre": proyecto.nombre,
        "descripcion": proyecto.descripcion,
        "cliente_id": proyecto.cliente_id,
        "nombre_cliente": (
            proyecto.cliente.nombre
            if proyecto.cliente
            else None
        ),
        "estado": proyecto.estado,
        "color": proyecto.color,
        "archivado": proyecto.archivado,
        "horas_registradas": horas_registradas,
        "segundos_registrados": total_segundos,
        "creado_en": proyecto.creado_en,
        "actualizado_en": proyecto.actualizado_en,
    }


# ============================================================
# LISTAR PROYECTOS
# ============================================================

@router.get("", response_model=List[ProyectoOut])
def listar_proyectos(
    estado: Optional[str] = Query(
        None,
        description="activo, archivado o todo"
    ),
    nombre: Optional[str] = Query(
        None,
        description="Buscar proyecto por nombre"
    ),
    cliente_id: Optional[int] = Query(
        None,
        description="Filtrar por cliente"
    ),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):

    query = db.query(Proyecto)

    # Por defecto mostramos proyectos activos
    if estado is None or estado.lower() == "activo":
        query = query.filter(
            Proyecto.archivado == False
        )

    elif estado.lower() == "archivado":
        query = query.filter(
            Proyecto.archivado == True
        )

    elif estado.lower() == "todo":
        pass

    else:
        raise HTTPException(
            status_code=400,
            detail="El estado debe ser activo, archivado o todo"
        )

    # Buscar por nombre
    if nombre:
        query = query.filter(
            Proyecto.nombre.ilike(f"%{nombre}%")
        )

    # Filtrar por cliente
    if cliente_id is not None:
        query = query.filter(
            Proyecto.cliente_id == cliente_id
        )

    proyectos = query.order_by(
        Proyecto.nombre.asc()
    ).all()

    return [
        construir_proyecto_out(proyecto, db)
        for proyecto in proyectos
    ]


# ============================================================
# OBTENER UN PROYECTO
# ============================================================

@router.get(
    "/{proyecto_id}",
    response_model=ProyectoOut
)
def obtener_proyecto(
    proyecto_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):

    proyecto = (
        db.query(Proyecto)
        .filter(Proyecto.id == proyecto_id)
        .first()
    )

    if not proyecto:
        raise HTTPException(
            status_code=404,
            detail="Proyecto no encontrado"
        )

    return construir_proyecto_out(proyecto, db)


# ============================================================
# CREAR PROYECTO
# ============================================================

@router.post(
    "",
    response_model=ProyectoOut,
    status_code=status.HTTP_201_CREATED
)
def crear_proyecto(
    datos: ProyectoCrear,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):

    # Verificar cliente
    if datos.cliente_id is not None:

        cliente = (
            db.query(Cliente)
            .filter(Cliente.id == datos.cliente_id)
            .first()
        )

        if not cliente:
            raise HTTPException(
                status_code=404,
                detail="Cliente no encontrado"
            )

        if cliente.archivado:
            raise HTTPException(
                status_code=400,
                detail="No se puede asignar un cliente archivado"
            )

    # Evitar nombres duplicados
    existe = (
        db.query(Proyecto)
        .filter(
            Proyecto.nombre.ilike(datos.nombre)
        )
        .first()
    )

    if existe:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un proyecto con ese nombre"
        )

    proyecto = Proyecto(
        nombre=datos.nombre,
        descripcion=datos.descripcion,
        cliente_id=datos.cliente_id,
        estado=datos.estado.upper(),
        color=datos.color,
        archivado=False,
    )

    db.add(proyecto)
    db.commit()
    db.refresh(proyecto)

    registrar_auditoria(
        db=db,
        usuario=usuario,
        proyecto=proyecto,
        accion="CREAR",
        detalle=f"Proyecto '{proyecto.nombre}' creado",
        datos_anteriores=None,
        datos_nuevos=_snapshot_proyecto(proyecto),
    )
    db.commit()

    return construir_proyecto_out(proyecto, db)


# ============================================================
# EDITAR PROYECTO
# ============================================================

@router.put(
    "/{proyecto_id}",
    response_model=ProyectoOut
)
def editar_proyecto(
    proyecto_id: int,
    datos: ProyectoEditar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):

    proyecto = (
        db.query(Proyecto)
        .filter(Proyecto.id == proyecto_id)
        .first()
    )

    if not proyecto:
        raise HTTPException(
            status_code=404,
            detail="Proyecto no encontrado"
        )

    # Snapshot del estado anterior ANTES de aplicar cambios
    snapshot_anterior = _snapshot_proyecto(proyecto)

    # Cambiar nombre
    if datos.nombre is not None:

        duplicado = (
            db.query(Proyecto)
            .filter(
                Proyecto.nombre.ilike(datos.nombre),
                Proyecto.id != proyecto_id
            )
            .first()
        )

        if duplicado:
            raise HTTPException(
                status_code=400,
                detail="Ya existe otro proyecto con ese nombre"
            )

        proyecto.nombre = datos.nombre

    # Cambiar descripción
    if datos.descripcion is not None:
        proyecto.descripcion = datos.descripcion

    # Cambiar cliente
    if datos.cliente_id is not None:

        cliente = (
            db.query(Cliente)
            .filter(Cliente.id == datos.cliente_id)
            .first()
        )

        if not cliente:
            raise HTTPException(
                status_code=404,
                detail="Cliente no encontrado"
            )

        if cliente.archivado:
            raise HTTPException(
                status_code=400,
                detail="No se puede asignar un cliente archivado"
            )

        proyecto.cliente_id = datos.cliente_id

    # Cambiar estado
    if datos.estado is not None:
        proyecto.estado = datos.estado.upper()

    # Cambiar color
    if datos.color is not None:
        proyecto.color = datos.color

    db.commit()
    db.refresh(proyecto)

    registrar_auditoria(
        db=db,
        usuario=usuario,
        proyecto=proyecto,
        accion="EDITAR",
        detalle=f"Proyecto '{proyecto.nombre}' editado",
        datos_anteriores=snapshot_anterior,
        datos_nuevos=_snapshot_proyecto(proyecto),
    )
    db.commit()

    return construir_proyecto_out(proyecto, db)


# ============================================================
# ARCHIVAR
# ============================================================

@router.patch(
    "/{proyecto_id}/archivar",
    response_model=ProyectoOut
)
def archivar_proyecto(
    proyecto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):

    proyecto = (
        db.query(Proyecto)
        .filter(Proyecto.id == proyecto_id)
        .first()
    )

    if not proyecto:
        raise HTTPException(
            status_code=404,
            detail="Proyecto no encontrado"
        )

    if proyecto.archivado:
        raise HTTPException(
            status_code=400,
            detail="El proyecto ya está archivado"
        )

    snapshot_anterior = _snapshot_proyecto(proyecto)

    proyecto.archivado = True
    proyecto.estado = "ARCHIVADO"

    db.commit()
    db.refresh(proyecto)

    registrar_auditoria(
        db=db,
        usuario=usuario,
        proyecto=proyecto,
        accion="ARCHIVAR",
        detalle=f"Proyecto '{proyecto.nombre}' archivado",
        datos_anteriores=snapshot_anterior,
        datos_nuevos=_snapshot_proyecto(proyecto),
    )
    db.commit()

    return construir_proyecto_out(proyecto, db)


# ============================================================
# DESARCHIVAR
# ============================================================

@router.patch(
    "/{proyecto_id}/desarchivar",
    response_model=ProyectoOut
)
def desarchivar_proyecto(
    proyecto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):

    proyecto = (
        db.query(Proyecto)
        .filter(Proyecto.id == proyecto_id)
        .first()
    )

    if not proyecto:
        raise HTTPException(
            status_code=404,
            detail="Proyecto no encontrado"
        )

    if not proyecto.archivado:
        raise HTTPException(
            status_code=400,
            detail="El proyecto ya está activo"
        )

    snapshot_anterior = _snapshot_proyecto(proyecto)

    proyecto.archivado = False
    proyecto.estado = "ACTIVO"

    db.commit()
    db.refresh(proyecto)

    registrar_auditoria(
        db=db,
        usuario=usuario,
        proyecto=proyecto,
        accion="DESARCHIVAR",
        detalle=f"Proyecto '{proyecto.nombre}' desarchivado",
        datos_anteriores=snapshot_anterior,
        datos_nuevos=_snapshot_proyecto(proyecto),
    )
    db.commit()

    return construir_proyecto_out(proyecto, db)


# ============================================================
# ELIMINAR
# ============================================================

@router.delete(
    "/{proyecto_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_proyecto(
    proyecto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):

    proyecto = (
        db.query(Proyecto)
        .filter(Proyecto.id == proyecto_id)
        .first()
    )

    if not proyecto:
        raise HTTPException(
            status_code=404,
            detail="Proyecto no encontrado"
        )

    # Guardamos el snapshot antes de eliminar
    snapshot_anterior = _snapshot_proyecto(proyecto)
    nombre_proyecto = proyecto.nombre

    # Registrar auditoría ANTES de eliminar el proyecto
    # (el registro apunta a proyecto_id que quedará huérfano,
    #  pero proyecto_nombre queda guardado como texto)
    registrar_auditoria(
        db=db,
        usuario=usuario,
        proyecto=proyecto,
        accion="ELIMINAR",
        detalle=f"Proyecto '{nombre_proyecto}' eliminado permanentemente",
        datos_anteriores=snapshot_anterior,
        datos_nuevos=None,
    )

    db.delete(proyecto)
    db.commit()

    return None


# ============================================================
# HISTORIAL DE AUDITORÍA
# ============================================================

@router.get(
    "/auditoria",
    response_model=List[ProyectoAuditoriaOut],
    summary="Historial de auditoría de proyectos",
    description=(
        "Devuelve el historial de acciones sobre proyectos "
        "(CREAR, EDITAR, ARCHIVAR, DESARCHIVAR, ELIMINAR). "
        "Solo accesible para ADMIN, ADMINISTRADOR, SUPERADMIN y SUPERVISOR."
    ),
)
def listar_auditoria(
    proyecto_id: Optional[int] = Query(
        None,
        description="Filtrar por proyecto específico"
    ),
    usuario_id: Optional[int] = Query(
        None,
        description="Filtrar por usuario que realizó la acción"
    ),
    accion: Optional[str] = Query(
        None,
        description="Filtrar por acción: CREAR, EDITAR, ARCHIVAR, DESARCHIVAR, ELIMINAR"
    ),
    limite: int = Query(
        100,
        ge=1,
        le=500,
        description="Cantidad máxima de registros a devolver"
    ),
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_auditoria),
):
    query = db.query(ProyectoAuditoria)

    if proyecto_id is not None:
        query = query.filter(
            ProyectoAuditoria.proyecto_id == proyecto_id
        )

    if usuario_id is not None:
        query = query.filter(
            ProyectoAuditoria.usuario_id == usuario_id
        )

    if accion is not None:
        query = query.filter(
            ProyectoAuditoria.accion == accion.upper()
        )

    registros = (
        query
        .order_by(desc(ProyectoAuditoria.fecha))
        .limit(limite)
        .all()
    )

    return [_parse_auditoria(r) for r in registros]


@router.get(
    "/{proyecto_id}/auditoria",
    response_model=List[ProyectoAuditoriaOut],
    summary="Historial de auditoría de un proyecto específico",
)
def listar_auditoria_proyecto(
    proyecto_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_auditoria),
):
    registros = (
        db.query(ProyectoAuditoria)
        .filter(ProyectoAuditoria.proyecto_id == proyecto_id)
        .order_by(desc(ProyectoAuditoria.fecha))
        .all()
    )

    return [_parse_auditoria(r) for r in registros]
