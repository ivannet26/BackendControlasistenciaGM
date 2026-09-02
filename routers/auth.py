from datetime import timedelta

from fas tapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    crear_token,
    get_usuario_actual,
    hash_password,
    verificar_password,
)
from database import get_db

router = APIRouter(prefix="/auth", tags=["Autenticación"])


# ── POST /auth/registro ───────────────────────────────────────────────────────

@router.post("/registro", response_model=schemas.UsuarioOut, status_code=status.HTTP_201_CREATED)
def registro(datos: schemas.UsuarioRegistro, db: Session = Depends(get_db)):
    """
    Registra un nuevo usuario.
    - Verifica que el email no esté en uso
    - Hashea la contraseña antes de guardarla
    - Devuelve el usuario creado (sin password_hash)
    """
    # ¿Ya existe ese email?
    existe = db.query(models.Usuario).filter(models.Usuario.email == datos.email).first()
    if existe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese email",
        )

    # ¿El rol_id enviado existe en la BD?
    rol = db.query(models.Rol).filter(models.Rol.id == datos.rol_id).first()
    if not rol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El rol con id {datos.rol_id} no existe",
        )

    nuevo_usuario = models.Usuario(
        nombre        = datos.nombre,
        apellido      = datos.apellido,
        email         = datos.email,
        password_hash = hash_password(datos.password),  # ← nunca guardamos el texto plano
        rol_id        = datos.rol_id,
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    return nuevo_usuario


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post("/login", response_model=schemas.Token)
def login(datos: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    Autentica al usuario y devuelve un JWT.
    - Busca al usuario por email
    - Verifica la contraseña
    - Genera y devuelve el access_token
    """
    usuario = db.query(models.Usuario).filter(models.Usuario.email == datos.email).first()

    # Mismo mensaje para email incorrecto y password incorrecto
    # (no le decimos al atacante cuál de los dos falló)
    if not usuario or not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada, contacta al administrador",
        )

    token = crear_token(
        data={
            "sub": usuario.email,
            "rol": usuario.rol.nombre,
            "id":  usuario.id,
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {"access_token": token, "token_type": "bearer"}


# ── GET /auth/me ──────────────────────────────────────────────────────────────

@router.get("/me", response_model=schemas.UsuarioOut)
def perfil_actual(usuario: models.Usuario = Depends(get_usuario_actual)):
    """
    Devuelve los datos del usuario dueño del token.
    Endpoint de prueba: si el token es válido, funciona.
    """
    return usuario
