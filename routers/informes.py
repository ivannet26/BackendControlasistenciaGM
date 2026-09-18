import io
import csv
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario
from proyecto_models import Proyecto
from cliente_models import Cliente
from equipo_models import MiembroEquipo, Etiqueta
from rastreador_models import Tarea, TiempoRegistro

from security import get_usuario_actual
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
import os
from zoneinfo import ZoneInfo


router = APIRouter(
    prefix="/informes",
    tags=["Informes"]
)


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def formatear_segundos(segundos: int) -> str:
    """Convierte segundos a formato HH:MM:SS"""
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segs = segundos % 60
    return f"{horas:02d}:{minutos:02d}:{segs:02d}"


def ruta_imagen(nombre: str) -> str:
    """
    Devuelve la ruta absoluta de una imagen dentro de la carpeta assets,
    en formato file:/// compatible con WeasyPrint en Windows.
    """
    ruta = os.path.join(os.path.dirname(__file__), "assets", nombre)
    return "file:///" + ruta.replace("\\", "/")


# ============================================================
# INFORME GENERAL
# ============================================================

@router.get("/resumen")
def informe_resumen(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual)
):

    total_proyectos = db.query(Proyecto).count()
    proyectos_activos = db.query(Proyecto).filter(Proyecto.archivado == False).count()
    proyectos_archivados = db.query(Proyecto).filter(Proyecto.archivado == True).count()

    total_clientes = db.query(Cliente).count()
    clientes_activos = db.query(Cliente).filter(Cliente.archivado == False).count()

    total_miembros = db.query(MiembroEquipo).count()
    miembros_activos = db.query(MiembroEquipo).filter(MiembroEquipo.estado == "ACTIVO").count()

    total_etiquetas = db.query(Etiqueta).count()
    etiquetas_activas = db.query(Etiqueta).filter(Etiqueta.archivado == False).count()

    total_tareas = db.query(Tarea).count()
    pendientes = db.query(Tarea).filter(Tarea.estado == "PENDIENTE").count()
    progreso = db.query(Tarea).filter(Tarea.estado == "EN_PROGRESO").count()
    completadas = db.query(Tarea).filter(Tarea.estado == "COMPLETADA").count()

    return {
        "proyectos": {
            "total": total_proyectos,
            "activos": proyectos_activos,
            "archivados": proyectos_archivados
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
    estado: Optional[str] = Query(None, description="PENDIENTE, EN_PROGRESO o COMPLETADA"),
    prioridad: Optional[str] = Query(None, description="BAJA, MEDIA o ALTA"),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual)
):

    query = db.query(Tarea)

    if estado:
        query = query.filter(Tarea.estado == estado.upper())

    if prioridad:
        query = query.filter(Tarea.prioridad == prioridad.upper())

    if fecha_desde:
        query = query.filter(Tarea.fecha_limite >= fecha_desde)

    if fecha_hasta:
        query = query.filter(Tarea.fecha_limite <= fecha_hasta)

    tareas = query.order_by(Tarea.fecha_limite.asc()).all()

    total = len(tareas)

    pendientes = sum(1 for tarea in tareas if tarea.estado == "PENDIENTE")
    en_progreso = sum(1 for tarea in tareas if tarea.estado == "EN_PROGRESO")
    completadas = sum(1 for tarea in tareas if tarea.estado == "COMPLETADA")

    hoy = date.today()

    vencidas = sum(
        1 for tarea in tareas
        if (tarea.fecha_limite and tarea.fecha_limite < hoy and tarea.estado != "COMPLETADA")
    )

    detalle = []

    for tarea in tareas:
        detalle.append({
            "id": tarea.id,
            "titulo": tarea.titulo,
            "descripcion": tarea.descripcion,
            "estado": tarea.estado,
            "prioridad": tarea.prioridad,
            "fecha_limite": tarea.fecha_limite,
            "usuario_id": tarea.usuario_id,
            "creada_en": tarea.creada_en
        })

    return {
        "resumen": {
            "total": total,
            "pendientes": pendientes,
            "en_progreso": en_progreso,
            "completadas": completadas,
            "vencidas": vencidas
        },
        "tareas": detalle
    }


# ============================================================
# INFORME DE PROYECTOS
# ============================================================

