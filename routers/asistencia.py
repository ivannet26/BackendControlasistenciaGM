from datetime import date, datetime, time, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from asistencia_models import HistorialHorasPracticas, RegistroAsistencia
from asistencia_schemas import (
    AsistenciaHoyResponse,
    HistorialManualCrear,
    HistorialManualOut,
    RegistroAsistenciaCrear,
    RegistroAsistenciaOut,
    ResumenAsistenciaUsuario,
)
from auditoria_helper import registrar_auditoria
from database import get_db
from justificacion_models import Justificacion
from horario_models import HorarioBloque
from models import Usuario
from perfil_models import PerfilUsuario
from security import get_usuario_actual, requiere_admin


TZ_PERU = ZoneInfo("America/Lima")

router = APIRouter(prefix="/asistencia", tags=["Asistencia"])

META_SEMANAL_BASE_HORAS = 40.0
META_SEMANAL_BASE_SEGUNDOS = int(META_SEMANAL_BASE_HORAS * 3600)  # 144000
# Tope semanal usado solo para el cálculo de deuda. Las horas extra por
# encima de 40 h no reducen la deuda ni la meta de la semana siguiente.
TOPE_SEMANAL_DEUDA_SEGUNDOS = META_SEMANAL_BASE_SEGUNDOS  # 144000


def _segundos_computables_semana(segundos_trabajados: int) -> int:
    """Horas de una semana que cuentan para la deuda (máximo 40 h).

    Las horas extra se siguen mostrando en el tiempo trabajado y en el
    acumulado histórico, pero aquí se recortan: no compensan faltantes de
    esa semana ni reducen la meta de la semana siguiente.
    """
    return max(0, min(int(segundos_trabajados), TOPE_SEMANAL_DEUDA_SEGUNDOS))


def _deuda_semana_desde_segundos(segundos_trabajados: int) -> int:
    """Deuda de una semana ya finalizada, ignorando las horas extra."""
    return max(
        0,
        META_SEMANAL_BASE_SEGUNDOS
        - _segundos_computables_semana(segundos_trabajados),
    )


def _rango_fecha(fecha: date) -> tuple[datetime, datetime]:
    inicio = datetime.combine(fecha, time.min, tzinfo=TZ_PERU)
    fin = datetime.combine(fecha, time.max, tzinfo=TZ_PERU)
    return inicio, fin


def _normalizar_hora(hora: datetime) -> datetime:
    # MySQL puede devolver naive los DateTime; se interpretan como hora local.
    if hora.tzinfo is None:
        return hora.replace(tzinfo=TZ_PERU)
    return hora.astimezone(TZ_PERU)


def _registro_a_salida(registro: RegistroAsistencia) -> dict:
    return {
        "id": registro.id,
        "usuario_id": registro.usuario_id,
        "tipo": registro.tipo,
        "hora": _normalizar_hora(registro.hora),
        "notas": registro.notas,
    }


def obtener_registros_hoy(db: Session, usuario_id: int) -> List[RegistroAsistencia]:
    hoy = datetime.now(TZ_PERU).date()
    inicio, fin = _rango_fecha(hoy)
    return (
        db.query(RegistroAsistencia)
        .filter(
            RegistroAsistencia.usuario_id == usuario_id,
            RegistroAsistencia.hora >= inicio,
            RegistroAsistencia.hora <= fin,
        )
        .order_by(RegistroAsistencia.hora.asc(), RegistroAsistencia.id.asc())
        .all()
    )


def _obtener_registros_fecha(
    db: Session, usuario_id: int, fecha: date, bloquear: bool = False
) -> List[RegistroAsistencia]:
    inicio, fin = _rango_fecha(fecha)
    consulta = (
        db.query(RegistroAsistencia)
        .filter(
            RegistroAsistencia.usuario_id == usuario_id,
            RegistroAsistencia.hora >= inicio,
            RegistroAsistencia.hora <= fin,
        )
        .order_by(RegistroAsistencia.hora.asc(), RegistroAsistencia.id.asc())
    )
    if bloquear:
        consulta = consulta.with_for_update()
    return consulta.all()


def obtener_estado_asistencia(registros: List[RegistroAsistencia]) -> str:
    if not registros:
        return "SIN_ENTRADA"

    ultimo_tipo = registros[-1].tipo
    if ultimo_tipo in ("ENTRADA", "BREAK_FIN"):
        return "TRABAJANDO"
    if ultimo_tipo == "BREAK_INICIO":
        return "EN_BREAK"
    if ultimo_tipo == "SALIDA":
        return "FINALIZADO"
    return "SIN_ENTRADA"


