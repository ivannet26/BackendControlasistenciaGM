# routers/usuarios.py
# Módulo de gestión de usuarios: SOLO administradores.

from datetime import datetime
from pathlib import Path
import time
from zoneinfo import ZoneInfo
from typing import List, Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)

import schemas
from auditoria_helper import registrar_auditoria
from database import get_db
from models import Usuario
from perfil_models import PerfilUsuario
from perfil_schemas import CambiarPasswordRequest, PerfilEditar, PerfilOut
from rastreador_models import TiempoRegistro
from routers.perfil import _actualizar_perfil
from security import (
    get_usuario_actual,
    hash_password,
    requiere_admin,
    verificar_password,
)


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
    db.flush()

    registrar_auditoria(
        db=db,
        usuario=admin,
        accion="CREAR",
        entidad="USUARIO",
        entidad_id=usuario.id,
        entidad_nombre=f"{usuario.nombre} {usuario.apellido}",
        detalle=f"Creó al usuario '{usuario.nombre} {usuario.apellido}' con rol {usuario.rol}",
        datos_nuevos={
            "nombre": usuario.nombre,
            "apellido": usuario.apellido,
            "email": usuario.email,
            "rol": usuario.rol,
            "activo": usuario.activo,
        },
    )

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

    if usuario.id == admin.id:
        if cambios.get("activo") is False:
            raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta")
        if "rol" in cambios and cambios["rol"] is not None:
            if _normalizar_rol(cambios["rol"]) not in ROLES_ADMIN:
                raise HTTPException(
                    status_code=400,
                    detail="No puedes quitarte tu propio rol de administrador",
                )

    # Snapshot ANTES
    snapshot_anterior = {
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "email": usuario.email,
        "rol": usuario.rol,
        "activo": usuario.activo,
    }

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

    db.flush()

    registrar_auditoria(
        db=db,
        usuario=admin,
        accion="EDITAR",
        entidad="USUARIO",
        entidad_id=usuario.id,
        entidad_nombre=f"{usuario.nombre} {usuario.apellido}",
        detalle=f"Editó al usuario '{usuario.nombre} {usuario.apellido}'",
        datos_anteriores=snapshot_anterior,
        datos_nuevos={
            "nombre": usuario.nombre,
            "apellido": usuario.apellido,
            "email": usuario.email,
            "rol": usuario.rol,
            "activo": usuario.activo,
        },
    )

    db.commit()
    db.refresh(usuario)

    return usuario


# ============================================================
# DESACTIVAR (BAJA LÓGICA)
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

    # 1. Cerrar timers abiertos del usuario (cierra el rastreador si está corriendo)
    _cerrar_timers_abiertos(db, usuario.id)

    # 2. Marcar como inactivo
    usuario.activo = False

    db.flush()

    registrar_auditoria(
        db=db,
        usuario=admin,
        accion="DESACTIVAR",
        entidad="USUARIO",
        entidad_id=usuario.id,
        entidad_nombre=f"{usuario.nombre} {usuario.apellido}",
        detalle=f"Desactivó al usuario '{usuario.nombre} {usuario.apellido}'",
    )

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
    db.flush()

    registrar_auditoria(
        db=db,
        usuario=admin,
        accion="ACTIVAR",
        entidad="USUARIO",
        entidad_id=usuario.id,
        entidad_nombre=f"{usuario.nombre} {usuario.apellido}",
        detalle=f"Reactivó al usuario '{usuario.nombre} {usuario.apellido}'",
    )

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
        _cerrar_timers_abiertos(db, usuario.id)

        # Auditoría ANTES de borrar
        registrar_auditoria(
            db=db,
            usuario=admin,
            accion="ELIMINAR",
            entidad="USUARIO",
            entidad_id=usuario.id,
            entidad_nombre=f"{usuario.nombre} {usuario.apellido}",
            detalle=f"Eliminó permanentemente al usuario '{usuario.nombre} {usuario.apellido}'",
            datos_anteriores={
                "nombre": usuario.nombre,
                "apellido": usuario.apellido,
                "email": usuario.email,
                "rol": usuario.rol,
            },
        )

        db.delete(usuario)
        db.commit()
    except Exception as e:
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


# ============================================================
# PERFIL DEL USUARIO AUTENTICADO (COMPATIBILIDAD)
# ============================================================