@router.get("/proyectos")
def informe_proyectos(
    estado: Optional[str] = Query(None),
    cliente_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual)
):

    query = db.query(Proyecto)

    if estado:
        query = query.filter(Proyecto.estado == estado.upper())

    if cliente_id is not None:
        query = query.filter(Proyecto.cliente_id == cliente_id)

    proyectos = query.order_by(Proyecto.nombre.asc()).all()

    resultado = []

    for proyecto in proyectos:
        resultado.append({
            "id": proyecto.id,
            "nombre": proyecto.nombre,
            "descripcion": proyecto.descripcion,
            "cliente_id": proyecto.cliente_id,
            "cliente": (proyecto.cliente.nombre if proyecto.cliente else None),
            "estado": proyecto.estado,
            "color": proyecto.color,
            "archivado": proyecto.archivado,
            "creado_en": proyecto.creado_en
        })

    return {
        "total": len(resultado),
        "proyectos": resultado
    }


# ============================================================
# INFORME DE CLIENTES
# ============================================================

@router.get("/clientes")
def informe_clientes(
    incluir_archivados: bool = False,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual)
):

    query = db.query(Cliente)

    if not incluir_archivados:
        query = query.filter(Cliente.archivado == False)

    clientes = query.order_by(Cliente.nombre.asc()).all()

    resultado = []

    for cliente in clientes:
        cantidad_proyectos = (
            db.query(Proyecto)
            .filter(Proyecto.cliente_id == cliente.id)
            .count()
        )

        resultado.append({
            "id": cliente.id,
            "nombre": cliente.nombre,
            "email": cliente.email,
            "direccion": cliente.direccion,
            "moneda": cliente.moneda,
            "archivado": cliente.archivado,
            "cantidad_proyectos": cantidad_proyectos,
            "creado_en": cliente.creado_en
        })

    return {
        "total": len(resultado),
        "clientes": resultado
    }


# ============================================================
# INFORME DE TIEMPO (por rango de fechas)
# ============================================================

@router.get("/tiempo")
def informe_tiempo(
    fecha_desde: Optional[date] = Query(None, description="Fecha de inicio del rango (YYYY-MM-DD)"),
    fecha_hasta: Optional[date] = Query(None, description="Fecha de fin del rango (YYYY-MM-DD)"),
    estado: Optional[str] = Query(None, description="PENDIENTE, EN_PROGRESO o COMPLETADA"),
    prioridad: Optional[str] = Query(None, description="BAJA, MEDIA o ALTA"),
    usuario_id: Optional[int] = Query(None, description="Filtrar por miembro del equipo (usuario_id)"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual)
):
    """
    Informe de tareas agrupadas por rango de fechas.
    Filtra por fecha_limite dentro del rango indicado.
    Si no se indica rango, devuelve todas las tareas.
    """

    query = db.query(Tarea)

    if fecha_desde:
        query = query.filter(Tarea.fecha_limite >= fecha_desde)

    if fecha_hasta:
        query = query.filter(Tarea.fecha_limite <= fecha_hasta)

    if estado:
        query = query.filter(Tarea.estado == estado.upper())

    if prioridad:
        query = query.filter(Tarea.prioridad == prioridad.upper())

    if usuario_id is not None:
        query = query.filter(Tarea.usuario_id == usuario_id)

    tareas = query.order_by(Tarea.fecha_limite.asc()).all()

    total = len(tareas)
    hoy = date.today()

    pendientes = sum(1 for t in tareas if t.estado == "PENDIENTE")
    en_progreso = sum(1 for t in tareas if t.estado == "EN_PROGRESO")
    completadas = sum(1 for t in tareas if t.estado == "COMPLETADA")

    vencidas = sum(
        1 for t in tareas
        if (t.fecha_limite and t.fecha_limite < hoy and t.estado != "COMPLETADA")
    )

    avance_porcentaje = (
        round((completadas / total) * 100, 2)
        if total > 0
        else 0.0
    )

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


# ============================================================
# EXPORTACION DE INFORME DE TIEMPOS (CSV O EXCEL)
# Filtra siempre por el usuario logueado
# ============================================================

