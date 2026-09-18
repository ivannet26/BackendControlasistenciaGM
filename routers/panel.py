from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario
from proyecto_models import Proyecto
from cliente_models import Cliente
from equipo_models import MiembroEquipo, Etiqueta
from rastreador_models import Tarea, TiempoRegistro

from security import get_usuario_actual


router = APIRouter(
    prefix="/panel",
    tags=["Panel"]
)


TZ_PERU = ZoneInfo("America/Lima")


# ============================================================
# HELPER: Calcular segundos de un registro (incluso si está abierto)
# ============================================================

def segundos_de_registro(registro, ahora_ref):
    """
    Devuelve los segundos de un TiempoRegistro.
    - Si está cerrado (fin != None), usa su duracion_segundos.
    - Si está abierto (fin == None), calcula en vivo hasta ahora_ref.
    """
    if registro.fin is not None:
        return registro.duracion_segundos or 0

    if not registro.inicio:
        return 0

    if registro.inicio.tzinfo is None:
        inicio_aware = registro.inicio.replace(tzinfo=TZ_PERU)
    else:
        inicio_aware = registro.inicio

    segs = int((ahora_ref - inicio_aware).total_seconds())
    return max(segs, 0)


# ============================================================
# PANEL PRINCIPAL (administrativo)
# ============================================================

@router.get("/resumen")
def obtener_resumen_panel(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual)
):

    total_proyectos = db.query(Proyecto).count()
    proyectos_activos = db.query(Proyecto).filter(Proyecto.archivado == False).count()
    proyectos_archivados = db.query(Proyecto).filter(Proyecto.archivado == True).count()

    total_clientes = db.query(Cliente).count()
    clientes_activos = db.query(Cliente).filter(Cliente.archivado == False).count()
    clientes_archivados = db.query(Cliente).filter(Cliente.archivado == True).count()

    total_miembros = db.query(MiembroEquipo).count()
    miembros_activos = db.query(MiembroEquipo).filter(MiembroEquipo.estado == "ACTIVO").count()
    miembros_inactivos = db.query(MiembroEquipo).filter(MiembroEquipo.estado != "ACTIVO").count()

    total_etiquetas = db.query(Etiqueta).count()
    etiquetas_activas = db.query(Etiqueta).filter(Etiqueta.archivado == False).count()
    etiquetas_archivadas = db.query(Etiqueta).filter(Etiqueta.archivado == True).count()

    total_tareas = db.query(Tarea).count()
    tareas_pendientes = db.query(Tarea).filter(Tarea.estado == "PENDIENTE").count()
    tareas_en_progreso = db.query(Tarea).filter(Tarea.estado == "EN_PROGRESO").count()
    tareas_completadas = db.query(Tarea).filter(Tarea.estado == "COMPLETADA").count()

    hoy = datetime.now(TZ_PERU).date()
    tareas_vencidas = (
        db.query(Tarea)
        .filter(Tarea.fecha_limite < hoy, Tarea.estado != "COMPLETADA")
        .count()
    )

    ultimas_tareas = db.query(Tarea).order_by(Tarea.id.desc()).limit(10).all()

    lista_ultimas_tareas = [
        {
            "id": t.id,
            "titulo": t.titulo,
            "descripcion": t.descripcion,
            "estado": t.estado,
            "prioridad": t.prioridad,
            "fecha_limite": t.fecha_limite,
            "usuario_id": t.usuario_id,
            "creada_en": t.creada_en
        }
        for t in ultimas_tareas
    ]

    if total_tareas > 0:
        porcentaje_completadas = round((tareas_completadas / total_tareas) * 100, 2)
    else:
        porcentaje_completadas = 0

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
            "porcentaje_completadas": porcentaje_completadas
        },
        "ultimas_tareas": lista_ultimas_tareas
    }


# ============================================================
# PANEL DE ANÁLISIS DE TIEMPO (RASTREADOR)
# ============================================================

