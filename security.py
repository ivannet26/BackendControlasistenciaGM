from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import os

from database import get_db
from models import Usuario
from sesion_models import SesionUsuario
from sesiones import obtener_sesion_valida


SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "tu-clave-secreta-super-segura-cambia-esta"
)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

security = HTTPBearer()

# ============================================================
# HASHEO DE CONTRASEÑAS con bcrypt
# ============================================================

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Genera un hash bcrypt de la contraseña."""
    return _pwd_context.hash(password)


def verificar_password(
    plain_password: str,
    hashed_password: str
) -> bool:
    """Verifica la contraseña contra su hash bcrypt."""
    return _pwd_context.verify(plain_password, hashed_password)


def es_texto_plano(password_hash: str) -> bool:
    """
    Detecta si el valor guardado es texto plano (no un hash bcrypt).
    Los hashes bcrypt siempre empiezan con '$2b$' o '$2a$'.
    """
    return not (
        password_hash.startswith("$2b$") or
        password_hash.startswith("$2a$")
    )


# ============================================================
# JWT
# ============================================================

def crear_token(
    data: dict,
    expires_delta: timedelta = None
) -> str:

    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def decodificar_token(token: str):

    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

    except JWTError:
        return None


def _validar_credenciales(
    credentials: HTTPAuthorizationCredentials,
    db: Session,
):
    """Valida JWT + usuario + sesión en BD. Devuelve (usuario, sesion)."""
    payload = decodificar_token(credentials.credentials)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("sub")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario = db.query(Usuario).filter(
        Usuario.email == email
    ).first()

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado",
        )

    # La sesión debe seguir activa en BD (no cerrada por logout, límite o admin)
    sesion = obtener_sesion_valida(db, payload.get("jti"), usuario.id)
    if not sesion:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión cerrada o expirada. Inicia sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return usuario, sesion


def get_usuario_actual(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Usuario:
    usuario, _ = _validar_credenciales(credentials, db)
    return usuario


def get_sesion_actual(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> SesionUsuario:
    """Devuelve la sesión (fila de sesiones_usuario) del token actual."""
    _, sesion = _validar_credenciales(credentials, db)
    return sesion


# ============================================================
# PERMISOS: SOLO ADMINISTRADORES
# ============================================================

ROLES_ADMIN = {
    "ADMIN",
    "ADMINISTRADOR",
    "ADMINISTRACION",
    "SUPERADMIN",
}


def requiere_admin(
    usuario: Usuario = Depends(get_usuario_actual)
) -> Usuario:
    """Solo ADMIN / ADMINISTRADOR pueden acceder."""
    rol = (getattr(usuario, "rol", "") or "").strip().upper()

    if rol not in ROLES_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para realizar esta acción. Se requiere rol de administrador."
        )

    return usuario


# ============================================================
# PERMISOS ELEVADOS PARA AUDITORÍA
# ============================================================

ROLES_AUDITORIA = {
    "ADMIN",
    "ADMINISTRADOR",
    "SUPERADMIN",
    "SUPERVISOR",
}


def requiere_auditoria(
    usuario: Usuario = Depends(get_usuario_actual)
) -> Usuario:

    rol = (
        getattr(usuario, "rol", "") or ""
    ).strip().upper()

    if rol not in ROLES_AUDITORIA:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para consultar la auditoría de proyectos"
        )

    return usuario
