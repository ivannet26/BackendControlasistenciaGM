import secrets
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import schemas
from database import get_db
from models import Usuario
from equipo_models import Etiqueta
from proyecto_models import Proyecto
from rastreador_models import Tarea, EnlaceRastreador, TiempoRegistro
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

    # Validar que el proyecto exista y no esté archivado
    proyecto = (
        db.query(Proyecto)
        .filter(Proyecto.id == datos.proyecto_id)
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
            detail="No se puede asignar un proyecto archivado"
        )

    # Separar campos de la tarea de la lista de etiquetas
    datos_dict = datos.model_dump(exclude={"etiqueta_ids"})
    tarea = Tarea(
        usuario_id=usuario.id,
        **datos_dict
    )

    # Asociar etiquetas si las mandaron en el JSON
    if datos.etiqueta_ids:
        etiquetas = (
            db.query(Etiqueta)
            .filter(
                Etiqueta.id.in_(datos.etiqueta_ids),
                Etiqueta.archivado == False
            )
            .all()
        )
        tarea.etiquetas = etiquetas

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
    proyecto_id: int | None = None,
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

    # Filtro opcional por proyecto
    if proyecto_id is not None:
        query = query.filter(
            Tarea.proyecto_id == proyecto_id
        )

    return query.order_by(
        Tarea.fecha_limite.is_(None),
        Tarea.fecha_limite.asc(),
        Tarea.id.desc()
    ).all()


# ============================================================
# OBTENER UNA TAREA
# ============================================================
@router.get(
    "/tareas/{tarea_id}",
    response_model=schemas.TareaOut
)
def obtener_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):
    """Devuelve el detalle de una tarea puntual con sus etiquetas y proyecto."""
    return obtener_tarea_o_404(
        db,
        tarea_id,
        usuario.id
    )


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

    # Validar proyecto solo si el usuario lo envió para cambiarlo
    if "proyecto_id" in cambios and cambios["proyecto_id"] is not None:
        proyecto = (
            db.query(Proyecto)
            .filter(Proyecto.id == cambios["proyecto_id"])
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
                detail="No se puede asignar un proyecto archivado"
            )

    # Actualizar etiquetas si mandaron la lista
    if "etiqueta_ids" in cambios:
        ids_etiquetas = cambios.pop("etiqueta_ids")
        if ids_etiquetas is not None:
            etiquetas = (
                db.query(Etiqueta)
                .filter(
                    Etiqueta.id.in_(ids_etiquetas),
                    Etiqueta.archivado == False
                )
                .all()
            )
            tarea.etiquetas = etiquetas

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
        Tarea.fecha_limite.is_(None),
        Tarea.fecha_limite.asc(),
        Tarea.id.desc()
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



# ============================================================
# TEMPORIZADOR: INICIAR SESIÓN (START)
# ============================================================

@router.post(
    "/tiempo/iniciar",
    response_model=schemas.TiempoRegistroOut,
    status_code=status.HTTP_201_CREATED
)
def iniciar_temporizador(
    datos: schemas.TiempoIniciar,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):
    # Validar que no tenga ya un temporizador corriendo
    activo = (
        db.query(TiempoRegistro)
        .filter(
            TiempoRegistro.usuario_id == usuario.id,
            TiempoRegistro.fin.is_(None)
        )
        .first()
    )
    if activo:
        raise HTTPException(
            status_code=400,
            detail="Ya tienes un temporizador activo en curso. Detenlo antes de iniciar otro."
        )

    # Validar que el proyecto exista y esté activo
    proyecto = (
        db.query(Proyecto)
        .filter(Proyecto.id == datos.proyecto_id)
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
            detail="No se puede cronometrar sobre un proyecto archivado"
        )

    # Si mandaron tarea, validar existencia y pertenencia al proyecto
    if datos.tarea_id is not None:
        tarea = (
            db.query(Tarea)
            .filter(Tarea.id == datos.tarea_id)
            .first()
        )
        if not tarea:
            raise HTTPException(
                status_code=404,
                detail="Tarea no encontrada"
            )
        if tarea.proyecto_id != datos.proyecto_id:
            raise HTTPException(
                status_code=400,
                detail="La tarea seleccionada no pertenece al proyecto indicado"
            )

    nuevo_registro = TiempoRegistro(
        usuario_id=usuario.id,
        proyecto_id=datos.proyecto_id,
        tarea_id=datos.tarea_id,
        descripcion=datos.descripcion,
        inicio=datetime.now(),
        fin=None,
        duracion_segundos=0
    )

    db.add(nuevo_registro)
    db.commit()
    db.refresh(nuevo_registro)
    return nuevo_registro