@router.get("/resumen-tiempo")
def obtener_resumen_tiempo(
    fecha_inicio: date,
    fecha_fin: date,
    usuario_filtro: str = "yo",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual)
):
    inicio_dt = datetime.combine(fecha_inicio, time.min, tzinfo=TZ_PERU)
    fin_dt = datetime.combine(fecha_fin, time.max, tzinfo=TZ_PERU)

    ahora = datetime.now(TZ_PERU)

    # ⚠️ SIN filtro de "fin.is_not(None)" para incluir actividades en curso
    query_base = db.query(TiempoRegistro).filter(
        TiempoRegistro.inicio >= inicio_dt,
        TiempoRegistro.inicio <= fin_dt
    )

    if usuario_filtro == "yo":
        query_base = query_base.filter(TiempoRegistro.usuario_id == usuario.id)

    registros = query_base.all()

    tiempo_total = sum(
        segundos_de_registro(r, ahora)
        for r in registros
    )

    # Tiempo de HOY (solo del usuario actual, incluye en curso)
    inicio_hoy = datetime.combine(ahora.date(), time.min, tzinfo=TZ_PERU)
    fin_hoy = datetime.combine(ahora.date(), time.max, tzinfo=TZ_PERU)

    registros_hoy = (
        db.query(TiempoRegistro)
        .filter(
            TiempoRegistro.usuario_id == usuario.id,
            TiempoRegistro.inicio >= inicio_hoy,
            TiempoRegistro.inicio <= fin_hoy
        )
        .all()
    )

    tiempo_hoy = sum(
        segundos_de_registro(r, ahora)
        for r in registros_hoy
    )

    # Agrupar por día
    dias_semana = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    meses = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]

    por_dia_dict = {}
    delta = (fecha_fin - fecha_inicio).days

    for i in range(delta + 1):
        dia = fecha_inicio + timedelta(days=i)
        clave = dia.strftime("%Y-%m-%d")
        por_dia_dict[clave] = 0

    for r in registros:
        if not r.inicio:
            continue
        dia_peru = r.inicio.date()
        clave = dia_peru.strftime("%Y-%m-%d")
        if clave in por_dia_dict:
            por_dia_dict[clave] += segundos_de_registro(r, ahora)

    por_dia = []
    for clave, segundos in sorted(por_dia_dict.items()):
        d = datetime.strptime(clave, "%Y-%m-%d")
        etiqueta = f"{dias_semana[d.weekday()]}, {d.day} {meses[d.month - 1]}"
        por_dia.append({
            "fecha": clave,
            "dia": etiqueta,
            "segundos": segundos
        })

    # Agrupar por proyecto
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
        por_proyecto_dict[pid]["segundos"] += segundos_de_registro(r, ahora)

    por_proyecto = sorted(
        por_proyecto_dict.values(),
        key=lambda x: x["segundos"],
        reverse=True
    )

    # Proyecto principal + cliente principal
    proyecto_principal = None
    cliente_principal = None

    if por_proyecto:
        proyecto_principal = por_proyecto[0]["nombre"]

        pid_top = None
        for pid, data in por_proyecto_dict.items():
            if data["nombre"] == proyecto_principal:
                pid_top = pid
                break

        if pid_top:
            proyecto_top = (
                db.query(Proyecto)
                .filter(Proyecto.id == pid_top)
                .first()
            )

            if proyecto_top:
                if hasattr(proyecto_top, "cliente") and proyecto_top.cliente:
                    cliente_principal = proyecto_top.cliente.nombre
                elif hasattr(proyecto_top, "cliente_id") and proyecto_top.cliente_id:
                    cliente_obj = (
                        db.query(Cliente)
                        .filter(Cliente.id == proyecto_top.cliente_id)
                        .first()
                    )
                    if cliente_obj:
                        cliente_principal = cliente_obj.nombre
                elif hasattr(proyecto_top, "id_cliente") and proyecto_top.id_cliente:
                    cliente_obj = (
                        db.query(Cliente)
                        .filter(Cliente.id == proyecto_top.id_cliente)
                        .first()
                    )
                    if cliente_obj:
                        cliente_principal = cliente_obj.nombre
                elif hasattr(proyecto_top, "nombre_cliente") and proyecto_top.nombre_cliente:
                    cliente_principal = proyecto_top.nombre_cliente

    # Top actividades
    actividades_dict = {}

    for r in registros:
        descripcion = r.descripcion or "(sin descripción)"
        proyecto_nombre = r.proyecto.nombre if r.proyecto else "Sin proyecto"
        clave = f"{descripcion}|{proyecto_nombre}"

        if clave not in actividades_dict:
            actividades_dict[clave] = {
                "nombre": descripcion,
                "proyecto": proyecto_nombre,
                "segundos": 0
            }
        actividades_dict[clave]["segundos"] += segundos_de_registro(r, ahora)

    top_actividades = sorted(
        actividades_dict.values(),
        key=lambda x: x["segundos"],
        reverse=True
    )[:10]

    # Label de la semana
    hoy = datetime.now(TZ_PERU).date()
    lunes_actual = hoy - timedelta(days=hoy.weekday())
    domingo_actual = lunes_actual + timedelta(days=6)
    lunes_pasado = lunes_actual - timedelta(days=7)
    domingo_pasado = domingo_actual - timedelta(days=7)

    if fecha_inicio == lunes_actual and fecha_fin == domingo_actual:
        label_semana = "Esta semana"
    elif fecha_inicio == lunes_pasado and fecha_fin == domingo_pasado:
        label_semana = "La semana pasada"
    else:
        label_semana = (
            f"{fecha_inicio.day}-{fecha_fin.day} "
            f"{meses[fecha_inicio.month - 1]}"
        )

    return {
        "label_semana": label_semana,
        "fecha_inicio": str(fecha_inicio),
        "fecha_fin": str(fecha_fin),
        "tiempo_total": tiempo_total,
        "tiempo_hoy": tiempo_hoy,
        "proyecto_principal": proyecto_principal,
        "cliente_principal": cliente_principal,
        "por_dia": por_dia,
        "por_proyecto": por_proyecto,
        "top_actividades": top_actividades
    }