@router.put("/me", response_model=PerfilOut)
def actualizar_mi_perfil_compatibilidad(
    datos: PerfilEditar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return _actualizar_perfil(db, usuario, datos)


@router.put("/me/password")
def cambiar_mi_password(
    datos: CambiarPasswordRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    usuario = (
        db.query(Usuario)
        .filter(Usuario.id == usuario.id)
        .with_for_update()
        .first()
    )
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not verificar_password(datos.password_actual, usuario.password_hash):
        raise HTTPException(
            status_code=400,
            detail="La contraseña actual es incorrecta",
        )

    usuario.password_hash = hash_password(datos.password_nueva)
    db.flush()
    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="CAMBIAR_PASSWORD",
        entidad="USUARIO",
        entidad_id=usuario.id,
        entidad_nombre=f"{usuario.nombre} {usuario.apellido}",
        detalle="Cambió su contraseña",
    )
    db.commit()
    return {"mensaje": "Contraseña actualizada correctamente"}


@router.post("/me/avatar", response_model=dict)
async def subir_avatar(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    usuario = (
        db.query(Usuario)
        .filter(Usuario.id == usuario.id)
        .with_for_update()
        .first()
    )
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    extensiones_permitidas = {"png", "jpg", "jpeg", "webp", "gif"}
    extension = Path(archivo.filename or "").suffix.lower().lstrip(".")
    if not archivo.content_type or not archivo.content_type.lower().startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
    if extension not in extensiones_permitidas:
        raise HTTPException(
            status_code=400,
            detail="Extensión no permitida. Usa png, jpg, jpeg, webp o gif",
        )

    contenido = await archivo.read()
    if len(contenido) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="El avatar no puede superar los 2 MB",
        )

    directorio_avatars = Path(__file__).resolve().parent.parent / "static" / "avatars"
    perfil = (
        db.query(PerfilUsuario)
        .filter(PerfilUsuario.usuario_id == usuario.id)
        .first()
    )
    if perfil is None:
        perfil = PerfilUsuario(usuario_id=usuario.id)
        db.add(perfil)

    avatar_anterior = perfil.avatar_url
    directorio_avatars.mkdir(parents=True, exist_ok=True)
    for archivo_viejo in directorio_avatars.glob(f"usuario_{usuario.id}_*"):
        try:
            archivo_viejo.unlink()
        except OSError as error:
            print(f"No se pudo borrar {archivo_viejo}: {error}")

    # Elimina también los avatares con el formato anterior, sin timestamp.
    for archivo_viejo in directorio_avatars.glob(f"usuario_{usuario.id}.*"):
        try:
            archivo_viejo.unlink()
        except OSError as error:
            print(f"No se pudo borrar {archivo_viejo}: {error}")

    timestamp = int(time.time() * 1000)
    nombre_unico = f"usuario_{usuario.id}_{timestamp}.{extension}"
    ruta_archivo = directorio_avatars / nombre_unico

    archivo_iniciado = False
    try:
        archivo_iniciado = True
        with open(ruta_archivo, "wb") as archivo_destino:
            archivo_destino.write(contenido)
        if not ruta_archivo.is_file() or ruta_archivo.stat().st_size != len(contenido):
            raise OSError("No se pudo verificar el archivo guardado")
    except OSError as error:
        if archivo_iniciado:
            try:
                ruta_archivo.unlink()
            except FileNotFoundError:
                pass
        raise HTTPException(
            status_code=500,
            detail="No se pudo guardar el archivo del avatar",
        ) from error

    avatar_url = f"/static/avatars/{nombre_unico}"
    perfil.avatar_url = avatar_url
    try:
        db.flush()
        registrar_auditoria(
            db=db,
            usuario=usuario,
            accion="ACTUALIZAR_AVATAR",
            entidad="PERFIL",
            entidad_id=usuario.id,
            entidad_nombre=f"{usuario.nombre} {usuario.apellido}",
            detalle=f"Actualizó su avatar a {avatar_url}",
            datos_anteriores={"avatar_url": avatar_anterior},
            datos_nuevos={"avatar_url": avatar_url},
        )
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        try:
            ruta_archivo.unlink()
        except FileNotFoundError:
            pass
        raise HTTPException(
            status_code=500,
            detail="No se pudo actualizar el avatar en la base de datos",
        ) from error

    return {
        "ok": True,
        "avatar_url": avatar_url,
        "mensaje": "Avatar actualizado correctamente",
    }