@router.get("/tiempo/exportar")
def exportar_informe_tiempo(
    formato: str = Query("csv", description="Formato de exportacion: 'csv' o 'excel'"),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    proyecto_id: Optional[int] = Query(None),
    cliente_id: Optional[int] = Query(None),
    usuario_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual)
):
    """
    Genera y descarga el archivo con los tiempos filtrados.
    Soporta formato=csv o formato=excel.

    Siempre filtra por el usuario logueado, excepto si se pasa
    explicitamente un usuario_id (util para admins).
    """

    query = (
        db.query(TiempoRegistro, Usuario, Proyecto)
        .join(Usuario, TiempoRegistro.usuario_id == Usuario.id)
        .join(Proyecto, TiempoRegistro.proyecto_id == Proyecto.id)
        .filter(TiempoRegistro.fin.is_not(None))
    )

    # Filtros de fecha
    if fecha_desde:
        query = query.filter(
            TiempoRegistro.inicio >= datetime.combine(fecha_desde, datetime.min.time())
        )

    if fecha_hasta:
        query = query.filter(
            TiempoRegistro.inicio <= datetime.combine(fecha_hasta, datetime.max.time())
        )

    # Filtros opcionales
    if proyecto_id is not None:
        query = query.filter(TiempoRegistro.proyecto_id == proyecto_id)

    if cliente_id is not None:
        query = query.filter(Proyecto.cliente_id == cliente_id)

    # Filtro por usuario
    if usuario_id is not None:
        query = query.filter(TiempoRegistro.usuario_id == usuario_id)
    else:
        query = query.filter(TiempoRegistro.usuario_id == usuario_actual.id)

    filas = query.order_by(TiempoRegistro.inicio.desc()).all()

    # Preparar datos
    datos = []

    for reg, user, proy in filas:

        nombre_cliente = (
            proy.cliente.nombre
            if proy and proy.cliente
            else "Sin cliente"
        )

        titulo_tarea = reg.tarea.titulo if reg.tarea else ""

        inicio_str = reg.inicio.strftime("%Y-%m-%d %H:%M:%S") if reg.inicio else ""
        fin_str = reg.fin.strftime("%Y-%m-%d %H:%M:%S") if reg.fin else ""

        datos.append({
            "Usuario": f"{user.nombre} {user.apellido}",
            "Email": user.email,
            "Proyecto": proy.nombre if proy else "",
            "Cliente": nombre_cliente,
            "Tarea": titulo_tarea,
            "Descripcion": reg.descripcion or "",
            "Inicio": inicio_str,
            "Fin": fin_str,
            "Duracion (HH:MM:SS)": formatear_segundos(reg.duracion_segundos),
            "Duracion (Horas)": round(reg.duracion_segundos / 3600.0, 2)
        })

    columnas = [
        "Usuario", "Email", "Proyecto", "Cliente", "Tarea",
        "Descripcion", "Inicio", "Fin",
        "Duracion (HH:MM:SS)", "Duracion (Horas)"
    ]

    nombre_archivo = f"informe_tiempo_{date.today().strftime('%Y%m%d')}"

    # Excel
    if formato.lower() == "excel":
        import pandas as pd

        df = pd.DataFrame(datos, columns=columnas)

        buffer_salida = io.BytesIO()

        with pd.ExcelWriter(buffer_salida, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Tiempos")

        buffer_salida.seek(0)

        headers = {
            "Content-Disposition": f"attachment; filename={nombre_archivo}.xlsx"
        }

        return StreamingResponse(
            buffer_salida,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )

    # CSV (por defecto)
    buffer_texto = io.StringIO()

    escritor = csv.DictWriter(buffer_texto, fieldnames=columnas)
    escritor.writeheader()

    if datos:
        escritor.writerows(datos)

    contenido_bytes = buffer_texto.getvalue().encode("utf-8-sig")

    headers = {
        "Content-Disposition": f"attachment; filename={nombre_archivo}.csv"
    }

    return StreamingResponse(
        io.BytesIO(contenido_bytes),
        media_type="text/csv",
        headers=headers
    )


# ============================================================
# INFORME DE TIEMPO EN JSON (para graficos y tablas)
# ============================================================

@router.get("/tiempo/datos")
def datos_informe_tiempo(
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    proyecto_id: Optional[int] = Query(None),
    cliente_id: Optional[int] = Query(None),
    usuario_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual)
):
    """
    Devuelve los tiempos del periodo agrupados por dia, proyecto y actividad.
    Solo del usuario actual (para informes personales).
    """
    from datetime import time as time_type, timedelta
    from zoneinfo import ZoneInfo

    TZ_PERU = ZoneInfo("America/Lima")

    if not fecha_desde:
        fecha_desde = date.today() - timedelta(days=date.today().weekday())
    if not fecha_hasta:
        fecha_hasta = fecha_desde + timedelta(days=6)

    inicio_dt = datetime.combine(fecha_desde, time_type.min, tzinfo=TZ_PERU)
    fin_dt = datetime.combine(fecha_hasta, time_type.max, tzinfo=TZ_PERU)

    ahora = datetime.now(TZ_PERU)

    def segundos_de_registro(r):
        if r.fin is not None:
            return r.duracion_segundos or 0
        if not r.inicio:
            return 0
        inicio = r.inicio
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=TZ_PERU)
        segs = int((ahora - inicio).total_seconds())
        return max(segs, 0)

    # Filtro por usuario (siempre el logueado, salvo que se pase usuario_id)
    query = db.query(TiempoRegistro).filter(
        TiempoRegistro.inicio >= inicio_dt,
        TiempoRegistro.inicio <= fin_dt
    )

    if usuario_id is not None:
        query = query.filter(TiempoRegistro.usuario_id == usuario_id)
    else:
        query = query.filter(TiempoRegistro.usuario_id == usuario_actual.id)

    if proyecto_id is not None:
        query = query.filter(TiempoRegistro.proyecto_id == proyecto_id)

    registros = query.all()

    if cliente_id is not None:
        registros = [
            r for r in registros
            if r.proyecto and r.proyecto.cliente_id == cliente_id
        ]

    tiempo_total = sum(segundos_de_registro(r) for r in registros)

    dias_semana = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
    meses = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]

    por_dia_dict = {}
    delta = (fecha_hasta - fecha_desde).days
    for i in range(delta + 1):
        dia = fecha_desde + timedelta(days=i)
        por_dia_dict[dia.strftime("%Y-%m-%d")] = 0

    for r in registros:
        if not r.inicio:
            continue
        dia_peru = r.inicio.date()
        clave = dia_peru.strftime("%Y-%m-%d")
        if clave in por_dia_dict:
            por_dia_dict[clave] += segundos_de_registro(r)

    por_dia = []
    for clave, segundos in sorted(por_dia_dict.items()):
        d = datetime.strptime(clave, "%Y-%m-%d")
        etiqueta = f"{dias_semana[d.weekday()]}, {d.day} {meses[d.month - 1]}"
        por_dia.append({
            "fecha": clave,
            "dia": etiqueta,
            "segundos": segundos
        })

    por_proyecto_dict = {}
    for r in registros:
        if not r.proyecto:
            continue
        pid = r.proyecto.id
        if pid not in por_proyecto_dict:
            por_proyecto_dict[pid] = {
                "nombre": r.proyecto.nombre,
                "color": getattr(r.proyecto, "color", "#b06fd8"),
                "segundos": 0
            }
        por_proyecto_dict[pid]["segundos"] += segundos_de_registro(r)

    por_proyecto = sorted(
        por_proyecto_dict.values(),
        key=lambda x: x["segundos"],
        reverse=True
    )

    actividades_dict = {}
    for r in registros:
        descripcion = r.descripcion or "(sin descripcion)"
        proyecto_nombre = r.proyecto.nombre if r.proyecto else "Sin proyecto"
        clave = f"{descripcion}|{proyecto_nombre}"

        if clave not in actividades_dict:
            actividades_dict[clave] = {
                "nombre": descripcion,
                "proyecto": proyecto_nombre,
                "segundos": 0
            }
        actividades_dict[clave]["segundos"] += segundos_de_registro(r)

    top_actividades = sorted(
        actividades_dict.values(),
        key=lambda x: x["segundos"],
        reverse=True
    )[:50]

    return {
        "fecha_desde": str(fecha_desde),
        "fecha_hasta": str(fecha_hasta),
        "tiempo_total": tiempo_total,
        "por_dia": por_dia,
        "por_proyecto": por_proyecto,
        "top_actividades": top_actividades
    }