# ============================================================
# TEMPORIZADOR: DETENER SESIÓN (STOP)
# ============================================================

@router.post(
    "/tiempo/detener",
    response_model=schemas.TiempoRegistroOut
)
def detener_temporizador(
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):
    registro = (
        db.query(TiempoRegistro)
        .filter(
            TiempoRegistro.usuario_id == usuario.id,
            TiempoRegistro.fin.is_(None)
        )
        .first()
    )
    if not registro:
        raise HTTPException(
            status_code=404,
            detail="No hay ningún temporizador activo para detener"
        )

    ahora = datetime.now()
    segundos_transcurridos = int((ahora - registro.inicio).total_seconds())

    registro.fin = ahora
    registro.duracion_segundos = max(segundos_transcurridos, 0)

    db.commit()
    db.refresh(registro)
    return registro


# ============================================================
# TEMPORIZADOR: CONSULTAR SESIÓN ACTIVA
# ============================================================

@router.get(
    "/tiempo/activo",
    response_model=schemas.TiempoRegistroOut | None
)
def obtener_temporizador_activo(
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):
    """Devuelve el registro en curso para que el frontend reanude el cronómetro."""
    return (
        db.query(TiempoRegistro)
        .filter(
            TiempoRegistro.usuario_id == usuario.id,
            TiempoRegistro.fin.is_(None)
        )
        .first()
    )
# ============================================================
# HISTORIAL DE TIEMPOS
# ============================================================

@router.get(
    "/tiempo/historial",
    response_model=list[schemas.TiempoRegistroOut]
)
def historial_tiempos(
    proyecto_id: int | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):
    """
    Lista las sesiones de tiempo cerradas
    del usuario actual.
    """

    if fecha_desde and fecha_hasta:
        if fecha_desde > fecha_hasta:
            raise HTTPException(
                status_code=400,
                detail="fecha_desde no puede ser mayor que fecha_hasta"
            )

    query = db.query(TiempoRegistro).filter(
        TiempoRegistro.usuario_id == usuario.id,
        TiempoRegistro.fin.is_not(None)
    )

    # Filtro por proyecto
    if proyecto_id is not None:
        query = query.filter(
            TiempoRegistro.proyecto_id == proyecto_id
        )

    # Filtro desde fecha
    if fecha_desde is not None:
        query = query.filter(
            TiempoRegistro.inicio >= datetime.combine(
                fecha_desde,
                datetime.min.time()
            )
        )

    # Filtro hasta fecha
    if fecha_hasta is not None:
        query = query.filter(
            TiempoRegistro.inicio <= datetime.combine(
                fecha_hasta,
                datetime.max.time()
            )
        )

    return query.order_by(
        TiempoRegistro.inicio.desc()
    ).all()


# ============================================================
# ELIMINAR REGISTRO DE TIEMPO
# ============================================================

@router.delete(
    "/tiempo/{registro_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_registro_tiempo(
    registro_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):
    """
    Elimina una entrada de tiempo del usuario actual.
    """

    registro = db.query(TiempoRegistro).filter(
        TiempoRegistro.id == registro_id,
        TiempoRegistro.usuario_id == usuario.id
    ).first()

    if not registro:
        raise HTTPException(
            status_code=404,
            detail="Registro de tiempo no encontrado"
        )

    # No permitir eliminar un temporizador activo
    if registro.fin is None:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar un temporizador que está activo"
        )

    db.delete(registro)
    db.commit()

    return None