def _crear_registro(
    db: Session,
    usuario: Usuario,
    tipo: str,
    notas: Optional[str],
    request: Request,
) -> dict:
    # El bloqueo serializa las validaciones y escrituras de un mismo usuario.
    usuario_bloqueado = (
        db.query(Usuario)
        .filter(Usuario.id == usuario.id)
        .with_for_update()
        .first()
    )
    if usuario_bloqueado is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    ahora = datetime.now(TZ_PERU)
    registros = _obtener_registros_fecha(
        db, usuario.id, ahora.date(), bloquear=True
    )
    estado = obtener_estado_asistencia(registros)

    if tipo == "ENTRADA":
        if any(registro.tipo == "ENTRADA" for registro in registros):
            raise HTTPException(
                status_code=400,
                detail="Ya registraste tu entrada hoy",
            )
        if estado != "SIN_ENTRADA":
            raise HTTPException(
                status_code=400,
                detail="No puedes registrar entrada después de iniciar tu jornada",
            )
    elif tipo == "BREAK_INICIO":
        if any(registro.tipo == "BREAK_INICIO" for registro in registros):
            raise HTTPException(
                status_code=400,
                detail="Ya registraste un descanso hoy",
            )
        if estado != "TRABAJANDO":
            raise HTTPException(
                status_code=400,
                detail="Solo puedes iniciar un descanso mientras estás trabajando",
            )
    elif tipo == "BREAK_FIN":
        if estado != "EN_BREAK":
            raise HTTPException(
                status_code=400,
                detail="No tienes un descanso activo",
            )
    elif tipo == "SALIDA":
        if any(registro.tipo == "SALIDA" for registro in registros):
            raise HTTPException(
                status_code=400,
                detail="Ya registraste tu salida hoy",
            )
        if estado == "EN_BREAK":
            raise HTTPException(
                status_code=400,
                detail="Debes terminar tu descanso antes de registrar la salida",
            )
        if estado != "TRABAJANDO":
            raise HTTPException(
                status_code=400,
                detail="Solo puedes registrar salida mientras estás trabajando",
            )

    registro = RegistroAsistencia(
        usuario_id=usuario.id,
        tipo=tipo,
        hora=ahora,
        ip_address=request.client.host if request.client else None,
        notas=notas,
    )
    db.add(registro)
    db.flush()

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="ASISTENCIA",
        entidad="ASISTENCIA",
        entidad_id=registro.id,
        entidad_nombre=f"{usuario.nombre} {usuario.apellido}",
        detalle=f"Registró {tipo} a las {ahora.isoformat()}",
    )
    respuesta = _registro_a_salida(registro)
    db.commit()
    return respuesta


def _fecha_hoy() -> date:
    return datetime.now(TZ_PERU).date()


def _horas_horario_fecha(
    db: Session, usuario_id: int, fecha: date
) -> tuple[float, Optional[int]]:
    bloques = (
        db.query(HorarioBloque)
        .filter(
            HorarioBloque.usuario_id == usuario_id,
            HorarioBloque.dia_semana == fecha.isoweekday(),
        )
        .all()
    )
    if not bloques:
        return 8.0, None
    hora_inicio = min(bloque.hora_inicio for bloque in bloques)
    horas_distintas = len({
        bloque.hora_inicio for bloque in bloques
    })
    return float(horas_distintas), hora_inicio


def _horas_horario_semana(db: Session, usuario_id: int, lunes: date) -> float:
    horas_totales = 0.0
    for dia in range(7):
        fecha = lunes + timedelta(days=dia)
        horas_totales += _horas_horario_fecha(db, usuario_id, fecha)[0]
    return horas_totales if horas_totales else 40.0


def _meta_semanal_base(db: Session, usuario_id: int, lunes: date) -> float:
    return META_SEMANAL_BASE_HORAS


