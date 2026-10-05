import uuid
from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import models
import schemas
from security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    crear_token,
    get_sesion_actual,
    get_usuario_actual,
    hash_password,
    verificar_password,
    es_texto_plano,
)
from database import get_db
from sesion_models import SesionUsuario
from sesion_schemas import SesionOut
from sesiones import (
    MAX_SESIONES_ACTIVAS,
    ahora_utc,
    crear_sesion,
    revocar_sesion,
    revocar_todas,
)


router = APIRouter(prefix="/auth", tags=["Autenticación"])

ROLES_ADMIN = {"ADMINISTRACION", "ADMINISTRADOR", "ADMIN"}

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

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Migración gradual: si la contraseña está en texto plano,
    # verificamos directo y aprovechamos para hashearla
    if es_texto_plano(usuario.password_hash):
        if datos.password != usuario.password_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email o contraseña incorrectos",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Migrar a bcrypt en este mismo login
        usuario.password_hash = hash_password(datos.password)
        db.commit()
    else:
        if not verificar_password(datos.password, usuario.password_hash):
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


# ── GET /auth/usuarios ────────────────────────────────────────────────────────

@router.get("/usuarios", response_model=List[schemas.UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual),
):
    rol = (usuario_actual.rol or "").strip().upper()
    if rol not in ROLES_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los administradores pueden listar usuarios",
        )
    return db.query(models.Usuario).order_by(models.Usuario.id.asc()).all()

# ── PUT /auth/usuarios/{id} ───────────────────────────────────────────────────

@router.put("/usuarios/{usuario_id}", response_model=schemas.UsuarioOut)
def editar_usuario(
    usuario_id: int,
    datos: schemas.UsuarioEditar,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual),
):
    rol = (usuario_actual.rol or "").strip().upper()
    es_admin = rol in ROLES_ADMIN

    if not es_admin and usuario_actual.id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para editar este usuario",
        )

    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if datos.email is not None and datos.email != usuario.email:
        existe = db.query(models.Usuario).filter(
            models.Usuario.email == datos.email,
            models.Usuario.id != usuario_id,
        ).first()
        if existe:
            raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")
        usuario.email = datos.email

    if datos.nombre is not None:
        usuario.nombre = datos.nombre
    if datos.apellido is not None:
        usuario.apellido = datos.apellido
    if datos.password is not None:
        usuario.password_hash = hash_password(datos.password)

    db.commit()
    db.refresh(usuario)
    return usuario

# ── PATCH /auth/usuarios/{id}/desactivar ─────────────────────────────────────

@router.patch("/usuarios/{usuario_id}/desactivar", response_model=schemas.UsuarioOut)
def desactivar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual),
):
    rol = (usuario_actual.rol or "").strip().upper()
    if rol not in ROLES_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los administradores pueden desactivar usuarios",
        )
    if usuario_actual.id == usuario_id:
        raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo")

    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not usuario.activo:
        raise HTTPException(status_code=400, detail="El usuario ya está desactivado")

    usuario.activo = False
    db.commit()
    db.refresh(usuario)
    return usuario

# ── PATCH /auth/usuarios/{id}/activar ────────────────────────────────────────

@router.patch("/usuarios/{usuario_id}/activar", response_model=schemas.UsuarioOut)
def activar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual),
):
    rol = (usuario_actual.rol or "").strip().upper()
    if rol not in ROLES_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los administradores pueden activar usuarios",
        )

    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if usuario.activo:
        raise HTTPException(status_code=400, detail="El usuario ya está activo")

    usuario.activo = True
    db.commit()
    db.refresh(usuario)
    return usuario


# ── POST /auth/usuarios ───────────────────────────────────────────────────────

ROLES_VALIDOS = {"PRACTICANTE", "ADMIN", "ADMINISTRADOR", "ADMINISTRACION", "SUPERVISOR", "SUPERADMIN"}

@router.post(
    "/usuarios",
    response_model=schemas.UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario (solo administradores)",
    description=(
        "Permite a un administrador crear un nuevo usuario con rol personalizable. "
        "Roles disponibles: PRACTICANTE, SUPERVISOR, ADMIN, ADMINISTRADOR, ADMINISTRACION, SUPERADMIN."
    ),
)
def crear_usuario(
    datos: schemas.UsuarioCrear,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(get_usuario_actual),
):
    # Solo admins pueden crear usuarios
    rol_actual = (usuario_actual.rol or "").strip().upper()
    if rol_actual not in ROLES_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los administradores pueden crear usuarios",
        )

    # Validar que el rol enviado sea uno permitido
    rol_nuevo = (datos.rol or "PRACTICANTE").strip().upper()
    if rol_nuevo not in ROLES_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rol inválido. Los roles permitidos son: {', '.join(sorted(ROLES_VALIDOS))}",
        )

    # Verificar que el email no esté en uso
    existe = db.query(models.Usuario).filter(
        models.Usuario.email == datos.email
    ).first()
    if existe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese email",
        )

    nuevo = models.Usuario(
        nombre=datos.nombre.strip(),
        apellido=datos.apellido.strip(),
        email=datos.email,
        password_hash=hash_password(datos.password),
        rol=rol_nuevo,
        activo=True,
    )

    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

