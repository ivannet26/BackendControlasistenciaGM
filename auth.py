import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db

load_dotenv()

# ── Configuración JWT ─────────────────────────────────────────────────────────
# SECRET_KEY: clave secreta para firmar los tokens. NUNCA la expongas.
SECRET_KEY  = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion-por-favor")
ALGORITHM   = "HS256"
# El token expira en 8 horas (ajusta según necesiten)
ACCESS_TOKEN_EXPIRE_MINUTES = 480

# ── Hashing de contraseñas ────────────────────────────────────────────────────
# bcrypt convierte "mi_password" → "$2b$12$..." (no reversible)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Le dice a FastAPI dónde esperar el token (header: Authorization: Bearer <token>)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Funciones de password ─────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Convierte contraseña en texto plano a hash bcrypt."""
    return pwd_context.hash(password)


def verificar_password(password_plano: str, password_hash: str) -> bool:
    """Compara contraseña ingresada contra el hash guardado en BD."""
    return pwd_context.verify(password_plano, password_hash)


# ── Funciones de JWT ──────────────────────────────────────────────────────────

def crear_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crea un JWT firmado con los datos del usuario.
    data: dict con lo que quieres guardar en el token (email, rol, id)
    """
    payload = data.copy()
    expira = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload.update({"exp": expira})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verificar_token(token: str) -> schemas.TokenData:
    """
    Decodifica y valida el JWT.
    Lanza excepción si el token es inválido o expiró.
    """
    credenciales_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar el token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        rol: str   = payload.get("rol")
        uid: int   = payload.get("id")
        if email is None:
            raise credenciales_exception
        return schemas.TokenData(email=email, rol=rol, usuario_id=uid)
    except JWTError:
        raise credenciales_exception


# ── Dependencia: usuario actual ───────────────────────────────────────────────

def get_usuario_actual(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.Usuario:
    """
    Dependencia de FastAPI: extrae y valida el token, devuelve el usuario de BD.
    Úsala en cualquier endpoint que requiera estar autenticado:
        @router.get("/protegido")
        def ruta(usuario = Depends(get_usuario_actual)):
    """
    token_data = verificar_token(token)
    usuario = db.query(models.Usuario).filter(
        models.Usuario.email == token_data.email
    ).first()
    if usuario is None or not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo",
        )
    return usuario


def requiere_rol(*roles_permitidos: str):
    """
    Dependencia de rol. Uso:
        @router.get("/solo-admin")
        def ruta(usuario = Depends(requiere_rol("admin"))):
    """
    def verificar(usuario: models.Usuario = Depends(get_usuario_actual)):
        if usuario.rol.nombre not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere rol: {', '.join(roles_permitidos)}",
            )
        return usuario
    return verificar
