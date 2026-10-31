from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import models
import schemas
from perfil_models import PerfilUsuario
from security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    crear_token,
    get_usuario_actual,
    hash_password,
    verificar_password,
    es_texto_plano,
)
from database import get_db
from refresh_tokens import (
    ahora_utc,
    buscar_refresh_token,
    emitir_refresh_token,
    reutilizar_en_gracia,
    revocar_familia_refresh,
    rotar_refresh_token,
)


router = APIRouter(prefix="/auth", tags=["Autenticación"])

ROLES_ADMIN = {"ADMINISTRACION", "ADMINISTRADOR", "ADMIN"}


@router.post("/registro", response_model=schemas.UsuarioOut, status_code=status.HTTP_201_CREATED)
def registro(datos: schemas.UsuarioRegistro, db: Session = Depends(get_db)):
    existe = db.query(models.Usuario).filter(models.Usuario.email == datos.email).first()
    if existe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese email",
        )

    nuevo_usuario = models.Usuario(
        nombre=datos.nombre,
        apellido=datos.apellido,
        email=datos.email,
        password_hash=hash_password(datos.password),
        rol="PRACTICANTE",
        activo=True
    )

    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    return nuevo_usuario


@router.post("/login", response_model=schemas.Token)
def login(datos: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(models.Usuario.email == datos.email).first()

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # verificar si está activo
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta está desactivada.",
        )

    # verificar contraseña
    if es_texto_plano(usuario.password_hash):
        if datos.password != usuario.password_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email o contraseña incorrectos",
                headers={"WWW-Authenticate": "Bearer"},
            )
        usuario.password_hash = hash_password(datos.password)
        db.commit()
    else:
        if not verificar_password(datos.password, usuario.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email o contraseña incorrectos",
                headers={"WWW-Authenticate": "Bearer"},
            )

    token = crear_token(
        data={
            "sub": usuario.email,
            "id": usuario.id,
            "rol": usuario.rol,
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    perfil = (
        db.query(PerfilUsuario)
        .filter(PerfilUsuario.usuario_id == usuario.id)
        .first()
    )
    avatar_url = perfil.avatar_url if perfil else None

    # Refresh token opaco: el cliente recibe el texto; en BD solo queda el hash.
    emitido = emitir_refresh_token(
        db,
        usuario.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    refresh_token = emitido[0] if emitido else None
    db.commit()

    return {
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "usuario": {
            "id": usuario.id,
            "nombre": usuario.nombre,
            "apellido": usuario.apellido,
            "email": usuario.email,
            "rol": usuario.rol,
            "avatar_url": avatar_url,
        }
    }

# ── POST /auth/refresh ────────────────────────────────────────────────────────

@router.post("/refresh", response_model=schemas.Token)
def refrescar_token(
    datos: schemas.RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Rota el refresh token y devuelve un access token nuevo.

    - Reutilización dentro de 60 s (respuesta perdida): se restaura y devuelve
      el mismo refresh, sin revocar la familia.
    - Reutilización fuera de la gracia: se revoca la familia completa (401).
    """
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    token_plano = (datos.refresh_token or "").strip()

    fila = buscar_refresh_token(db, token_plano, con_bloqueo=True)
    usuario = (
        db.query(models.Usuario)
        .filter(models.Usuario.id == fila.usuario_id)
        .first()
        if fila is not None
        else None
    )

    if fila is None or usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta está desactivada.",
        )

    ahora = ahora_utc()

    if fila.expira_en <= ahora:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if fila.revocado_en is not None:
        if not reutilizar_en_gracia(db, fila, ahora):
            revocar_familia_refresh(db, fila, ahora)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido o expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )
        nuevo_refresh = token_plano
    else:
        nuevo_refresh = rotar_refresh_token(
            db, fila, ip=ip, user_agent=user_agent, ahora=ahora
        )
        if nuevo_refresh is None:
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido o expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )

    db.commit()

    access_token = crear_token(
        data={
            "sub": usuario.email,
            "id": usuario.id,
            "rol": usuario.rol,
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {
        "access_token": access_token,
        "refresh_token": nuevo_refresh,
        "token_type": "bearer",
    }


@router.get("/me", response_model=schemas.UsuarioOut)
def perfil_actual(usuario: models.Usuario = Depends(get_usuario_actual)):
    return usuario