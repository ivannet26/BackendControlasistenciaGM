from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario
from proyecto_models import Proyecto
from cliente_models import Cliente
from equipo_models import MiembroEquipo, Etiqueta
from rastreador_models import Tarea

from security import get_usuario_actual


router = APIRouter(
    prefix="/informes",
    tags=["Informes"]
)


# ============================================================
# INFORME GENERAL
# ============================================================

@router.get("/resumen")
def informe_resumen(
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


    # ========================================================
    # TAREAS
    # ========================================================

    total_tareas = (
        db.query(Tarea)
        .count()
    )

    pendientes = (
        db.query(Tarea)
        .filter(
            Tarea.estado == "PENDIENTE"
        )
        .count()
    )

    progreso = (
        db.query(Tarea)
        .filter(
            Tarea.estado == "EN_PROGRESO"
        )
        .count()
    )

    completadas = (
        db.query(Tarea)
        .filter(
            Tarea.estado == "COMPLETADA"
        )
        .count()
    )


    return {

        "proyectos": {

            "total": total_proyectos,

            "activos": proyectos_activos,

            "archivados":
                proyectos_archivados

        },

        "clientes": {

            "total": total_clientes,

            "activos": clientes_activos

        },

        "equipo": {

            "total": total_miembros,

            "activos": miembros_activos

        },

        "etiquetas": {

            "total": total_etiquetas,

            "activas": etiquetas_activas

        },

        "tareas": {

            "total": total_tareas,

            "pendientes": pendientes,

            "en_progreso": progreso,

            "completadas": completadas

        }

    }


# ============================================================
# INFORME DE TAREAS
# ============================================================

@router.get("/tareas")
def informe_tareas(

    estado: Optional[str] = Query(
        None,
        description="PENDIENTE, EN_PROGRESO o COMPLETADA"
    ),

    prioridad: Optional[str] = Query(
        None,
        description="BAJA, MEDIA o ALTA"
    ),

    fecha_desde: Optional[date] = Query(None),

    fecha_hasta: Optional[date] = Query(None),

    db: Session = Depends(get_db),

    usuario: Usuario = Depends(
        get_usuario_actual
    )

):

    query = db.query(Tarea)


    # ========================================================
    # FILTRO ESTADO
    # ========================================================

    if estado:

        query = query.filter(
            Tarea.estado
            == estado.upper()
        )


    # ========================================================
    # FILTRO PRIORIDAD
    # ========================================================

    if prioridad:

        query = query.filter(
            Tarea.prioridad
            == prioridad.upper()
        )


    # ========================================================
    # FECHA DESDE
    # ========================================================

    if fecha_desde:

        query = query.filter(
            Tarea.fecha_limite
            >= fecha_desde
        )


    # ========================================================
    # FECHA HASTA
    # ========================================================

    if fecha_hasta:

        query = query.filter(
            Tarea.fecha_limite
            <= fecha_hasta
        )


    tareas = (
        query
        .order_by(
            Tarea.fecha_limite.asc()
        )
        .all()
    )


    # ========================================================
    # CONTADORES
    # ========================================================

    total = len(tareas)

    pendientes = sum(
        1
        for tarea in tareas
        if tarea.estado == "PENDIENTE"
    )

    en_progreso = sum(
        1
        for tarea in tareas
        if tarea.estado == "EN_PROGRESO"
    )

    completadas = sum(
        1
        for tarea in tareas
        if tarea.estado == "COMPLETADA"
    )

    hoy = date.today()

    vencidas = sum(
        1
        for tarea in tareas
        if (
            tarea.fecha_limite
            and tarea.fecha_limite < hoy
            and tarea.estado != "COMPLETADA"
        )
    )


    # ========================================================
    # DETALLE
    # ========================================================

    detalle = []

    for tarea in tareas:

        detalle.append({

            "id": tarea.id,

            "titulo": tarea.titulo,

            "descripcion":
                tarea.descripcion,

            "estado": tarea.estado,

            "prioridad":
                tarea.prioridad,

            "fecha_limite":
                tarea.fecha_limite,

            "usuario_id":
                tarea.usuario_id,

            "creada_en":
                tarea.creada_en

        })


    return {

        "resumen": {

            "total": total,

            "pendientes":
                pendientes,

            "en_progreso":
                en_progreso,

            "completadas":
                completadas,

            "vencidas":
                vencidas

        },

        "tareas": detalle

    }


# ============================================================
# INFORME DE PROYECTOS
# ============================================================

@router.get("/proyectos")
def informe_proyectos(

    estado: Optional[str] = Query(
        None
    ),

    cliente_id: Optional[int] = Query(
        None
    ),

    db: Session = Depends(get_db),

    usuario: Usuario = Depends(
        get_usuario_actual
    )

):

    query = db.query(Proyecto)


    if estado:

        estado_busqueda = estado.upper()

        query = query.filter(
            Proyecto.estado
            == estado_busqueda
        )


    if cliente_id is not None:

        query = query.filter(
            Proyecto.cliente_id
            == cliente_id
        )


    proyectos = (
        query
        .order_by(
            Proyecto.nombre.asc()
        )
        .all()
    )


    resultado = []


    for proyecto in proyectos:

        resultado.append({

            "id":
                proyecto.id,

            "nombre":
                proyecto.nombre,

            "descripcion":
                proyecto.descripcion,

            "cliente_id":
                proyecto.cliente_id,

            "cliente":
                (
                    proyecto.cliente.nombre
                    if proyecto.cliente
                    else None
                ),

            "estado":
                proyecto.estado,

            "color":
                proyecto.color,

            "archivado":
                proyecto.archivado,

            "creado_en":
                proyecto.creado_en

        })


    return {

        "total":
            len(resultado),

        "proyectos":
            resultado

    }


# ============================================================
# INFORME DE CLIENTES
# ============================================================

@router.get("/clientes")
def informe_clientes(

    incluir_archivados: bool = False,

    db: Session = Depends(get_db),

    usuario: Usuario = Depends(
        get_usuario_actual
    )

):

    query = db.query(Cliente)


    if not incluir_archivados:

        query = query.filter(
            Cliente.archivado == False
        )


    clientes = (
        query
        .order_by(
            Cliente.nombre.asc()
        )
        .all()
    )


    resultado = []


    for cliente in clientes:

        cantidad_proyectos = (
            db.query(Proyecto)
            .filter(
                Proyecto.cliente_id
                == cliente.id
            )
            .count()
        )


        resultado.append({

            "id":
                cliente.id,

            "nombre":
                cliente.nombre,

            "email":
                cliente.email,

            "direccion":
                cliente.direccion,

            "moneda":
                cliente.moneda,

            "archivado":
                cliente.archivado,

            "cantidad_proyectos":
                cantidad_proyectos,

            "creado_en":
                cliente.creado_en

        })


    return {

        "total":
            len(resultado),

        "clientes":
            resultado

    }


# ============================================================
# INFORME DE TIEMPO (por rango de fechas)
# ============================================================

@router.get("/tiempo")
def informe_tiempo(

    fecha_desde: Optional[date] = Query(
        None,
        description="Fecha de inicio del rango (YYYY-MM-DD)"
    ),

    fecha_hasta: Optional[date] = Query(
        None,
        description="Fecha de fin del rango (YYYY-MM-DD)"
    ),

    estado: Optional[str] = Query(
        None,
        description="PENDIENTE, EN_PROGRESO o COMPLETADA"
    ),

    prioridad: Optional[str] = Query(
        None,
        description="BAJA, MEDIA o ALTA"
    ),

    usuario_id: Optional[int] = Query(
        None,
        description="Filtrar por miembro del equipo (usuario_id)"
    ),

    db: Session = Depends(get_db),

    usuario: Usuario = Depends(get_usuario_actual)

):
    """
    Informe de tareas agrupadas por rango de fechas.
    Filtra por fecha_limite dentro del rango indicado.
    Si no se indica rango, devuelve todas las tareas.
    """

    query = db.query(Tarea)


    # ========================================================
    # FILTRO RANGO DE FECHAS (sobre fecha_limite)
    # ========================================================

    if fecha_desde:
        query = query.filter(
            Tarea.fecha_limite >= fecha_desde
        )

    if fecha_hasta:
        query = query.filter(
            Tarea.fecha_limite <= fecha_hasta
        )


    # ========================================================
    # FILTRO ESTADO
    # ========================================================

    if estado:
        query = query.filter(
            Tarea.estado == estado.upper()
        )


    # ========================================================
    # FILTRO PRIORIDAD
    # ========================================================

    if prioridad:
        query = query.filter(
            Tarea.prioridad == prioridad.upper()
        )


    # ========================================================
    # FILTRO POR USUARIO / MIEMBRO DEL EQUIPO
    # ========================================================

    if usuario_id is not None:
        query = query.filter(
            Tarea.usuario_id == usuario_id
        )


    tareas = (
        query
        .order_by(Tarea.fecha_limite.asc())
        .all()
    )


    # ========================================================
    # CONTADORES DEL PERÍODO
    # ========================================================

    total = len(tareas)
    hoy = date.today()

    pendientes = sum(
        1 for t in tareas
        if t.estado == "PENDIENTE"
    )

    en_progreso = sum(
        1 for t in tareas
        if t.estado == "EN_PROGRESO"
    )

    completadas = sum(
        1 for t in tareas
        if t.estado == "COMPLETADA"
    )

    vencidas = sum(
        1 for t in tareas
        if (
            t.fecha_limite
            and t.fecha_limite < hoy
            and t.estado != "COMPLETADA"
        )
    )

    avance_porcentaje = (
        round((completadas / total) * 100, 2)
        if total > 0
        else 0.0
    )


    # ========================================================
    # DETALLE DE TAREAS EN EL PERÍODO
    # ========================================================

    detalle = [
        {
            "id":           t.id,
            "titulo":       t.titulo,
            "descripcion":  t.descripcion,
            "estado":       t.estado,
            "prioridad":    t.prioridad,
            "fecha_limite": t.fecha_limite,
            "usuario_id":   t.usuario_id,
            "creada_en":    t.creada_en,
        }
        for t in tareas
    ]


    return {

        "periodo": {
            "desde": fecha_desde,
            "hasta": fecha_hasta,
        },

        "resumen": {
            "total":              total,
            "pendientes":         pendientes,
            "en_progreso":        en_progreso,
            "completadas":        completadas,
            "vencidas":           vencidas,
            "avance_porcentaje":  avance_porcentaje,
        },

        "tareas": detalle

    }
