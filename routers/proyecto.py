from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from sqlalchemy import func

from database import get_db
from models import Usuario
from cliente_models import Cliente
from proyecto_models import Proyecto
from rastreador_models import Tarea
from proyecto_schemas import (
    ProyectoCrear,
    ProyectoEditar,
    ProyectoOut,
)
from security import get_usuario_actual


router = APIRouter(
    prefix="/proyectos",
    tags=["Proyectos"]
)


# ============================================================
# FUNCIÓN AUXILIAR
# ============================================================

def construir_proyecto_out(proyecto: Proyecto, db: Session) -> dict:
    total_horas = (
        db.query(func.coalesce(func.sum(Tarea.horas), 0.0))
        .filter(Tarea.proyecto_id == proyecto.id)
        .scalar()
    )

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
        "horas_registradas": round(float(total_horas), 2),
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
    _: Usuario = Depends(get_usuario_actual),
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

    if proyecto.archivado:
        raise HTTPException(
            status_code=400,
            detail="El proyecto ya está archivado"
        )

    proyecto.archivado = True
    proyecto.estado = "ARCHIVADO"

    db.commit()
    db.refresh(proyecto)

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

    if not proyecto.archivado:
        raise HTTPException(
            status_code=400,
            detail="El proyecto ya está activo"
        )

    proyecto.archivado = False
    proyecto.estado = "ACTIVO"

    db.commit()
    db.refresh(proyecto)

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

    db.delete(proyecto)
    db.commit()

    return None