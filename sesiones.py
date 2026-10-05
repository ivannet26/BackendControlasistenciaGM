"""
Control de sesiones por usuario (punto 4 de la Práctica 26).

- Límite de sesiones activas simultáneas por usuario (MAX_SESIONES_ACTIVAS).
- Política al llegar al límite (SESIONES_POLITICA):
    "reemplazar" -> cierra la sesión más antigua y deja entrar (default)
    "rechazar"   -> el login falla con 409
- Revocación remota: una sesión, todas, o al desactivar la cuenta.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from sesion_models import SesionUsuario
from models import Usuario

MAX_SESIONES_ACTIVAS = int(os.getenv("MAX_SESIONES_ACTIVAS", "3"))
SESIONES_POLITICA = os.getenv("SESIONES_POLITICA", "reemplazar").strip().lower()
# Cada cuántos segundos se refresca `ultimo_uso` (evita un UPDATE por cada click)
TOUCH_INTERVALO_SEG = 60


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _activas_query(db: Session, usuario_id: int):
    return db.query(SesionUsuario).filter(
        SesionUsuario.usuario_id == usuario_id,
        SesionUsuario.activa == True,  # noqa: E712
        SesionUsuario.expira_en > ahora_utc(),
    )


def _marcar_expiradas(db: Session, usuario_id: int) -> None:
    ahora = ahora_utc()
    db.query(SesionUsuario).filter(
        SesionUsuario.usuario_id == usuario_id,
        SesionUsuario.activa == True,  # noqa: E712
        SesionUsuario.expira_en <= ahora,
    ).update(
        {"activa": False, "cerrada_en": ahora, "motivo_cierre": "EXPIRADA"},
        synchronize_session=False,
    )


def crear_sesion(
    db: Session,
    usuario: Usuario,
    jti: str,
    minutos_validez: int,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> SesionUsuario:
    """Registra la sesión aplicando el límite. Hace commit."""
    # Bloquea la fila del usuario para que dos logins simultáneos no se salten el límite
    db.query(Usuario).filter(Usuario.id == usuario.id).with_for_update().first()

    _marcar_expiradas(db, usuario.id)

    activas = _activas_query(db, usuario.id).order_by(SesionUsuario.creado_en.asc()).all()
    sobran = len(activas) - MAX_SESIONES_ACTIVAS + 1  # +1 por la que vamos a crear

    if sobran > 0:
        if SESIONES_POLITICA == "rechazar":
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Alcanzaste el límite de {MAX_SESIONES_ACTIVAS} sesiones activas. "
                    "Cierra una sesión en otro dispositivo o pide a un administrador que la cierre."
                ),
            )
        ahora = ahora_utc()
        for vieja in activas[:sobran]:
            vieja.activa = False
            vieja.cerrada_en = ahora
            vieja.motivo_cierre = "LIMITE"

    ahora = ahora_utc()
    sesion = SesionUsuario(
        usuario_id=usuario.id,
        jti=jti,
        ip=(ip or None) and ip[:45],
        user_agent=(user_agent or None) and user_agent[:255],
        creado_en=ahora,
        expira_en=ahora + timedelta(minutes=minutos_validez),
        ultimo_uso=ahora,
        activa=True,
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)
    return sesion


def revocar_sesion(db: Session, sesion: SesionUsuario, motivo: str) -> None:
    if sesion.activa:
        sesion.activa = False
        sesion.cerrada_en = ahora_utc()
        sesion.motivo_cierre = motivo


def revocar_todas(
    db: Session,
    usuario_id: int,
    motivo: str,
    excepto_jti: Optional[str] = None,
) -> int:
    """Cierra todas las sesiones activas del usuario. NO hace commit."""
    q = db.query(SesionUsuario).filter(
        SesionUsuario.usuario_id == usuario_id,
        SesionUsuario.activa == True,  # noqa: E712
    )
    if excepto_jti:
        q = q.filter(SesionUsuario.jti != excepto_jti)
    ahora = ahora_utc()
    return q.update(
        {"activa": False, "cerrada_en": ahora, "motivo_cierre": motivo},
        synchronize_session=False,
    )


def obtener_sesion_valida(db: Session, jti: Optional[str], usuario_id: int) -> Optional[SesionUsuario]:
    """Devuelve la sesión si existe, es del usuario, está activa y no venció."""
    if not jti:
        return None
    sesion = db.query(SesionUsuario).filter(SesionUsuario.jti == jti).first()
    if (
        not sesion
        or sesion.usuario_id != usuario_id
        or not sesion.activa
        or sesion.expira_en <= ahora_utc()
    ):
        return None

    ahora = ahora_utc()
    if (ahora - sesion.ultimo_uso).total_seconds() >= TOUCH_INTERVALO_SEG:
        sesion.ultimo_uso = ahora
        db.commit()
    return sesion