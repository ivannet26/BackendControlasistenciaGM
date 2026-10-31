# refresh_tokens.py
"""Refresh tokens opacos con rotación, gracia de 60 s y detección de reuso.

- El texto del token solo viaja al cliente; en BD queda su SHA-256.
- Cada rotación encadena `reemplazado_por`, y esa cadena define la familia.
- El tope absoluto se mide desde `creado_en` del token raíz de la familia.
- Si se reutiliza un token ya rotado dentro de la gracia y su sucesor nunca
  se usó, se restaura el token original (la respuesta anterior se perdió).
  Fuera de la gracia se revoca la familia completa.

Nota: al guardar solo el hash no se puede recuperar el texto del token que
emitió la rotación anterior; por eso la gracia restaura el token que el
cliente ya tiene en lugar de devolver el plaintext del sucesor.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from refresh_models import RefreshToken


REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
REFRESH_MAX_DAYS = int(os.getenv("REFRESH_MAX_DAYS", "180"))
GRACIA_REUTILIZACION_SEG = 60


def ahora_utc() -> datetime:
    """UTC sin tzinfo: el formato en que MySQL guarda los DATETIME."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_refresh_token(token_plano: str) -> str:
    return hashlib.sha256(token_plano.encode("utf-8")).hexdigest()


def _acortar(valor: Optional[str], largo: int) -> Optional[str]:
    if not valor:
        return None
    return valor[:largo]


def _tope_familia(raiz: RefreshToken) -> datetime:
    return raiz.creado_en + timedelta(days=REFRESH_MAX_DAYS)


def buscar_refresh_token(
    db: Session, token_plano: str, con_bloqueo: bool = False
) -> Optional[RefreshToken]:
    """Busca por hash. `con_bloqueo` serializa rotaciones concurrentes."""
    if not token_plano:
        return None
    consulta = db.query(RefreshToken).filter(
        RefreshToken.token_hash == hash_refresh_token(token_plano)
    )
    if con_bloqueo:
        consulta = consulta.with_for_update()
    return consulta.first()


def raiz_familia(db: Session, fila: RefreshToken) -> RefreshToken:
    """Sube por la cadena hasta el token original de la familia."""
    actual = fila
    vistos = {actual.id}
    while True:
        padre = (
            db.query(RefreshToken)
            .filter(RefreshToken.reemplazado_por == actual.id)
            .first()
        )
        if padre is None or padre.id in vistos:
            return actual
        vistos.add(padre.id)
        actual = padre


def ids_familia(db: Session, fila: RefreshToken) -> list[int]:
    raiz = raiz_familia(db, fila)
    ids = [raiz.id]
    vistos = {raiz.id}
    actual = raiz
    while actual.reemplazado_por:
        if actual.reemplazado_por in vistos:
            break
        hijo = (
            db.query(RefreshToken)
            .filter(RefreshToken.id == actual.reemplazado_por)
            .first()
        )
        if hijo is None:
            break
        ids.append(hijo.id)
        vistos.add(hijo.id)
        actual = hijo
    return ids


def emitir_refresh_token(
    db: Session,
    usuario_id: int,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    raiz: Optional[RefreshToken] = None,
    ahora: Optional[datetime] = None,
) -> Optional[tuple[str, RefreshToken]]:
    """Crea un refresh nuevo y devuelve (texto_plano, fila)."""
    ahora = ahora or ahora_utc()
    expira = ahora + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    if raiz is not None:
        tope = _tope_familia(raiz)
        if expira > tope:
            expira = tope
        if expira <= ahora:
            # Tope absoluto alcanzado: hay que iniciar sesión de nuevo.
            return None

    plano = secrets.token_urlsafe(48)
    fila = RefreshToken(
        usuario_id=usuario_id,
        token_hash=hash_refresh_token(plano),
        creado_en=ahora,
        expira_en=expira,
        revocado_en=None,
        reemplazado_por=None,
        ip=_acortar(ip, 45),
        user_agent=_acortar(user_agent, 255),
    )
    db.add(fila)
    db.flush()
    return plano, fila


def rotar_refresh_token(
    db: Session,
    fila: RefreshToken,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    ahora: Optional[datetime] = None,
) -> Optional[str]:
    """Revoca `fila` y emite su sucesor dentro de la misma familia."""
    ahora = ahora or ahora_utc()
    raiz = raiz_familia(db, fila)

    emitido = emitir_refresh_token(
        db,
        fila.usuario_id,
        ip=ip,
        user_agent=user_agent,
        raiz=raiz,
        ahora=ahora,
    )
    if emitido is None:
        return None

    plano, nueva = emitido
    fila.revocado_en = ahora
    fila.reemplazado_por = nueva.id
    db.flush()
    return plano


def reutilizar_en_gracia(
    db: Session,
    fila: RefreshToken,
    ahora: Optional[datetime] = None,
) -> bool:
    """Restaura el token si es un reintento dentro de la ventana de gracia."""
    ahora = ahora or ahora_utc()

    if fila.revocado_en is None or not fila.reemplazado_por:
        return False

    if (ahora - fila.revocado_en).total_seconds() > GRACIA_REUTILIZACION_SEG:
        return False

    sucesor = (
        db.query(RefreshToken)
        .filter(RefreshToken.id == fila.reemplazado_por)
        .first()
    )

    # Si el sucesor ya se usó, no es un reintento: es reutilización real.
    if sucesor is None or sucesor.reemplazado_por is not None:
        return False

    raiz = raiz_familia(db, fila)
    expira = ahora + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    tope = _tope_familia(raiz)
    if expira > tope:
        expira = tope
    if expira <= ahora:
        return False

    if sucesor.revocado_en is None:
        sucesor.revocado_en = ahora

    fila.revocado_en = None
    fila.reemplazado_por = None
    fila.expira_en = expira
    db.flush()
    return True


def revocar_familia_refresh(
    db: Session,
    fila: RefreshToken,
    ahora: Optional[datetime] = None,
) -> int:
    ahora = ahora or ahora_utc()
    ids = ids_familia(db, fila)
    return (
        db.query(RefreshToken)
        .filter(
            RefreshToken.id.in_(ids),
            RefreshToken.revocado_en.is_(None),
        )
        .update({"revocado_en": ahora}, synchronize_session=False)
    )


def revocar_refresh_de_usuario(
    db: Session,
    usuario_id: int,
    ahora: Optional[datetime] = None,
) -> int:
    """Revoca todos los refresh activos del usuario (contraseña / baja)."""
    ahora = ahora or ahora_utc()
    return (
        db.query(RefreshToken)
        .filter(
            RefreshToken.usuario_id == usuario_id,
            RefreshToken.revocado_en.is_(None),
        )
        .update({"revocado_en": ahora}, synchronize_session=False)
    )
