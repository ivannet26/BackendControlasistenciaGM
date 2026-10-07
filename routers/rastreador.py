import secrets
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func, case

from auditoria_helper import registrar_auditoria
import schemas
from database import get_db
from models import Usuario
from equipo_models import Etiqueta, MiembroEquipo
from proyecto_models import Proyecto
from rastreador_models import Tarea, EnlaceRastreador, TiempoRegistro
from security import get_usuario_actual, requiere_admin

router = APIRouter(
    prefix="/rastreador",
    tags=["Rastreador"]
)

TZ_PERU = ZoneInfo("America/Lima")

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
# FUNCIONES AUXILIARES PARA EAGER LOADING (OPTIMIZACIÓN)
# ============================================================

def _opciones_tarea():
    """Devuelve las opciones de eager loading para el modelo Tarea."""
    return [
        joinedload(Tarea.proyecto),
        selectinload(Tarea.etiquetas),
        selectinload(Tarea.miembros).joinedload(MiembroEquipo.usuario)
    ]

def _opciones_tiempo():
    """Devuelve las opciones de eager loading para el modelo TiempoRegistro."""
    return [
        joinedload(TiempoRegistro.proyecto),
        joinedload(TiempoRegistro.tarea)
    ]

# ============================================================
# OBTENER TAREA
# ============================================================

def obtener_tarea_o_404(db: Session, tarea_id: int, usuario_id: int):
    tarea = (
        db.query(Tarea)
        .options(*_opciones_tarea())
        .filter(Tarea.id == tarea_id, Tarea.usuario_id == usuario_id)
        .first()
    )
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
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
        raise HTTPException(status_code=400, detail="Estado inválido")

    if datos.prioridad not in PRIORIDADES:
        raise HTTPException(status_code=400, detail="Prioridad inválida")

    proyecto = (
        db.query(Proyecto)
        .filter(Proyecto.id == datos.proyecto_id)
        .first()
    )
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    if proyecto.archivado:
        raise HTTPException(status_code=400, detail="No se puede asignar un proyecto archivado")

    datos_dict = datos.model_dump(exclude={"etiqueta_ids"})
    tarea = Tarea(usuario_id=usuario.id, **datos_dict)

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
    db.flush()

    # 🔥 AUDITORÍA
    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="CREAR",
        entidad="TAREA",
        entidad_id=tarea.id,
        entidad_nombre=tarea.titulo,
        proyecto_id=proyecto.id,
        proyecto_nombre=proyecto.nombre,
        detalle=f"Creó la tarea '{tarea.titulo}' en el proyecto '{proyecto.nombre}'",
        datos_nuevos={
            "titulo": tarea.titulo,
            "estado": tarea.estado,
            "prioridad": tarea.prioridad,
            "proyecto_id": tarea.proyecto_id,
        },
    )

    db.commit()
    # OPTIMIZACIÓN: Recargar con eager loading para evitar N+1 al serializar
    return obtener_tarea_o_404(db, tarea.id, usuario.id)

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
    # OPTIMIZACIÓN: Eager loading
    query = db.query(Tarea).options(*_opciones_tarea()).filter(
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
    return obtener_tarea_o_404(
        db,
        tarea_id,
        usuario.id
    )


# ============================================================
# ACTUALIZAR TAREA
# ============================================================
@router.put("/tareas/{tarea_id}", response_model=schemas.TareaOut)
def actualizar_tarea(
    tarea_id: int,
    datos: schemas.TareaUpdate,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):
    tarea = obtener_tarea_o_404(db, tarea_id, usuario.id)

    # 📸 Snapshot ANTES
    snapshot_anterior = {
        "titulo": tarea.titulo,
        "estado": tarea.estado,
        "prioridad": tarea.prioridad,
        "descripcion": tarea.descripcion,
        "proyecto_id": tarea.proyecto_id,
    }

    cambios = datos.model_dump(exclude_unset=True)

    if "estado" in cambios and cambios["estado"] not in ESTADOS:
        raise HTTPException(status_code=400, detail="Estado inválido")

    if "prioridad" in cambios and cambios["prioridad"] not in PRIORIDADES:
        raise HTTPException(status_code=400, detail="Prioridad inválida")

    if "proyecto_id" in cambios and cambios["proyecto_id"] is not None:
        proyecto = (
            db.query(Proyecto)
            .filter(Proyecto.id == cambios["proyecto_id"])
            .first()
        )
        if not proyecto:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")
        if proyecto.archivado:
            raise HTTPException(status_code=400, detail="No se puede asignar un proyecto archivado")

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
        setattr(tarea, campo, valor)

    db.flush()

    proyecto_ref = None
    if tarea.proyecto_id:
        proyecto_ref = (
            db.query(Proyecto)
            .filter(Proyecto.id == tarea.proyecto_id)
            .first()
        )

    # 🔥 AUDITORÍA
    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="EDITAR",
        entidad="TAREA",
        entidad_id=tarea.id,
        entidad_nombre=tarea.titulo,
        proyecto_id=tarea.proyecto_id,
        proyecto_nombre=proyecto_ref.nombre if proyecto_ref else None,
        detalle=f"Editó la tarea '{tarea.titulo}'",
        datos_anteriores=snapshot_anterior,
        datos_nuevos={
            "titulo": tarea.titulo,
            "estado": tarea.estado,
            "prioridad": tarea.prioridad,
            "proyecto_id": tarea.proyecto_id,
        },
    )

    db.commit()
    # OPTIMIZACIÓN: Recargar con eager loading
    return obtener_tarea_o_404(db, tarea.id, usuario.id)


