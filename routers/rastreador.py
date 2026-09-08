import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import schemas
from database import get_db
from models import Usuario
from equipo_models import Etiqueta
from rastreador_models import Tarea, EnlaceRastreador
from security import get_usuario_actual


router = APIRouter(
    prefix="/rastreador",
    tags=["Rastreador"]
)


ESTADOS = {
    "PENDIENTE",
    "EN_PROGRESO",
    "COMPLETADA"
}

PRIORIDADES = {
    "BAJA",
    "MEDIA",
    "ALTA"
}


# ============================================================
# OBTENER TAREA
# ============================================================

def obtener_tarea_o_404(
    db: Session,
    tarea_id: int,
    usuario_id: int
):

    tarea = db.query(Tarea).filter(
        Tarea.id == tarea_id,
        Tarea.usuario_id == usuario_id
    ).first()

    if not tarea:
        raise HTTPException(
            status_code=404,
            detail="Tarea no encontrada"
        )

    return tarea


# ============================================================
# CREAR TAREA
# ============================================================

@router.post(
    "/tareas",
    response_model=schemas.TareaOut,
    status_code=status.HTTP_201_CREATED
)
def crear_tarea(
    datos: schemas.TareaCreate,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    if datos.estado not in ESTADOS:
        raise HTTPException(
            status_code=400,
            detail="Estado inválido"
        )

    if datos.prioridad not in PRIORIDADES:
        raise HTTPException(
            status_code=400,
            detail="Prioridad inválida"
        )

    tarea = Tarea(
        usuario_id=usuario.id,
        **datos.model_dump()
    )

    db.add(tarea)
    db.commit()
    db.refresh(tarea)

    return tarea


# ============================================================
# LISTAR TAREAS
# ============================================================

@router.get(
    "/tareas",
    response_model=list[schemas.TareaOut]
)
def listar_tareas(
    estado: str | None = None,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    query = db.query(Tarea).filter(
        Tarea.usuario_id == usuario.id
    )

    if estado:

        estado = estado.upper()

        if estado not in ESTADOS:
            raise HTTPException(
                status_code=400,
                detail="Estado inválido"
            )

        query = query.filter(
            Tarea.estado == estado
        )

    return query.order_by(
        Tarea.fecha_limite.asc().nullslast(),
        Tarea.id.desc()
    ).all()


# ============================================================
# ACTUALIZAR TAREA
# ============================================================

@router.put(
    "/tareas/{tarea_id}",
    response_model=schemas.TareaOut
)
def actualizar_tarea(
    tarea_id: int,
    datos: schemas.TareaUpdate,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    tarea = obtener_tarea_o_404(
        db,
        tarea_id,
        usuario.id
    )

    cambios = datos.model_dump(
        exclude_unset=True
    )

    if "estado" in cambios:

        if cambios["estado"] not in ESTADOS:
            raise HTTPException(
                status_code=400,
                detail="Estado inválido"
            )

    if "prioridad" in cambios:

        if cambios["prioridad"] not in PRIORIDADES:
            raise HTTPException(
                status_code=400,
                detail="Prioridad inválida"
            )

    for campo, valor in cambios.items():

        setattr(
            tarea,
            campo,
            valor
        )

    db.commit()
    db.refresh(tarea)

    return tarea


# ============================================================
# ELIMINAR TAREA
# ============================================================

@router.delete(
    "/tareas/{tarea_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    tarea = obtener_tarea_o_404(
        db,
        tarea_id,
        usuario.id
    )

    db.delete(tarea)
    db.commit()

    return None


# ============================================================
# ETIQUETAS DE TAREAS
# ============================================================

@router.post(
    "/tareas/{tarea_id}/etiquetas/{etiqueta_id}",
    response_model=schemas.TareaOut,
    status_code=status.HTTP_200_OK
)
def asignar_etiqueta_a_tarea(
    tarea_id: int,
    etiqueta_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    tarea = obtener_tarea_o_404(
        db,
        tarea_id,
        usuario.id
    )

    etiqueta = db.query(Etiqueta).filter(
        Etiqueta.id == etiqueta_id
    ).first()

    if not etiqueta:
        raise HTTPException(
            status_code=404,
            detail="Etiqueta no encontrada"
        )

    if etiqueta.archivado:
        raise HTTPException(
            status_code=400,
            detail="No se puede asignar una etiqueta archivada"
        )

    if etiqueta in tarea.etiquetas:
        raise HTTPException(
            status_code=400,
            detail="La tarea ya tiene asignada esta etiqueta"
        )

    tarea.etiquetas.append(etiqueta)

    db.commit()
    db.refresh(tarea)

    return tarea


@router.delete(
    "/tareas/{tarea_id}/etiquetas/{etiqueta_id}",
    response_model=schemas.TareaOut,
    status_code=status.HTTP_200_OK
)
def desasignar_etiqueta_de_tarea(
    tarea_id: int,
    etiqueta_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    tarea = obtener_tarea_o_404(
        db,
        tarea_id,
        usuario.id
    )

    etiqueta = db.query(Etiqueta).filter(
        Etiqueta.id == etiqueta_id
    ).first()

    if not etiqueta:
        raise HTTPException(
            status_code=404,
            detail="Etiqueta no encontrada"
        )

    if etiqueta not in tarea.etiquetas:
        raise HTTPException(
            status_code=400,
            detail="La tarea no tiene asignada esta etiqueta"
        )

    tarea.etiquetas.remove(etiqueta)

    db.commit()
    db.refresh(tarea)

    return tarea


# ============================================================
# RESUMEN DEL RASTREADOR
# ============================================================

@router.get(
    "/resumen",
    response_model=schemas.RastreadorResumen
)
def resumen(
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    tareas = db.query(Tarea).filter(
        Tarea.usuario_id == usuario.id
    ).all()

    total = len(tareas)

    completadas = sum(
        t.estado == "COMPLETADA"
        for t in tareas
    )

    en_progreso = sum(
        t.estado == "EN_PROGRESO"
        for t in tareas
    )

    pendientes = sum(
        t.estado == "PENDIENTE"
        for t in tareas
    )

    vencidas = sum(
        t.estado != "COMPLETADA"
        and t.fecha_limite is not None
        and t.fecha_limite < date.today()
        for t in tareas
    )

    avance = (
        round((completadas / total) * 100, 2)
        if total
        else 0
    )

    return {
        "total": total,
        "completadas": completadas,
        "en_progreso": en_progreso,
        "pendientes": pendientes,
        "vencidas": vencidas,
        "avance_porcentaje": avance
    }


# ============================================================
# CREAR ENLACE PÚBLICO
# ============================================================

@router.post(
    "/enlace",
    response_model=schemas.EnlaceOut,
    status_code=status.HTTP_201_CREATED
)
def crear_enlace(
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    enlace = db.query(
        EnlaceRastreador
    ).filter(
        EnlaceRastreador.usuario_id == usuario.id,
        EnlaceRastreador.activo == True
    ).first()

    if not enlace:

        enlace = EnlaceRastreador(
            usuario_id=usuario.id,
            token=secrets.token_urlsafe(32),
            activo=True
        )

        db.add(enlace)
        db.commit()
        db.refresh(enlace)

    return {
        "token": enlace.token,
        "url": f"/rastreador/publico/{enlace.token}"
    }


# ============================================================
# DESACTIVAR ENLACE
# ============================================================

@router.delete(
    "/enlace",
    status_code=status.HTTP_204_NO_CONTENT
)
def desactivar_enlace(
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    enlace = db.query(
        EnlaceRastreador
    ).filter(
        EnlaceRastreador.usuario_id == usuario.id,
        EnlaceRastreador.activo == True
    ).first()

    if enlace:

        enlace.activo = False

        db.commit()

    return None


# ============================================================
# CONSULTAR RASTREADOR MEDIANTE ENLACE
# ============================================================

@router.get(
    "/publico/{token}",
    response_model=schemas.RastreadorPublico
)
def consultar_rastreador_publico(
    token: str,
    db: Session = Depends(get_db)
):

    enlace = db.query(
        EnlaceRastreador
    ).filter(
        EnlaceRastreador.token == token,
        EnlaceRastreador.activo == True
    ).first()

    if not enlace:

        raise HTTPException(
            status_code=404,
            detail="Enlace no válido o desactivado"
        )

    usuario = db.query(
        Usuario
    ).filter(
        Usuario.id == enlace.usuario_id
    ).first()

    if not usuario:

        raise HTTPException(
            status_code=404,
            detail="Usuario no encontrado"
        )

    tareas = db.query(
        Tarea
    ).filter(
        Tarea.usuario_id == enlace.usuario_id
    ).order_by(
        Tarea.fecha_limite.asc().nullslast()
    ).all()

    total = len(tareas)

    completadas = sum(
        t.estado == "COMPLETADA"
        for t in tareas
    )

    pendientes = sum(
        t.estado == "PENDIENTE"
        for t in tareas
    )

    en_progreso = sum(
        t.estado == "EN_PROGRESO"
        for t in tareas
    )

    vencidas = sum(
        t.estado != "COMPLETADA"
        and t.fecha_limite is not None
        and t.fecha_limite < date.today()
        for t in tareas
    )

    avance = (
        round((completadas / total) * 100, 2)
        if total
        else 0
    )

    return {
        "nombre": f"{usuario.nombre} {usuario.apellido}",
        "tareas": tareas,
        "total": total,
        "completadas": completadas,
        "pendientes": pendientes,
        "en_progreso": en_progreso,
        "vencidas": vencidas,
        "avance_porcentaje": avance
    }