# ============================================================
# EXPORTAR INFORME DE TIEMPO EN PDF
# ============================================================

@router.get("/tiempo/exportar/pdf")
def exportar_informe_pdf(
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    proyecto_id: Optional[int] = Query(None),
    cliente_id: Optional[int] = Query(None),
    usuario_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual)
):
    """
    Genera y descarga el informe de tiempo en PDF con formato formal.
    """
    from datetime import time as time_type, timedelta

    TZ_PERU = ZoneInfo("America/Lima")

    # Rango por defecto: semana actual
    if not fecha_desde:
        fecha_desde = date.today() - timedelta(days=date.today().weekday())
    if not fecha_hasta:
        fecha_hasta = fecha_desde + timedelta(days=6)

    inicio_dt = datetime.combine(fecha_desde, time_type.min, tzinfo=TZ_PERU)
    fin_dt = datetime.combine(fecha_hasta, time_type.max, tzinfo=TZ_PERU)

    ahora = datetime.now(TZ_PERU)

    def segundos_de_registro(r):
        if r.fin is not None:
            return r.duracion_segundos or 0
        if not r.inicio:
            return 0
        inicio = r.inicio
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=TZ_PERU)
        return max(int((ahora - inicio).total_seconds()), 0)

    # Query filtrada por usuario
    query = db.query(TiempoRegistro).filter(
        TiempoRegistro.inicio >= inicio_dt,
        TiempoRegistro.inicio <= fin_dt
    )

    if usuario_id is not None:
        query = query.filter(TiempoRegistro.usuario_id == usuario_id)
    else:
        query = query.filter(TiempoRegistro.usuario_id == usuario_actual.id)

    if proyecto_id is not None:
        query = query.filter(TiempoRegistro.proyecto_id == proyecto_id)

    registros = query.all()

    if cliente_id is not None:
        registros = [r for r in registros if r.proyecto and r.proyecto.cliente_id == cliente_id]

    # Calculos
    tiempo_total = sum(segundos_de_registro(r) for r in registros)

    por_proyecto_dict = {}
    for r in registros:
        if not r.proyecto:
            continue
        pid = r.proyecto.id
        if pid not in por_proyecto_dict:
            por_proyecto_dict[pid] = {
                "nombre": r.proyecto.nombre,
                "segundos": 0
            }
        por_proyecto_dict[pid]["segundos"] += segundos_de_registro(r)

    por_proyecto = []
    for p in sorted(por_proyecto_dict.values(), key=lambda x: x["segundos"], reverse=True):
        pct = round((p["segundos"] / tiempo_total) * 100, 2) if tiempo_total else 0
        p["duracion_formateada"] = formatear_segundos(p["segundos"])
        p["porcentaje"] = pct
        por_proyecto.append(p)

    actividades_dict = {}
    for r in registros:
        desc = r.descripcion or "(sin descripcion)"
        proy_nom = r.proyecto.nombre if r.proyecto else "Sin proyecto"
        clave = f"{desc}|{proy_nom}"
        if clave not in actividades_dict:
            actividades_dict[clave] = {
                "nombre": desc,
                "proyecto": proy_nom,
                "segundos": 0
            }
        actividades_dict[clave]["segundos"] += segundos_de_registro(r)

    top_actividades = []
    for a in sorted(actividades_dict.values(), key=lambda x: x["segundos"], reverse=True):
        pct = round((a["segundos"] / tiempo_total) * 100, 2) if tiempo_total else 0
        a["duracion_formateada"] = formatear_segundos(a["segundos"])
        a["porcentaje"] = pct
        top_actividades.append(a)

    # Dias trabajados (dias con > 0 segundos)
    dias_set = set()
    for r in registros:
        if r.inicio and segundos_de_registro(r) > 0:
            dias_set.add(r.inicio.date())
    dias_trabajados = len(dias_set)

    # Datos para la plantilla
    contexto = {
        "usuario_nombre": f"{usuario_actual.nombre} {usuario_actual.apellido}",
        "usuario_email": usuario_actual.email,
        "fecha_desde": fecha_desde.strftime("%d/%m/%Y"),
        "fecha_hasta": fecha_hasta.strftime("%d/%m/%Y"),
        "tiempo_total_formateado": formatear_segundos(tiempo_total),
        "total_actividades": len(top_actividades),
        "total_proyectos": len(por_proyecto),
        "dias_trabajados": dias_trabajados,
        "por_proyecto": por_proyecto,
        "top_actividades": top_actividades,
        "fecha_generacion": ahora.strftime("%d/%m/%Y %H:%M:%S"),
        # Rutas de imagenes
        "logo_path": ruta_imagen("logo-mg.png"),
        "iso_path": ruta_imagen("iso.jpg"),
        "footer_path": ruta_imagen("footer.png"),
    }

    # Renderizar plantilla
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template("informe_tiempo.html")
    html_render = template.render(**contexto)

    # Convertir a PDF
    pdf_bytes = HTML(string=html_render).write_pdf()

    nombre_archivo = f"informe_tiempo_{fecha_desde}_{fecha_hasta}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
    )