# ============================================================
# ELIMINAR TAREA
# ============================================================

@router.delete("/tareas/{tarea_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):
    tarea = obtener_tarea_o_404(db, tarea_id, usuario.id)

    snapshot_anterior = {
        "titulo": tarea.titulo,
        "estado": tarea.estado,
        "prioridad": tarea.prioridad,
        "proyecto_id": tarea.proyecto_id,
    }

    proyecto_ref = None
    if tarea.proyecto_id:
        proyecto_ref = (
            db.query(Proyecto)
            .filter(Proyecto.id == tarea.proyecto_id)
            .first()
        )

    # 🔥 AUDITORÍA
    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="ELIMINAR",
        entidad="TAREA",
        entidad_id=tarea.id,
        entidad_nombre=tarea.titulo,
        proyecto_id=tarea.proyecto_id,
        proyecto_nombre=proyecto_ref.nombre if proyecto_ref else None,
        detalle=f"Eliminó la tarea '{tarea.titulo}'",
        datos_anteriores=snapshot_anterior,
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

    tarea = obtener_tarea_o_404(db, tarea_id, usuario.id)

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
    return tarea # Retornamos tarea directamente ya que las relaciones ya están cargadas


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

    tarea = obtener_tarea_o_404(db, tarea_id, usuario.id)

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
    return tarea

# ============================================================
# MIEMBROS DE TAREAS
# ============================================================

@router.post(
    "/tareas/{tarea_id}/miembros/{miembro_id}",
    response_model=schemas.TareaOut,
    status_code=status.HTTP_200_OK
)
def asignar_miembro_a_tarea(
    tarea_id: int,
    miembro_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    tarea = obtener_tarea_o_404(db, tarea_id, usuario.id)

    miembro = db.query(MiembroEquipo).filter(
        MiembroEquipo.id == miembro_id
    ).first()

    if not miembro:
        raise HTTPException(
            status_code=404,
            detail="Miembro no encontrado"
        )

    if miembro in tarea.miembros:
        raise HTTPException(
            status_code=400,
            detail="El miembro ya está asignado a esta tarea"
        )

    tarea.miembros.append(miembro)
    db.commit()
    return tarea


@router.delete(
    "/tareas/{tarea_id}/miembros/{miembro_id}",
    response_model=schemas.TareaOut,
    status_code=status.HTTP_200_OK
)
def desasignar_miembro_de_tarea(
    tarea_id: int,
    miembro_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_actual)
):

    tarea = obtener_tarea_o_404(db, tarea_id, usuario.id)

    miembro = db.query(MiembroEquipo).filter(
        MiembroEquipo.id == miembro_id
    ).first()

    if not miembro:
        raise HTTPException(
            status_code=404,
            detail="Miembro no encontrado"
        )

    if miembro not in tarea.miembros:
        raise HTTPException(
            status_code=400,
            detail="El miembro no está asignado a esta tarea"
        )

    tarea.miembros.remove(miembro)
    db.commit()
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
    # OPTIMIZACIÓN: Agregación en SQL en lugar de traer todo a Python
    hoy = datetime.now(TZ_PERU).date()
    
    resultado = db.query(
        func.count(Tarea.id).label('total'),
        func.sum(case((Tarea.estado == "COMPLETADA", 1), else_=0)).label('completadas'),
        func.sum(case((Tarea.estado == "EN_PROGRESO", 1), else_=0)).label('en_progreso'),
        func.sum(case((Tarea.estado == "PENDIENTE", 1), else_=0)).label('pendientes'),
        func.sum(
            case(
                (Tarea.estado != "COMPLETADA", 
                 case((Tarea.fecha_limite < hoy, 1), else_=0)), 
                else_=0
            )
        ).label('vencidas')
    ).filter(Tarea.usuario_id == usuario.id).first()

    total = resultado.total or 0
    completadas = resultado.completadas or 0
    en_progreso = resultado.en_progreso or 0
    pendientes = resultado.pendientes or 0
    vencidas = resultado.vencidas or 0

    avance = round((completadas / total) * 100, 2) if total else 0

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

    enlace = db.query(EnlaceRastreador).filter(
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

    enlace = db.query(EnlaceRastreador).filter(
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

    enlace = db.query(EnlaceRastreador).filter(
        EnlaceRastreador.token == token,
        EnlaceRastreador.activo == True
    ).first()

    if not enlace:
        raise HTTPException(
            status_code=404,
            detail="Enlace no válido o desactivado"
        )

    usuario = db.query(Usuario).filter(
        Usuario.id == enlace.usuario_id
    ).first()

    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Usuario no encontrado"
        )

    # OPTIMIZACIÓN: Eager loading
    tareas = db.query(Tarea).options(*_opciones_tarea()).filter(
        Tarea.usuario_id == enlace.usuario_id
    ).order_by(
        Tarea.fecha_limite.is_(None),
        Tarea.fecha_limite.asc(),
        Tarea.id.desc()
    ).all()

    # OPTIMIZACIÓN: Agregación en SQL
    hoy = datetime.now(TZ_PERU).date()
    resultado = db.query(
        func.count(Tarea.id).label('total'),
        func.sum(case((Tarea.estado == "COMPLETADA", 1), else_=0)).label('completadas'),
        func.sum(case((Tarea.estado == "EN_PROGRESO", 1), else_=0)).label('en_progreso'),
        func.sum(case((Tarea.estado == "PENDIENTE", 1), else_=0)).label('pendientes'),
        func.sum(
            case(
                (Tarea.estado != "COMPLETADA", 
                 case((Tarea.fecha_limite < hoy, 1), else_=0)), 
                else_=0
            )
        ).label('vencidas')
    ).filter(Tarea.usuario_id == enlace.usuario_id).first()

    total = resultado.total or 0
    completadas = resultado.completadas or 0
    en_progreso = resultado.en_progreso or 0
    pendientes = resultado.pendientes or 0
    vencidas = resultado.vencidas or 0

    avance = round((completadas / total) * 100, 2) if total else 0

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
    ahora = datetime.now(TZ_PERU)

    # Cerrar registros huérfanos (>4 horas)
    limite_huerfano = ahora - timedelta(hours=4)

    huerfanos = (
        db.query(TiempoRegistro)
        .filter(
            TiempoRegistro.usuario_id == usuario.id,
            TiempoRegistro.fin.is_(None),
            TiempoRegistro.inicio < limite_huerfano
        )
        .all()
    )

    for h in huerfanos:
        inicio_h = h.inicio
        if inicio_h.tzinfo is None:
            inicio_h = inicio_h.replace(tzinfo=TZ_PERU)

        h.fin = inicio_h + timedelta(seconds=1)
        h.duracion_segundos = 1

    if huerfanos:
        db.commit()

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
            detail="Ya tienes un temporizador activo en curso. Deténlo antes de iniciar otro."
        )

    proyecto = (
        db.query(Proyecto)
        .filter(Proyecto.id == datos.proyecto_id)
        .first()
    )
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    if proyecto.archivado:
        raise HTTPException(status_code=400, detail="No se puede cronometrar sobre un proyecto archivado")

    if datos.tarea_id is not None:
        tarea = (
            db.query(Tarea)
            .filter(Tarea.id == datos.tarea_id)
            .first()
        )
        if not tarea:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        if tarea.proyecto_id != datos.proyecto_id:
            raise HTTPException(status_code=400, detail="La tarea seleccionada no pertenece al proyecto indicado")

    nuevo_registro = TiempoRegistro(
        usuario_id=usuario.id,
        proyecto_id=datos.proyecto_id,
        tarea_id=datos.tarea_id,
        descripcion=datos.descripcion,
        inicio=ahora,
        fin=None,
        duracion_segundos=0
    )

    db.add(nuevo_registro)
    db.commit()
    
    # OPTIMIZACIÓN: Retornar con eager loading
    return db.query(TiempoRegistro).options(*_opciones_tiempo()).filter(TiempoRegistro.id == nuevo_registro.id).first()


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
        ahora = datetime.now(TZ_PERU)
        return {
            "id": 0,
            "proyecto_id": 0,
            "nombre_proyecto": None,
            "color_proyecto": None,
            "tarea_id": None,
            "titulo_tarea": None,
            "descripcion": "Sin temporizador activo",
            "inicio": ahora,
            "fin": ahora,
            "duracion_segundos": 0
        }

    ahora = datetime.now(TZ_PERU)

    if registro.inicio.tzinfo is None:
        inicio_aware = registro.inicio.replace(tzinfo=TZ_PERU)
    else:
        inicio_aware = registro.inicio

    segundos_transcurridos = int((ahora - inicio_aware).total_seconds())

    if segundos_transcurridos < 0:
        segundos_transcurridos = 0

    registro.fin = ahora
    registro.duracion_segundos = segundos_transcurridos

    db.commit()
    
    # OPTIMIZACIÓN: Retornar con eager loading
    return db.query(TiempoRegistro).options(*_opciones_tiempo()).filter(TiempoRegistro.id == registro.id).first()


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
    # OPTIMIZACIÓN: Eager loading
    return (
        db.query(TiempoRegistro)
        .options(*_opciones_tiempo())
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

    if fecha_desde and fecha_hasta:
        if fecha_desde > fecha_hasta:
            raise HTTPException(
                status_code=400,
                detail="fecha_desde no puede ser mayor que fecha_hasta"
            )

    # OPTIMIZACIÓN: Eager loading
    query = db.query(TiempoRegistro).options(*_opciones_tiempo()).filter(
        TiempoRegistro.usuario_id == usuario.id,
        TiempoRegistro.fin.is_not(None)
    )

    if proyecto_id is not None:
        query = query.filter(
            TiempoRegistro.proyecto_id == proyecto_id
        )

    if fecha_desde is not None:
        query = query.filter(
            TiempoRegistro.inicio >= datetime.combine(
                fecha_desde,
                datetime.min.time(),
                tzinfo=TZ_PERU
            )
        )

    if fecha_hasta is not None:
        query = query.filter(
            TiempoRegistro.inicio <= datetime.combine(
                fecha_hasta,
                datetime.max.time(),
                tzinfo=TZ_PERU
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

    registro = db.query(TiempoRegistro).filter(
        TiempoRegistro.id == registro_id,
        TiempoRegistro.usuario_id == usuario.id
    ).first()

    if not registro:
        raise HTTPException(
            status_code=404,
            detail="Registro de tiempo no encontrado"
        )

    if registro.fin is None:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar un temporizador que está activo"
        )

    db.delete(registro)
    db.commit()

    return None


# ============================================================
# ELIMINAR REGISTRO DE TIEMPO (ADMIN)
# Solo administradores pueden borrar registros de cualquier usuario
# ============================================================

@router.delete(
    "/admin/tiempo/{registro_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_registro_tiempo_admin(
    registro_id: int,
    db: Session = Depends(get_db),
    _=Depends(requiere_admin)
):
    registro = db.query(TiempoRegistro).filter(
        TiempoRegistro.id == registro_id
    ).first()

    if not registro:
        raise HTTPException(
            status_code=404,
            detail="Registro de tiempo no encontrado"
        )

    if registro.fin is None:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar un temporizador que está activo"
        )

    db.delete(registro)
    db.commit()

    return None
# ============================================================
# EDITAR REGISTRO DE TIEMPO (SOLO ADMIN)
# ============================================================

@router.put(
    "/admin/tiempo/{registro_id}",
    response_model=schemas.TiempoRegistroOut
)
def editar_registro_tiempo_admin(
    registro_id: int,
    datos: schemas.TiempoEditarAdmin,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    registro = db.query(TiempoRegistro).filter(
        TiempoRegistro.id == registro_id
    ).first()

    if not registro:
        raise HTTPException(
            status_code=404,
            detail="Registro de tiempo no encontrado"
        )

    # 📸 Snapshot ANTES de la edición
    snapshot_anterior = {
        "inicio": registro.inicio.isoformat() if registro.inicio else None,
        "fin": registro.fin.isoformat() if registro.fin else None,
        "descripcion": registro.descripcion,
        "duracion_segundos": registro.duracion_segundos,
    }

    # Aplicar cambios
    if datos.inicio is not None:
        registro.inicio = datos.inicio

    if datos.fin is not None:
        registro.fin = datos.fin

    if datos.descripcion is not None:
        registro.descripcion = datos.descripcion

    # Recalcular duración
    if registro.inicio and registro.fin:
        inicio_aware = (
            registro.inicio if registro.inicio.tzinfo
            else registro.inicio.replace(tzinfo=TZ_PERU)
        )
        fin_aware = (
            registro.fin if registro.fin.tzinfo
            else registro.fin.replace(tzinfo=TZ_PERU)
        )

        if fin_aware <= inicio_aware:
            raise HTTPException(
                status_code=400,
                detail="La hora de fin debe ser mayor que la de inicio"
            )

        duracion = int((fin_aware - inicio_aware).total_seconds())

        # 🛡️ Validación: máximo 12 horas por registro
        if duracion > 12 * 3600:
            raise HTTPException(
                status_code=400,
                detail="Un registro no puede superar las 12 horas"
            )

        registro.duracion_segundos = duracion

    # 🔥 AUDITORÍA
    usuario_afectado = db.query(Usuario).filter(
        Usuario.id == registro.usuario_id
    ).first()

    registrar_auditoria(
        db=db,
        usuario=admin,
        accion="EDITAR_TIEMPO",
        entidad="TIEMPO_REGISTRO",
        entidad_id=registro.id,
        entidad_nombre=registro.descripcion or "(sin descripción)",
        detalle=(
            f"Admin {admin.nombre} {admin.apellido} editó el tiempo de "
            f"{usuario_afectado.nombre} {usuario_afectado.apellido}. "
            f"Motivo: {datos.motivo}"
        ),
        datos_anteriores=snapshot_anterior,
        datos_nuevos={
            "inicio": registro.inicio.isoformat() if registro.inicio else None,
            "fin": registro.fin.isoformat() if registro.fin else None,
            "descripcion": registro.descripcion,
            "duracion_segundos": registro.duracion_segundos,
            "motivo": datos.motivo,
        },
    )

    db.commit()

    # Recargar con eager loading
    return db.query(TiempoRegistro).options(
        joinedload(TiempoRegistro.proyecto),
        joinedload(TiempoRegistro.tarea)
    ).filter(TiempoRegistro.id == registro.id).first()