# ============================================================
# ACTIVIDAD DEL EQUIPO (RASTREADOR)
# ============================================================

@router.get("/equipo-actividad")
def obtener_actividad_equipo(
    fecha_inicio: date,
    fecha_fin: date,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual)
):

    ROLES_ADMIN = ["ADMINISTRACION", "ADMINISTRADOR"]
    if usuario.rol not in ROLES_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Solo los administradores pueden ver la actividad del equipo"
        )

    ahora = datetime.now(TZ_PERU)
    limite_activo = ahora - timedelta(hours=4)

    usuarios = db.query(Usuario).all()

    inicio_hoy = datetime.combine(ahora.date(), time.min, tzinfo=TZ_PERU)
    fin_hoy = datetime.combine(ahora.date(), time.max, tzinfo=TZ_PERU)

    registros_hoy = (
        db.query(TiempoRegistro)
        .filter(
            TiempoRegistro.inicio >= inicio_hoy,
            TiempoRegistro.inicio <= fin_hoy
        )
        .all()
    )

    totales_por_usuario = {}

    for r in registros_hoy:
        uid = r.usuario_id
        totales_por_usuario[uid] = (
            totales_por_usuario.get(uid, 0)
            + segundos_de_registro(r, ahora)
        )

    miembros = []

    for u in usuarios:

        ultimo_cerrado = (
            db.query(TiempoRegistro)
            .filter(
                TiempoRegistro.usuario_id == u.id,
                TiempoRegistro.fin.is_not(None)
            )
            .order_by(TiempoRegistro.fin.desc())
            .first()
        )

        activo = (
            db.query(TiempoRegistro)
            .filter(
                TiempoRegistro.usuario_id == u.id,
                TiempoRegistro.fin.is_(None),
                TiempoRegistro.inicio >= limite_activo
            )
            .first()
        )

        registro_ref = activo if activo else ultimo_cerrado

        if registro_ref:
            ultima_actividad = registro_ref.descripcion or "(sin descripción)"
            ultimo_proyecto = (
                registro_ref.proyecto.nombre
                if registro_ref.proyecto
                else "Sin proyecto"
            )
        else:
            ultima_actividad = "(sin actividad)"
            ultimo_proyecto = ""

        if activo:
            hora_ref = activo.inicio
        elif ultimo_cerrado:
            hora_ref = ultimo_cerrado.fin
        else:
            hora_ref = None

        if activo:
            estado = "EN_CURSO"
            estado_texto = "En curso"
        elif hora_ref:
            if hora_ref.tzinfo is None:
                hora_aware = hora_ref.replace(tzinfo=TZ_PERU)
            else:
                hora_aware = hora_ref

            delta = ahora - hora_aware
            segundos = delta.total_seconds()

            if segundos < 0:
                segundos = 0

            if segundos < 3600:
                mins = int(segundos / 60)
                estado_texto = f"hace {mins} min"
            elif segundos < 86400:
                horas = int(segundos / 3600)
                estado_texto = f"hace {horas} h"
            else:
                dias = int(segundos / 86400)
                estado_texto = (
                    "hace 1 día"
                    if dias == 1
                    else f"hace {dias} días"
                )
            estado = "INACTIVO"
        else:
            estado = "SIN_ACTIVIDAD"
            estado_texto = "—"

        if hora_ref:
            if hora_ref.tzinfo is None:
                hora_mostrar = hora_ref.replace(tzinfo=TZ_PERU)
            else:
                hora_mostrar = hora_ref
            hora_formateada = hora_mostrar.strftime("%H:%M:%S")
        else:
            hora_formateada = "—"

        total_hoy = totales_por_usuario.get(u.id, 0)

        SEGUNDOS_DIA_COMPLETO = 86400
        porcentaje = round((total_hoy / SEGUNDOS_DIA_COMPLETO) * 100, 2)
        if porcentaje > 100:
            porcentaje = 100

        iniciales = (
            (u.nombre[0] if u.nombre else "?")
            + (u.apellido[0] if u.apellido else "")
        ).upper()

        colores = [
            "#10a5f5", "#10a878", "#e6a23c",
            "#f56c6c", "#8b5cf6", "#ec4899"
        ]
        color_avatar = colores[u.id % len(colores)]

        miembros.append({
            "id": u.id,
            "nombre": f"{u.nombre} {u.apellido}",
            "iniciales": iniciales,
            "color_avatar": color_avatar,
            "email": u.email,
            "rol": u.rol,
            "ultima_actividad": ultima_actividad,
            "ultimo_proyecto": ultimo_proyecto,
            "hora": hora_formateada,
            "estado": estado,
            "estado_texto": estado_texto,
            "total_segundos": total_hoy,
            "porcentaje": porcentaje,
            "es_usuario_actual": (u.id == usuario.id)
        })

    def orden(m):
        prioridad = 0 if m["estado"] == "EN_CURSO" else 1
        return (prioridad, -m["total_segundos"])

    miembros.sort(key=orden)

    return {
        "fecha_inicio": str(fecha_inicio),
        "fecha_fin": str(fecha_fin),
        "miembros": miembros
    }