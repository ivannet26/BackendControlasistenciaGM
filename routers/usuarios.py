# routers/usuarios.py
# Módulo de gestión de usuarios: SOLO administradores.

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Query, status

import schemas
from database import get_db
from models import Usuario
from rastreador_models import TiempoRegistro
from security import hash_password, requiere_admin


TZ_PERU = ZoneInfo("America/Lima")

router = APIRouter(
    prefix="/usuarios",
    tags=["Usuarios"],
)

ROLES_VALIDOS = {
    "PRACTICANTE",
    "ADMINISTRADOR",
    "ADMINISTRACION",
}

# ADMINISTRADOR y ADMINISTRACION tienen los mismos permisos
ROLES_ADMIN = {"ADMINISTRADOR", "ADMINISTRACION"}

ROL_POR_DEFECTO = "PRACTICANTE"


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def _normalizar_rol(rol: str) -> str:
    rol = rol.strip().upper()
    if rol not in ROLES_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Rol inválido. Roles permitidos: {', '.join(sorted(ROLES_VALIDOS))}",
        )
    return rol


def _obtener_usuario_o_404(db: Session, usuario_id: int) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


def _email_en_uso(db, email, excluir_id=None):
    query = db.query(Usuario).filter(func.lower(Usuario.email) == email.lower())
    if excluir_id is not None:
        query = query.filter(Usuario.id != excluir_id)
    return query.first() is not None


def _cerrar_timers_abiertos(db: Session, usuario_id: int) -> int:
    """
    Cierra todos los TiempoRegistro abiertos (fin IS NULL) del usuario.
    Devuelve cuántos registros cerró.
    """
    ahora = datetime.now(TZ_PERU)

    registros_abiertos = (
        db.query(TiempoRegistro)
        .filter(
            TiempoRegistro.usuario_id == usuario_id,
            TiempoRegistro.fin.is_(None),
        )
        .all()
    )

    for r in registros_abiertos:
        if r.inicio:
            inicio = r.inicio
            if inicio.tzinfo is None:
                inicio = inicio.replace(tzinfo=TZ_PERU)

            r.fin = ahora
            r.duracion_segundos = max(
                int((ahora - inicio).total_seconds()),
                0,
            )

    return len(registros_abiertos)


# ============================================================
# LISTAR USUARIOS
# ============================================================

@router.get("", response_model=List[schemas.UsuarioOut])
def listar_usuarios(
    activo: Optional[bool] = Query(None, description="Filtrar por activos/inactivos"),
    rol: Optional[str] = Query(None, description="Filtrar por rol"),
    buscar: Optional[str] = Query(None, description="Buscar por nombre, apellido o email"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    query = db.query(Usuario)

    if activo is not None:
        query = query.filter(Usuario.activo == activo)

    if rol:
        query = query.filter(Usuario.rol == rol.strip().upper())

    if buscar:
        patron = f"%{buscar}%"
        query = query.filter(
            or_(
                Usuario.nombre.ilike(patron),
                Usuario.apellido.ilike(patron),
                Usuario.email.ilike(patron),
            )
        )

    # Los más nuevos primero
    return query.order_by(Usuario.id.desc()).all()


# ============================================================
# OBTENER UN USUARIO
# ============================================================

@router.get("/{usuario_id}", response_model=schemas.UsuarioOut)
def obtener_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    return _obtener_usuario_o_404(db, usuario_id)


# ============================================================
# CREAR USUARIO (ALTA)
# ============================================================

@router.post(
    "",
    response_model=schemas.UsuarioOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_usuario(
    datos: schemas.UsuarioCrear,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    if _email_en_uso(db, datos.email):
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")

    usuario = Usuario(
        nombre=datos.nombre.strip(),
        apellido=datos.apellido.strip(),
        email=datos.email.lower(),
        password_hash=hash_password(datos.password),
        rol=_normalizar_rol(datos.rol),
        activo=True,
    )

    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    return usuario


# ============================================================
# EDITAR USUARIO
# ============================================================

@router.put("/{usuario_id}", response_model=schemas.UsuarioOut)
def editar_usuario(
    usuario_id: int,
    datos: schemas.UsuarioEditar,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    usuario = _obtener_usuario_o_404(db, usuario_id)
    cambios = datos.model_dump(exclude_unset=True)

    # Un admin no puede quitarse a sí mismo el acceso o el rol
    if usuario.id == admin.id:
        if cambios.get("activo") is False:
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")
        if "rol" in cambios and cambios["rol"] is not None:
            if _normalizar_rol(cambios["rol"]) not in ROLES_ADMIN:
                raise HTTPException(
                    status_code=400,
                    detail="No puedes quitarte tu propio rol de administrador",
                )

    if cambios.get("email") is not None:
        if _email_en_uso(db, cambios["email"], excluir_id=usuario.id):
            raise HTTPException(status_code=400, detail="Ya existe otro usuario con ese email")
        usuario.email = cambios["email"].lower()

    if cambios.get("nombre") is not None:
        usuario.nombre = cambios["nombre"].strip()

    if cambios.get("apellido") is not None:
        usuario.apellido = cambios["apellido"].strip()

    if cambios.get("rol") is not None:
        usuario.rol = _normalizar_rol(cambios["rol"])

    if cambios.get("activo") is not None:
        usuario.activo = cambios["activo"]

    if cambios.get("password"):
        usuario.password_hash = hash_password(cambios["password"])

    db.commit()
    db.refresh(usuario)

    return usuario


# ============================================================
# DESACTIVAR (BAJA LÓGICA) - cierra rastreador y bloquea sesión
# ============================================================

@router.patch("/{usuario_id}/desactivar", response_model=schemas.UsuarioOut)
def desactivar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    usuario = _obtener_usuario_o_404(db, usuario_id)

    if usuario.id == admin.id:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")

    if not usuario.activo:
        raise HTTPException(status_code=400, detail="El usuario ya está desactivado")

    # 1. Cerrar todos los timers abiertos (igual que el /deslogear del panel)
    _cerrar_timers_abiertos(db, usuario.id)

    # 2. Marcar como inactivo
    usuario.activo = False

    db.commit()
    db.refresh(usuario)

    return usuario


# ============================================================
# ACTIVAR (REACTIVAR CUENTA)
# ============================================================

@router.patch("/{usuario_id}/activar", response_model=schemas.UsuarioOut)
def activar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    usuario = _obtener_usuario_o_404(db, usuario_id)

    if usuario.activo:
        raise HTTPException(status_code=400, detail="El usuario ya está activo")

    usuario.activo = True
    db.commit()
    db.refresh(usuario)

    return usuario


# ============================================================
# ELIMINAR USUARIO (PERMANENTE)
# ============================================================

@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    usuario = _obtener_usuario_o_404(db, usuario_id)

    if usuario.id == admin.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta")

    try:
        # Cerrar timers abiertos antes de borrar
        _cerrar_timers_abiertos(db, usuario.id)

        db.delete(usuario)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "No se puede eliminar este usuario porque tiene registros "
                "asociados (tareas, proyectos, enlaces...). "
                "Considera desactivarlo en su lugar."
            ),
        )

    return None