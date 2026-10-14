from datetime import date, datetime, time
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from asistencia_models import RegistroAsistencia
from asistencia_schemas import (
    AsistenciaHoyResponse,
    RegistroAsistenciaCrear,
    RegistroAsistenciaOut,
    ResumenAsistenciaUsuario,
)
from auditoria_helper import registrar_auditoria
from database import get_db
from models import Usuario
from perfil_models import PerfilUsuario
from security import get_usuario_actual, requiere_admin


TZ_PERU = ZoneInfo("America/Lima")

router = APIRouter(prefix="/asistencia", tags=["Asistencia"])


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


def _respuesta_personal(
    db: Session, usuario_id: int, fecha: date
) -> AsistenciaHoyResponse:
    registros = _obtener_registros_fecha(db, usuario_id, fecha)
    return AsistenciaHoyResponse(
        usuario_id=usuario_id,
        fecha=fecha.isoformat(),
        registros=[_registro_a_salida(registro) for registro in registros],
        estado=obtener_estado_asistencia(registros),
    )


def _resumen_usuarios(
    db: Session, fecha: date
) -> List[ResumenAsistenciaUsuario]:
    inicio, fin = _rango_fecha(fecha)
    usuarios_con_perfil = (
        db.query(Usuario, PerfilUsuario)
        .outerjoin(PerfilUsuario, PerfilUsuario.usuario_id == Usuario.id)
        .order_by(Usuario.id.asc())
        .all()
    )
    registros = (
        db.query(RegistroAsistencia)
        .filter(
            RegistroAsistencia.hora >= inicio,
            RegistroAsistencia.hora <= fin,
        )
        .order_by(
            RegistroAsistencia.usuario_id.asc(),
            RegistroAsistencia.hora.asc(),
            RegistroAsistencia.id.asc(),
        )
        .all()
    )

    por_usuario: dict[int, List[RegistroAsistencia]] = {}
    for registro in registros:
        por_usuario.setdefault(registro.usuario_id, []).append(registro)

    resumen = []
    for usuario, perfil in usuarios_con_perfil:
        eventos = por_usuario.get(usuario.id, [])
        horas = {evento.tipo: _normalizar_hora(evento.hora) for evento in eventos}
        inicio_break = horas.get("BREAK_INICIO")
        fin_break = horas.get("BREAK_FIN")
        duracion_break = None
        if inicio_break is not None and fin_break is not None:
            duracion_break = int((fin_break - inicio_break).total_seconds())
        avatar_url = perfil.avatar_url if perfil else None

        resumen.append(
            ResumenAsistenciaUsuario(
                usuario_id=usuario.id,
                usuario_nombre=f"{usuario.nombre} {usuario.apellido}".strip(),
                usuario_email=usuario.email,
                rol=usuario.rol or "",
                avatar_url=avatar_url,
                entrada=horas.get("ENTRADA"),
                break_inicio=inicio_break,
                break_fin=fin_break,
                salida=horas.get("SALIDA"),
                duracion_break_segundos=duracion_break,
                estado=obtener_estado_asistencia(eventos),
                tiene_entrada="ENTRADA" in horas,
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