def _deuda_horas_semanas_finalizadas(
    db: Session,
    usuario_id: int,
    lunes_actual: date,
) -> int:
    lunes_semana_anterior = lunes_actual - timedelta(days=7)
    domingo_semana_anterior = lunes_semana_anterior + timedelta(days=6)

    fechas_usuario = (
        db.query(
            Usuario.fecha_inicio_rastreo,
            Usuario.fecha_inicio_practicas,
        )
        .filter(Usuario.id == usuario_id)
        .first()
    )
    fecha_inicio_rastreo, fecha_inicio_practicas = (
        fechas_usuario if fechas_usuario is not None else (None, None)
    )

    # El inicio de rastreo manda: las semanas anteriores al corte no generan
    # deuda. La semana en la que cae el corte también se condona para no
    # cobrar deuda por días previos al corte (mismo criterio que ya se usaba
    # con fecha_inicio_practicas).
    if fecha_inicio_rastreo is not None:
        if lunes_semana_anterior < fecha_inicio_rastreo:
            return 0
        corte = fecha_inicio_rastreo
    elif fecha_inicio_practicas is not None:
        if lunes_semana_anterior < fecha_inicio_practicas:
            return 0
        corte = fecha_inicio_practicas
    else:
        primer_registro = (
            db.query(RegistroAsistencia)
            .filter(RegistroAsistencia.usuario_id == usuario_id)
            .order_by(RegistroAsistencia.hora.asc())
            .first()
        )
        if primer_registro is None:
            return 0

        fecha_primer_registro = _normalizar_hora(primer_registro.hora).date()
        if fecha_primer_registro > domingo_semana_anterior:
            return 0
        corte = None

    segundos_trabajados = 0
    for dia in range(7):
        fecha_dia = lunes_semana_anterior + timedelta(days=dia)
        if corte is not None and fecha_dia < corte:
            continue
        efectivo, _, _ = _tiempo_efectivo_dia(
            _registros_fecha(db, usuario_id, fecha_dia),
            datetime.combine(fecha_dia, time.max, tzinfo=TZ_PERU),
        )
        segundos_trabajados += efectivo

    # Regla de negocio: la meta semanal es siempre 40 h y las horas extra de
    # la semana no generan crédito. Se aplica el tope una sola vez, sobre el
    # total de la semana (no por día), porque el excedente de un día puede
    # compensar un faltante de otro dentro de la misma semana.
    return _deuda_semana_desde_segundos(segundos_trabajados)


def _registros_fecha(db: Session, usuario_id: int, fecha: date) -> list[RegistroAsistencia]:
    return _obtener_registros_fecha(db, usuario_id, fecha)


def _tiempo_efectivo_dia(
    registros: List[RegistroAsistencia],
    ahora: datetime,
) -> tuple[int, int, int]:
    entrada = next(
        (_normalizar_hora(registro.hora) for registro in registros if registro.tipo == "ENTRADA"),
        None,
    )
    if entrada is None:
        return 0, 0, 0

    salida = next(
        (_normalizar_hora(registro.hora) for registro in registros if registro.tipo == "SALIDA"),
        None,
    )
    fin_jornada = salida or ahora
    if fin_jornada < entrada:
        fin_jornada = entrada

    break_inicio: Optional[datetime] = None
    segmentos_break: list[tuple[datetime, datetime]] = []
    for registro in registros:
        momento = _normalizar_hora(registro.hora)
        if registro.tipo == "BREAK_INICIO" and break_inicio is None:
            break_inicio = momento
        elif registro.tipo == "BREAK_FIN" and break_inicio is not None:
            if momento >= break_inicio:
                segmentos_break.append((break_inicio, momento))
            break_inicio = None

    if break_inicio is not None and break_inicio < fin_jornada:
        segmentos_break.append((break_inicio, fin_jornada))

    segundos_break = sum(
        max(0, int((min(fin, fin_jornada) - max(inicio, entrada)).total_seconds()))
        for inicio, fin in segmentos_break
        if fin >= entrada and inicio <= fin_jornada
    )
    # Regla de negocio: el break es solo informativo, NO se descuenta del total.
    segundos_efectivos = max(0, int((fin_jornada - entrada).total_seconds()))
    return (
        segundos_efectivos,
        segundos_break,
        int((fin_jornada - entrada).total_seconds()),
    )


