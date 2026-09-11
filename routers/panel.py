from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario
from proyecto_models import Proyecto
from cliente_models import Cliente
from equipo_models import MiembroEquipo, Etiqueta
from rastreador_models import Tarea

from security import get_usuario_actual


router = APIRouter(
    prefix="/panel",
    tags=["Panel"]
)


# ============================================================
# PANEL PRINCIPAL
# ============================================================

@router.get("/resumen")
def obtener_resumen_panel(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual)
):

    # ========================================================
    # PROYECTOS
    # ========================================================

    total_proyectos = (
        db.query(Proyecto)
        .count()
    )

    proyectos_activos = (
        db.query(Proyecto)
        .filter(
            Proyecto.archivado == False
        )
        .count()
    )

    proyectos_archivados = (
        db.query(Proyecto)
        .filter(
            Proyecto.archivado == True
        )
        .count()
    )


    # ========================================================
    # CLIENTES
    # ========================================================

    total_clientes = (
        db.query(Cliente)
        .count()
    )

    clientes_activos = (
        db.query(Cliente)
        .filter(
            Cliente.archivado == False
        )
        .count()
    )

    clientes_archivados = (
        db.query(Cliente)
        .filter(
            Cliente.archivado == True
        )
        .count()
    )


    # ========================================================
    # EQUIPO
    # ========================================================

    total_miembros = (
        db.query(MiembroEquipo)
        .count()
    )

    miembros_activos = (
        db.query(MiembroEquipo)
        .filter(
            MiembroEquipo.estado == "ACTIVO"
        )
        .count()
    )

    miembros_inactivos = (
        db.query(MiembroEquipo)
        .filter(
            MiembroEquipo.estado != "ACTIVO"
        )
        .count()
    )


    # ========================================================
    # ETIQUETAS
    # ========================================================

    total_etiquetas = (
        db.query(Etiqueta)
        .count()
    )

    etiquetas_activas = (
        db.query(Etiqueta)
        .filter(
            Etiqueta.archivado == False
        )
        .count()
    )

    etiquetas_archivadas = (
        db.query(Etiqueta)
        .filter(
            Etiqueta.archivado == True
        )
        .count()
    )


    # ========================================================
    # TAREAS
    # ========================================================

    total_tareas = (
        db.query(Tarea)
        .count()
    )

    tareas_pendientes = (
        db.query(Tarea)
        .filter(
            Tarea.estado == "PENDIENTE"
        )
        .count()
    )

    tareas_en_progreso = (
        db.query(Tarea)
        .filter(
            Tarea.estado == "EN_PROGRESO"
        )
        .count()
    )

    tareas_completadas = (
        db.query(Tarea)
        .filter(
            Tarea.estado == "COMPLETADA"
        )
        .count()
    )


    # ========================================================
    # TAREAS VENCIDAS
    # ========================================================

    hoy = date.today()

    tareas_vencidas = (
        db.query(Tarea)
        .filter(
            Tarea.fecha_limite < hoy,
            Tarea.estado != "COMPLETADA"
        )
        .count()
    )


    # ========================================================
    # ÚLTIMAS TAREAS
    # ========================================================

    ultimas_tareas = (
        db.query(Tarea)
        .order_by(
            Tarea.id.desc()
        )
        .limit(10)
        .all()
    )


    lista_ultimas_tareas = []

    for tarea in ultimas_tareas:

        lista_ultimas_tareas.append({

            "id": tarea.id,

            "titulo": tarea.titulo,

            "descripcion": tarea.descripcion,

            "estado": tarea.estado,

            "prioridad": tarea.prioridad,

            "fecha_limite": tarea.fecha_limite,

            "usuario_id": tarea.usuario_id,

            "creada_en": tarea.creada_en

        })


    # ========================================================
    # PORCENTAJE DE TAREAS COMPLETADAS
    # ========================================================

    if total_tareas > 0:

        porcentaje_completadas = round(
            (
                tareas_completadas
                / total_tareas
            ) * 100,
            2
        )

    else:

        porcentaje_completadas = 0


    # ========================================================
    # RESPUESTA
    # ========================================================

    return {

        "usuario_actual": {

            "id": usuario.id,

            "nombre": usuario.nombre,

            "apellido": usuario.apellido,

            "email": usuario.email,

            "rol": usuario.rol

        },

        "proyectos": {

            "total": total_proyectos,

            "activos": proyectos_activos,

            "archivados": proyectos_archivados

        },

        "clientes": {

            "total": total_clientes,

            "activos": clientes_activos,

            "archivados": clientes_archivados

        },

        "equipo": {

            "total": total_miembros,

            "activos": miembros_activos,

            "inactivos": miembros_inactivos

        },

        "etiquetas": {

            "total": total_etiquetas,

            "activas": etiquetas_activas,

            "archivadas": etiquetas_archivadas

        },

        "tareas": {

            "total": total_tareas,

            "pendientes": tareas_pendientes,

            "en_progreso": tareas_en_progreso,

            "completadas": tareas_completadas,

            "vencidas": tareas_vencidas,

            "porcentaje_completadas":
                porcentaje_completadas

        },

        "ultimas_tareas":
            lista_ultimas_tareas

    }