from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
from security import (
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
    - El rol por defecto es PRACTICANTE
    """
    # Verificar email existente
    existe = db.query(models.Usuario).filter(models.Usuario.email == datos.email).first()
    if existe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese email",
        )

    # Crear usuario con rol PRACTICANTE por defecto
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

# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post("/login", response_model=schemas.Token)
def login(datos: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Autentica al usuario y devuelve un JWT"""
    usuario = db.query(models.Usuario).filter(models.Usuario.email == datos.email).first()

    if not usuario or not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada",
        )

    token = crear_token(
        data={
            "sub": usuario.email,
            "id": usuario.id,
            "rol": usuario.rol,
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": {
            "id": usuario.id,
            "nombre": usuario.nombre,
            "apellido": usuario.apellido,
            "email": usuario.email,
            "rol": usuario.rol
        }
    }

# ── GET /auth/me ──────────────────────────────────────────────────────────────

@router.get("/me", response_model=schemas.UsuarioOut)
def perfil_actual(usuario: models.Usuario = Depends(get_usuario_actual)):
    """Devuelve los datos del usuario autenticado"""
    return usuario