@router.get("/resumen-horas")
def resumen_horas(
    fecha: Optional[date] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    hoy = fecha or _fecha_hoy()
    ahora = datetime.now(TZ_PERU)
    fecha_fin_semana = hoy
    lunes = hoy - timedelta(days=hoy.weekday())

    registros_hoy = _registros_fecha(db, usuario.id, hoy)
    horas_objetivo, hora_inicio = _horas_horario_fecha(db, usuario.id, hoy)
    segundos_objetivo = int(horas_objetivo * 3600)

    trabajando, en_break, presencia = _tiempo_efectivo_dia(
        registros_hoy,
        ahora if hoy == _fecha_hoy() else datetime.combine(
            hoy, time.max, tzinfo=TZ_PERU
        ),
    )
    pendiente = max(0, segundos_objetivo - trabajando)
    entrada = next(
        (
            _normalizar_hora(registro.hora)
            for registro in registros_hoy
            if registro.tipo == "ENTRADA"
        ),
        None,
    )
    estado_dia = "SIN_ENTRADA"
    if entrada is not None:
        estado_dia = obtener_estado_asistencia(registros_hoy)

    tardanza = False
    minutos_tardanza = 0
    if entrada is not None and hora_inicio is not None:
        inicio_programado = datetime.combine(
            hoy,
            time(hour=hora_inicio),
            tzinfo=TZ_PERU,
        )
        minutos_tardanza = max(
            0,
            int((entrada - inicio_programado).total_seconds() // 60),
        )
        tardanza = entrada > inicio_programado + timedelta(minutes=30)

    inicio_semana = lunes
    registros_semana = []
    for dia in range(7):
        fecha_dia = inicio_semana + timedelta(days=dia)
        if fecha_dia > fecha_fin_semana:
            break
        registros_semana.extend(_registros_fecha(db, usuario.id, fecha_dia))

    corte_semana = usuario.fecha_inicio_rastreo
    segundos_semana = 0
    for dia in range((fecha_fin_semana - lunes).days + 1):
        fecha_dia = lunes + timedelta(days=dia)
        if corte_semana is not None and fecha_dia < corte_semana:
            continue
        efectivo, _, _ = _tiempo_efectivo_dia(
            _registros_fecha(db, usuario.id, fecha_dia),
            ahora if fecha_dia == _fecha_hoy() else datetime.combine(
                fecha_dia, time.max, tzinfo=TZ_PERU
            ),
        )
        segundos_semana += efectivo

    meta_base = _meta_semanal_base(db, usuario.id, lunes)
    segundos_deuda = _deuda_horas_semanas_finalizadas(db, usuario.id, lunes)
    meta_ajustada = meta_base + (segundos_deuda / 3600)
    mensaje_deuda = None
    if segundos_deuda > 0:
        horas_deuda = segundos_deuda / 3600
        mensaje_deuda = (
            f"Tienes {horas_deuda:g} horas pendientes de semanas anteriores. "
            f"Meta ajustada: {meta_ajustada:g}h"
        )

    tarde_semana = 0
    for dia in range((hoy - lunes).days + 1):
        fecha_dia = lunes + timedelta(days=dia)
        registros_dia = _registros_fecha(db, usuario.id, fecha_dia)
        entrada_dia = next(
            (
                _normalizar_hora(registro.hora)
                for registro in registros_dia
                if registro.tipo == "ENTRADA"
            ),
            None,
        )
        _, hora_inicio_dia = _horas_horario_fecha(db, usuario.id, fecha_dia)
        if entrada_dia is not None and hora_inicio_dia is not None:
            inicio_dia = datetime.combine(
                fecha_dia,
                time(hour=hora_inicio_dia),
                tzinfo=TZ_PERU,
            )
            if entrada_dia > inicio_dia + timedelta(minutes=30):
                tarde_semana += 1

    historial = (
        db.query(HistorialHorasPracticas)
        .filter(HistorialHorasPracticas.usuario_id == usuario.id)
        .first()
    )
    horas_historial = float(historial.horas_acumuladas) if historial else 0.0

    return {
        "usuario_id": usuario.id,
        "fecha": hoy.isoformat(),
        "diario": {
            "horas_objetivo": horas_objetivo,
            "segundos_objetivo": segundos_objetivo,
            "trabajando_segundos": trabajando,
            "en_break_segundos": en_break,
            "pendiente_segundos": pendiente,
            "presencia_segundos": presencia,
            "estado": estado_dia,
        },
        "tardanza": {
            "aplica": tardanza,
            "minutos_desde_inicio": minutos_tardanza,
            "tolerancia_minutos": 30,
            "cantidad_semana": tarde_semana,
        },
        "semanal": {
            "meta_base_horas": meta_base,
            "meta_ajustada_horas": meta_ajustada,
            "trabajadas_segundos": segundos_semana,
            "pendiente_segundos": max(
                0,
                int(meta_ajustada * 3600) - segundos_semana,
            ),
            "horas_deuda_semana_anterior": segundos_deuda / 3600,
            "mensaje_deuda": mensaje_deuda,
            "semana_inicio": lunes.isoformat(),
            "semana_fin": (lunes + timedelta(days=6)).isoformat(),
        },
        "historial_practicas": {
            "horas_acumuladas": horas_historial,
        },
    }


@router.post("/historial-manual", response_model=HistorialManualOut)
def registrar_historial_manual(
    datos: HistorialManualCrear,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    usuario = db.query(Usuario).filter(Usuario.id == datos.usuario_id).first()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    historial = (
        db.query(HistorialHorasPracticas)
        .filter(HistorialHorasPracticas.usuario_id == datos.usuario_id)
        .first()
    )
    if historial is None:
        historial = HistorialHorasPracticas(usuario_id=datos.usuario_id)
        db.add(historial)

    historial.horas_acumuladas = datos.horas_acumuladas
    db.commit()
    db.refresh(historial)
    return HistorialManualOut(
        usuario_id=historial.usuario_id,
        horas_acumuladas=float(historial.horas_acumuladas),
        actualizado_en=_normalizar_hora(historial.actualizado_en),
    )


def _respuesta_personal(
    db: Session, usuario_id: int, fecha: date
) -> AsistenciaHoyResponse:
    registros = _obtener_registros_fecha(db, usuario_id, fecha)
    justificacion_falta = (
        db.query(Justificacion)
        .filter(
            Justificacion.usuario_id == usuario_id,
            Justificacion.fecha == fecha,
            Justificacion.tipo == "Falta",
            Justificacion.estado == "ACEPTADA",
        )
        .order_by(
            Justificacion.intento_numero.desc(),
            Justificacion.fecha_resolucion.desc(),
            Justificacion.id.desc(),
        )
        .first()
    )

    estado = obtener_estado_asistencia(registros)
    if justificacion_falta is not None:
        estado = "FALTA_JUSTIFICADA"

    return AsistenciaHoyResponse(
        usuario_id=usuario_id,
        fecha=fecha.isoformat(),
        registros=[_registro_a_salida(registro) for registro in registros],
        estado=estado,
        justificacion_falta=(
            {
                "asunto": justificacion_falta.asunto,
                "mensaje": justificacion_falta.mensaje,
            }
            if justificacion_falta is not None
            else None
        ),
    )


def _resumen_usuarios(
    db: Session, fecha: date
) -> List[ResumenAsistenciaUsuario]:
    _, fin = _rango_fecha(fecha)
    ahora = datetime.now(TZ_PERU)
    fecha_hoy = _fecha_hoy()
    usuarios_con_perfil = (
        db.query(Usuario, PerfilUsuario)
        .outerjoin(PerfilUsuario, PerfilUsuario.usuario_id == Usuario.id)
        .order_by(Usuario.id.asc())
        .all()
    )
    registros = (
        db.query(RegistroAsistencia)
        .filter(RegistroAsistencia.hora <= fin)
        .order_by(
            RegistroAsistencia.usuario_id.asc(),
            RegistroAsistencia.hora.asc(),
            RegistroAsistencia.id.asc(),
        )
        .all()
    )

    registros_por_usuario: dict[
        int, dict[date, List[RegistroAsistencia]]
    ] = {}
    for registro in registros:
        fecha_registro = _normalizar_hora(registro.hora).date()
        registros_por_usuario.setdefault(registro.usuario_id, {}).setdefault(
            fecha_registro, []
        ).append(registro)

    justificaciones_aceptadas = (
        db.query(Justificacion)
        .filter(
            Justificacion.fecha == fecha,
            Justificacion.estado == "ACEPTADA",
        )
        .all()
    )
    por_usuario_justificacion = {
        justificacion.usuario_id: justificacion
        for justificacion in justificaciones_aceptadas
    }

    resumen = []
    for usuario, perfil in usuarios_con_perfil:
        dias_registrados = registros_por_usuario.get(usuario.id, {})
        eventos = dias_registrados.get(fecha, [])
        justificacion = por_usuario_justificacion.get(usuario.id)
        horas = {evento.tipo: _normalizar_hora(evento.hora) for evento in eventos}
        inicio_break = horas.get("BREAK_INICIO")
        fin_break = horas.get("BREAK_FIN")
        duracion_break = None
        if inicio_break is not None and fin_break is not None:
            duracion_break = int((fin_break - inicio_break).total_seconds())
        avatar_url = perfil.avatar_url if perfil else None
        # El inicio de rastreo manda; si no existe, se mantiene el filtro
        # actual por fecha_inicio_practicas (o todo el historial si es NULL).
        corte_acumulado = (
            usuario.fecha_inicio_rastreo
            if usuario.fecha_inicio_rastreo is not None
            else usuario.fecha_inicio_practicas
        )
        segundos_acumulados = 0
        for fecha_registro, eventos_dia in dias_registrados.items():
            if (
                corte_acumulado is not None
                and fecha_registro < corte_acumulado
            ):
                continue
            fin_jornada = (
                ahora
                if fecha_registro == fecha and fecha == fecha_hoy
                else datetime.combine(
                    fecha_registro, time.max, tzinfo=TZ_PERU
                )
            )
            segundos_dia, _, _ = _tiempo_efectivo_dia(
                eventos_dia,
                fin_jornada,
            )
            segundos_acumulados += segundos_dia

        resumen.append(
            ResumenAsistenciaUsuario(
                usuario_id=usuario.id,
                usuario_nombre=f"{usuario.nombre} {usuario.apellido}".strip(),
                usuario_email=usuario.email,
                rol=usuario.rol or "",
                horas_acumuladas=segundos_acumulados / 3600,
                fecha_inicio_practicas=usuario.fecha_inicio_practicas,
                fecha_inicio_rastreo=usuario.fecha_inicio_rastreo,
                avatar_url=avatar_url,
                entrada=horas.get("ENTRADA"),
                break_inicio=inicio_break,
                break_fin=fin_break,
                salida=horas.get("SALIDA"),
                duracion_break_segundos=duracion_break,
                estado=obtener_estado_asistencia(eventos),
                tiene_entrada="ENTRADA" in horas,
                justificacion_aceptada=justificacion is not None,
                comentario_admin=(
                    justificacion.comentario_admin if justificacion else None
                ),
                justificacion_asunto=(
                    justificacion.asunto if justificacion else None
                ),
                justificacion_mensaje=(
                    justificacion.mensaje if justificacion else None
                ),
                justificacion_evidencia_url=(
                    justificacion.evidencia_url if justificacion else None
                ),
            )
        )
    return resumen


@router.post("/entrada", response_model=RegistroAsistenciaOut)
def registrar_entrada(
    request: Request,
    datos: Optional[RegistroAsistenciaCrear] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return _crear_registro(
        db, usuario, "ENTRADA", datos.notas if datos else None, request
    )


@router.post("/break/iniciar", response_model=RegistroAsistenciaOut)
def iniciar_break(
    request: Request,
    datos: Optional[RegistroAsistenciaCrear] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return _crear_registro(
        db, usuario, "BREAK_INICIO", datos.notas if datos else None, request
    )


@router.post("/break/terminar", response_model=RegistroAsistenciaOut)
def terminar_break(
    request: Request,
    datos: Optional[RegistroAsistenciaCrear] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return _crear_registro(
        db, usuario, "BREAK_FIN", datos.notas if datos else None, request
    )


@router.post("/salida", response_model=RegistroAsistenciaOut)
def registrar_salida(
    request: Request,
    datos: Optional[RegistroAsistenciaCrear] = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return _crear_registro(
        db, usuario, "SALIDA", datos.notas if datos else None, request
    )


@router.get("/hoy", response_model=AsistenciaHoyResponse)
def asistencia_hoy(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return _respuesta_personal(db, usuario.id, _fecha_hoy())


@router.get("/por-fecha", response_model=AsistenciaHoyResponse)
def asistencia_por_fecha(
    fecha: date,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return _respuesta_personal(db, usuario.id, fecha)


@router.get("/admin/hoy", response_model=List[ResumenAsistenciaUsuario])
def asistencia_admin_hoy(
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    return _resumen_usuarios(db, _fecha_hoy())


@router.get("/admin/por-fecha", response_model=List[ResumenAsistenciaUsuario])
def asistencia_admin_por_fecha(
    fecha: date,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    return _resumen_usuarios(db, fecha)
