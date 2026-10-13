from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from auditoria_helper import registrar_auditoria
from database import get_db
from models import Usuario
from perfil_models import PerfilUsuario
from perfil_schemas import PerfilEditar, PerfilOut
from security import get_usuario_actual


router = APIRouter(prefix="/perfil", tags=["Perfil"])


def _obtener_o_crear_perfil(db: Session, usuario: Usuario) -> PerfilUsuario:
    perfil = (
        db.query(PerfilUsuario)
        .filter(PerfilUsuario.usuario_id == usuario.id)
        .first()
    )
    if perfil is None:
        perfil = PerfilUsuario(usuario_id=usuario.id)
        db.add(perfil)
        db.flush()
    return perfil


def _serializar_perfil(usuario: Usuario, perfil: PerfilUsuario) -> Dict[str, Any]:
    return {
        "usuario_id": usuario.id,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "email": usuario.email,
        "rol": usuario.rol or "",
        "telefono": perfil.telefono,
        "dni": perfil.dni,
        "direccion": perfil.direccion,
        "fecha_nacimiento": perfil.fecha_nacimiento,
        "puesto": perfil.puesto,
        "avatar_url": perfil.avatar_url,
    }


@router.get("/mi-perfil", response_model=PerfilOut)
def obtener_mi_perfil(
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
    perfil = _obtener_o_crear_perfil(db, usuario)
    db.commit()
    db.refresh(perfil)
    return _serializar_perfil(usuario, perfil)


@router.put("/mi-perfil", response_model=PerfilOut)
def actualizar_mi_perfil(
    datos: PerfilEditar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return _actualizar_perfil(db, usuario, datos)


def _actualizar_perfil(
    db: Session, usuario: Usuario, datos: PerfilEditar
) -> Dict[str, Any]:
    cambios = datos.model_dump(exclude_unset=True)
    usuario = (
        db.query(Usuario)
        .filter(Usuario.id == usuario.id)
        .with_for_update()
        .first()
    )
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    perfil = _obtener_o_crear_perfil(db, usuario)
    valores_anteriores = _serializar_perfil(usuario, perfil)

    for campo in ("nombre", "apellido"):
        if campo in cambios:
            valor = cambios.pop(campo)
            if valor is None or len(valor.strip()) < 2:
                raise HTTPException(
                    status_code=400,
                    detail=f"El campo {campo} debe tener al menos 2 caracteres",
                )
            setattr(usuario, campo, valor.strip())

    if "email" in cambios:
        email = cambios.pop("email")
        if email is None:
            raise HTTPException(
                status_code=400,
                detail="El email no puede estar vacío",
            )
        email = str(email).strip()
        if email.lower() != usuario.email.lower():
            email_en_uso = (
                db.query(Usuario.id)
                .filter(
                    func.lower(Usuario.email) == email.lower(),
                    Usuario.id != usuario.id,
                )
                .first()
            )
            if email_en_uso:
                raise HTTPException(
                    status_code=400,
                    detail="Ya existe un usuario con ese email",
                )
            usuario.email = email

    for campo, valor in cambios.items():
        setattr(perfil, campo, valor)

    db.flush()
    valores_nuevos = _serializar_perfil(usuario, perfil)
    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="EDITAR",
        entidad="PERFIL",
        entidad_id=usuario.id,
        entidad_nombre=f"{usuario.nombre} {usuario.apellido}",
        detalle="Actualizó su perfil",
        datos_anteriores=valores_anteriores,
        datos_nuevos=valores_nuevos,
    )
    db.commit()
    db.refresh(usuario)
    db.refresh(perfil)
    return _serializar_perfil(usuario, perfil)
