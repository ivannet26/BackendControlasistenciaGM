from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.Database import get_db
from app.models import Usuario, MarcacionAsistencia
from app.Schemas import JornadaActual, JornadaHistorialItem, ReporteAdminItem
from app.Deps import obtener_usuario_actual, requiere_admin

router = APIRouter(prefix="/timetracker", tags=["Time Tracker"])


def _obtener_o_crear_marcacion_hoy(db: Session, idpracticante: int) -> MarcacionAsistencia:
    hoy = date.today()
    marcacion = (
        db.query(MarcacionAsistencia)
        .filter(MarcacionAsistencia.idpracticante == idpracticante, MarcacionAsistencia.fecha == hoy)
        .first()
    )
    return marcacion


@router.post("/start")
def iniciar_jornada(usuario: Usuario = Depends(obtener_usuario_actual), db: Session = Depends(get_db)):
    """Marca la hora de entrada del día actual para el usuario logueado."""
    hoy = date.today()
    ahora = datetime.now().time()

    marcacion = _obtener_o_crear_marcacion_hoy(db, usuario.idpracticante)

    if marcacion and marcacion.hora_entrada is not None:
        raise HTTPException(status_code=400, detail=f"Ya iniciaste tu jornada hoy a las {marcacion.hora_entrada}")

    if marcacion:
        marcacion.hora_entrada = ahora
    else:
        marcacion = MarcacionAsistencia(idpracticante=usuario.idpracticante, fecha=hoy, hora_entrada=ahora)
        db.add(marcacion)

    db.commit()
    return {"mensaje": "Jornada iniciada", "hora_inicio": str(ahora)}


@router.post("/stop")
def finalizar_jornada(usuario: Usuario = Depends(obtener_usuario_actual), db: Session = Depends(get_db)):
    """Marca la hora de salida del día actual para el usuario logueado."""
    ahora = datetime.now().time()
    marcacion = _obtener_o_crear_marcacion_hoy(db, usuario.idpracticante)

    if not marcacion or marcacion.hora_entrada is None:
        raise HTTPException(status_code=400, detail="No has iniciado tu jornada hoy todavía")

    if marcacion.hora_salida is not None:
        raise HTTPException(status_code=400, detail=f"Ya finalizaste tu jornada hoy a las {marcacion.hora_salida}")

    marcacion.hora_salida = ahora
    db.commit()
    return {"mensaje": "Jornada finalizada", "hora_fin": str(ahora)}


@router.get("/current", response_model=JornadaActual)
def jornada_actual(usuario: Usuario = Depends(obtener_usuario_actual), db: Session = Depends(get_db)):
    """Devuelve el estado de la jornada de hoy: si ya inició y/o finalizó."""
    hoy = date.today()
    marcacion = _obtener_o_crear_marcacion_hoy(db, usuario.idpracticante)

    if not marcacion:
        return JornadaActual(fecha=hoy, hora_entrada=None, hora_salida=None)

    return JornadaActual(fecha=hoy, hora_entrada=marcacion.hora_entrada, hora_salida=marcacion.hora_salida)


@router.get("/history", response_model=List[JornadaHistorialItem])
def historial_jornadas(
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Devuelve el historial de jornadas del usuario logueado, filtrable por rango de fechas."""
    query = db.query(MarcacionAsistencia).filter(MarcacionAsistencia.idpracticante == usuario.idpracticante)

    if desde:
        query = query.filter(MarcacionAsistencia.fecha >= desde)
    if hasta:
        query = query.filter(MarcacionAsistencia.fecha <= hasta)

    resultados = query.order_by(MarcacionAsistencia.fecha.desc()).all()
    return [
        JornadaHistorialItem(fecha=r.fecha, hora_entrada=r.hora_entrada, hora_salida=r.hora_salida)
        for r in resultados
    ]


@router.get("/report", response_model=List[ReporteAdminItem])
def reporte_admin(
    fecha: date = date.today(),
    usuario: Usuario = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    """(Solo administradores) Reporte de las jornadas de TODOS los practicantes en una fecha."""
    from app.models import Usuario as UsuarioModel

    resultados = (
        db.query(UsuarioModel.username, MarcacionAsistencia.hora_entrada, MarcacionAsistencia.hora_salida)
        .join(MarcacionAsistencia, MarcacionAsistencia.idpracticante == UsuarioModel.idpracticante)
        .filter(MarcacionAsistencia.fecha == fecha)
        .all()
    )
    return [
        ReporteAdminItem(username=r[0], hora_entrada=r[1], hora_salida=r[2])
        for r in resultados
    ]