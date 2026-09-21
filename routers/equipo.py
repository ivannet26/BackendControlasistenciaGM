from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import Usuario
from equipo_models import Grupo, MiembroEquipo, Etiqueta
from equipo_schemas import (
    GrupoCrear, GrupoEditar, GrupoOut, GrupoConMiembrosOut,
    MiembroCrear, MiembroEditar, MiembroOut,
)
from security import get_usuario_actual
from datetime import datetime
from zoneinfo import ZoneInfo
from rastreador_models import TiempoRegistro

TZ_PERU = ZoneInfo("America/Lima")
router = APIRouter(prefix="/equipo", tags=["Equipo"])


# ════════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ════════════════════════════════════════════════════════════════════════════════


ROLES_ADMIN = {"ADMINISTRACION", "ADMINISTRADOR", "ADMIN"}


# ════════════════════════════════════════════════════════════════════════════════
# FUNCIÓN AUXILIAR PARA VALIDAR ADMIN
# ════════════════════════════════════════════════════════════════════════════════

def verificar_es_admin(
    db: Session,
    usuario_actual: Usuario,
    mensaje_error: str = "Solo un usuario con tipo ADMINISTRACION puede realizar esta acción"
):
    """
    Verifica si el usuario es admin por dos vías:
    1) Rol global en usuariosPrueba.rol
    2) Tipo en miembro_equipo.tipo_usuario
    """

    # 1) Rol global
    rol_global = (usuario_actual.rol or "").strip().upper()
    es_admin_global = rol_global in ROLES_ADMIN

    # 2) Tipo en la tabla del equipo
    miembro_actual = (
        db.query(MiembroEquipo)
        .filter(MiembroEquipo.usuario_id == usuario_actual.id)
        .first()
    )
    tipo_equipo = (
        (miembro_actual.tipo_usuario or "").strip().upper()
        if miembro_actual else ""
    )
    es_admin_equipo = tipo_equipo in ROLES_ADMIN

    # Permitir si es admin por cualquiera de las dos vías
    if not (es_admin_global or es_admin_equipo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{mensaje_error}. "
                f"Tu rol global es '{rol_global or 'SIN ROL'}' "
                f"y tu tipo de equipo es '{tipo_equipo or 'NO ESTÁS EN EL EQUIPO'}'"
            ),
        )


# ════════════════════════════════════════════════════════════════════════════════
# FUNCIÓN AUXILIAR PARA CONSTRUIR MIEMBROOUT
# ════════════════════════════════════════════════════════════════════════════════

def _construir_miembro_out(miembro: MiembroEquipo) -> dict:
    """Convierte un MiembroEquipo + sus relaciones en el dict de respuesta."""
    tiene_clave = bool(miembro.clave_temp)
    return {
        "id": miembro.id,
        "usuario_id": miembro.usuario_id,
        "nombre_usuario": f"{miembro.usuario.nombre} {miembro.usuario.apellido}",
        "email_usuario": miembro.usuario.email,
        "grupo_id": miembro.grupo_id,
        "nombre_grupo": miembro.grupo.nombre if miembro.grupo else None,
        "tipo_usuario": miembro.tipo_usuario,
        "estado": miembro.estado,
        "tiene_clave_temp": tiene_clave,
        "clave_temp_mascara": "********" if tiene_clave else None,
        "etiquetas": miembro.etiquetas,
        "creado_en": miembro.creado_en,
        "actualizado_en": miembro.actualizado_en,
    }


# ════════════════════════════════════════════════════════════════════════════════
# GRUPOS
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/grupos", response_model=List[GrupoOut])
def listar_grupos(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Devuelve todos los grupos con sus miembros."""

    grupos = db.query(Grupo).order_by(Grupo.nombre).all()

    return [
        {
            "id": g.id,
            "nombre": g.nombre,
            "descripcion": g.descripcion,
            "creado_en": g.creado_en,
            "miembros_count": len(g.miembros),
            "miembros": [
                f"{m.usuario.nombre} {m.usuario.apellido}"
                for m in g.miembros
            ],
        }
        for g in grupos
    ]


@router.get("/grupos/{grupo_id}", response_model=GrupoConMiembrosOut)
def obtener_grupo(
    grupo_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Devuelve un grupo con la lista de nombres de sus miembros."""
    grupo = db.query(Grupo).filter(Grupo.id == grupo_id).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    nombres = [
        f"{m.usuario.nombre} {m.usuario.apellido}"
        for m in grupo.miembros
    ]
    return {
        "id": grupo.id,
        "nombre": grupo.nombre,
        "descripcion": grupo.descripcion,
        "miembros": nombres,
    }


@router.post("/grupos", response_model=GrupoOut, status_code=status.HTTP_201_CREATED)
def crear_grupo(
    datos: GrupoCrear,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Crea un nuevo grupo."""
    existe = db.query(Grupo).filter(Grupo.nombre == datos.nombre).first()
    if existe:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un grupo con ese nombre",
        )
    grupo = Grupo(nombre=datos.nombre, descripcion=datos.descripcion)
    db.add(grupo)
    db.commit()
    db.refresh(grupo)
    return grupo


@router.put("/grupos/{grupo_id}", response_model=GrupoOut)
def editar_grupo(
    grupo_id: int,
    datos: GrupoEditar,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Edita el nombre o descripción de un grupo."""
    grupo = db.query(Grupo).filter(Grupo.id == grupo_id).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    if datos.nombre is not None:
        duplicado = (
            db.query(Grupo)
            .filter(Grupo.nombre == datos.nombre, Grupo.id != grupo_id)
            .first()
        )
        if duplicado:
            raise HTTPException(status_code=400, detail="Ese nombre ya está en uso")
        grupo.nombre = datos.nombre

    if datos.descripcion is not None:
        grupo.descripcion = datos.descripcion

    db.commit()
    db.refresh(grupo)
    return grupo


@router.delete("/grupos/{grupo_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_grupo(
    grupo_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Borra un grupo. Los miembros quedan sin grupo (grupo_id = NULL)."""
    grupo = db.query(Grupo).filter(Grupo.id == grupo_id).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    for miembro in grupo.miembros:
        miembro.grupo_id = None

    db.delete(grupo)
    db.commit()


# ════════════════════════════════════════════════════════════════════════════════
# MIEMBROS
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/miembros", response_model=List[MiembroOut])
def listar_miembros(
    estado: Optional[str] = Query(None, description="ACTIVO, INACTIVO o INVITADO"),
    tipo_usuario: Optional[str] = Query(None, description="MIEMBRO o ADMINISTRACION"),
    grupo_id: Optional[int] = Query(None, description="ID del grupo"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """
    Lista todos los miembros del equipo.
    Se puede filtrar por estado, tipo_usuario y/o grupo_id.
    """
    query = db.query(MiembroEquipo)

    if estado:
        query = query.filter(MiembroEquipo.estado == estado.upper())
    if tipo_usuario:
        query = query.filter(MiembroEquipo.tipo_usuario == tipo_usuario.upper())
    if grupo_id:
        query = query.filter(MiembroEquipo.grupo_id == grupo_id)

    miembros = query.all()
    return [_construir_miembro_out(m) for m in miembros]


@router.get("/miembros/{miembro_id}", response_model=MiembroOut)
def obtener_miembro(
    miembro_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Devuelve el detalle de un miembro por su ID."""
    miembro = db.query(MiembroEquipo).filter(MiembroEquipo.id == miembro_id).first()
    if not miembro:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")
    return _construir_miembro_out(miembro)


@router.post("/miembros", response_model=MiembroOut, status_code=status.HTTP_201_CREATED)
def agregar_miembro(
    datos: MiembroCrear,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual),
):
    """
    Agrega un usuario al equipo.
    Solo un ADMINISTRACION / ADMINISTRADOR / ADMIN puede agregar miembros.
    """

   
    verificar_es_admin(
        db,
        usuario_actual,
        mensaje_error="Solo un usuario con tipo ADMINISTRACION puede agregar miembros al equipo"
    )

    # Verificar que el usuario exista
    usuario = db.query(Usuario).filter(Usuario.id == datos.usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Verificar que el usuario no esté ya en el equipo
    ya_existe = (
        db.query(MiembroEquipo)
        .filter(MiembroEquipo.usuario_id == datos.usuario_id)
        .first()
    )
    if ya_existe:
        raise HTTPException(
            status_code=400,
            detail="El usuario ya es miembro del equipo",
        )

    # Verificar que el grupo exista si se proporcionó
    if datos.grupo_id:
        grupo = db.query(Grupo).filter(Grupo.id == datos.grupo_id).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")

    miembro = MiembroEquipo(
        usuario_id=datos.usuario_id,
        grupo_id=datos.grupo_id,
        tipo_usuario=datos.tipo_usuario.upper(),
        estado=datos.estado.upper(),
        clave_temp=datos.clave_temp,
    )
    db.add(miembro)
    db.commit()
    db.refresh(miembro)
    return _construir_miembro_out(miembro)


@router.put("/miembros/{miembro_id}", response_model=MiembroOut)
def editar_miembro(
    miembro_id: int,
    datos: MiembroEditar,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual),
):
    """
    Edita grupo, tipo_usuario, estado o clave_temp de un miembro.

    Regla de permisos:
    - Cambiar tipo_usuario, estado o grupo_id → requiere ser ADMINISTRACION en el equipo.
    - Cambiar clave_temp → cualquier usuario autenticado puede hacerlo.
    """
    miembro = db.query(MiembroEquipo).filter(MiembroEquipo.id == miembro_id).first()
    if not miembro:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    # ── Verificar si el usuario actual intenta cambiar campos sensibles ────────
    campos_sensibles = (
        datos.tipo_usuario is not None
        or datos.estado is not None
        or datos.grupo_id is not None
    )

    if campos_sensibles:
        verificar_es_admin(
            db,
            usuario_actual,
            mensaje_error="Solo un usuario con tipo ADMINISTRACION puede cambiar el tipo, estado o grupo de un miembro"
        )

    # ── Aplicar cambios ────────────────────────────────────────────────────────
    if datos.grupo_id is not None:
        grupo = db.query(Grupo).filter(Grupo.id == datos.grupo_id).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")
        miembro.grupo_id = datos.grupo_id

    if datos.tipo_usuario is not None:
        miembro.tipo_usuario = datos.tipo_usuario.upper()

    if datos.estado is not None:
        miembro.estado = datos.estado.upper()

    if datos.clave_temp is not None:
        miembro.clave_temp = datos.clave_temp

    db.commit()
    db.refresh(miembro)
    return _construir_miembro_out(miembro)


@router.delete("/miembros/{miembro_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_miembro(
    miembro_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual),
):
    """
    Elimina a un miembro del equipo.
    Solo un ADMINISTRACION / ADMINISTRADOR / ADMIN puede eliminar miembros.
    """

    
    verificar_es_admin(
        db,
        usuario_actual,
        mensaje_error="Solo un usuario con tipo ADMINISTRACION puede eliminar miembros del equipo"
    )

    miembro = db.query(MiembroEquipo).filter(MiembroEquipo.id == miembro_id).first()
    if not miembro:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    db.delete(miembro)
    db.commit()


# ════════════════════════════════════════════════════════════════════════════════
# ENDPOINT ESPECIAL: VER CLAVE TEMPORAL EN ASTERISCOS
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/miembros/{miembro_id}/clave", response_model=dict)
def ver_clave_miembro(
    miembro_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """
    Muestra si el miembro tiene clave temporal asignada.
    Devuelve la clave enmascarada (asteriscos), NUNCA la clave real.
    """
    miembro = db.query(MiembroEquipo).filter(MiembroEquipo.id == miembro_id).first()
    if not miembro:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    if not miembro.clave_temp:
        return {"tiene_clave_temp": False, "clave_temp_mascara": None}

    return {
        "tiene_clave_temp": True,
        "clave_temp_mascara": "*" * len(miembro.clave_temp),
    }


# ════════════════════════════════════════════════════════════════════════════════
# ETIQUETAS DE MIEMBROS
# ════════════════════════════════════════════════════════════════════════════════

@router.post("/miembros/{miembro_id}/etiquetas/{etiqueta_id}", response_model=MiembroOut, status_code=status.HTTP_200_OK)
def asignar_etiqueta_a_miembro(
    miembro_id: int,
    etiqueta_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Asocia una etiqueta a un miembro del equipo."""
    miembro = db.query(MiembroEquipo).filter(MiembroEquipo.id == miembro_id).first()
    if not miembro:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    etiqueta = db.query(Etiqueta).filter(Etiqueta.id == etiqueta_id).first()
    if not etiqueta:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada")

    if etiqueta.archivado:
        raise HTTPException(
            status_code=400,
            detail="No se puede asignar una etiqueta que está archivada",
        )

    if etiqueta in miembro.etiquetas:
        raise HTTPException(
            status_code=400,
            detail="El miembro ya tiene asignada esta etiqueta",
        )

    miembro.etiquetas.append(etiqueta)
    db.commit()
    db.refresh(miembro)
    return _construir_miembro_out(miembro)


@router.delete("/miembros/{miembro_id}/etiquetas/{etiqueta_id}", response_model=MiembroOut, status_code=status.HTTP_200_OK)
def desasignar_etiqueta_de_miembro(
    miembro_id: int,
    etiqueta_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Quita una etiqueta asignada a un miembro del equipo."""
    miembro = db.query(MiembroEquipo).filter(MiembroEquipo.id == miembro_id).first()
    if not miembro:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    etiqueta = db.query(Etiqueta).filter(Etiqueta.id == etiqueta_id).first()
    if not etiqueta:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada")

    if etiqueta not in miembro.etiquetas:
        raise HTTPException(
            status_code=400,
            detail="El miembro no tiene asignada esta etiqueta",
        )

    miembro.etiquetas.remove(etiqueta)
    db.commit()
    db.refresh(miembro)
    return _construir_miembro_out(miembro)
# ════════════════════════════════════════════════════════════════════════════════
# DESLOGEO / BLOQUEO FORZADO POR ADMIN
# ════════════════════════════════════════════════════════════════════════════════

@router.post("/miembros/{usuario_id}/deslogear", status_code=status.HTTP_200_OK)
def deslogear_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual),
):
    """
    Fuerza el cierre de sesión de un usuario:
    - Marca la cuenta como inactiva (activo = False)
    - Cierra todos los registros de tiempo ABIERTOS (fin = None)
    """
    verificar_es_admin(
        db,
        usuario_actual,
        mensaje_error="Solo un usuario con tipo ADMINISTRACION puede deslogear a otros usuarios"
    )

    if usuario_id == usuario_actual.id:
        raise HTTPException(
            status_code=400,
            detail="No puedes deslogearte a ti mismo desde aquí."
        )

    usuario_objetivo = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario_objetivo:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # 1. Desactivar la cuenta
    usuario_objetivo.activo = False

    # 2. Cerrar todos los TiempoRegistro abiertos
    ahora = datetime.now(TZ_PERU)

    registros_abiertos = (
        db.query(TiempoRegistro)
        .filter(
            TiempoRegistro.usuario_id == usuario_id,
            TiempoRegistro.fin.is_(None)
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
                0
            )

    db.commit()

    return {
        "ok": True,
        "mensaje": f"{usuario_objetivo.nombre} {usuario_objetivo.apellido} ha sido desconectado",
        "registros_cerrados": len(registros_abiertos)
    }


@router.post("/miembros/{usuario_id}/reactivar", status_code=status.HTTP_200_OK)
def reactivar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual),
):
    """
    Reactiva la cuenta de un usuario previamente desconectado.
    Solo ADMINISTRACION / ADMINISTRADOR / ADMIN puede hacerlo.
    """
    verificar_es_admin(
        db,
        usuario_actual,
        mensaje_error="Solo un usuario con tipo ADMINISTRACION puede reactivar usuarios"
    )

    usuario_objetivo = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario_objetivo:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    usuario_objetivo.activo = True
    db.commit()

    return {
        "ok": True,
        "mensaje": f"El usuario {usuario_objetivo.nombre} {usuario_objetivo.apellido} ha sido reactivado"
    }
@router.post("/miembros/{usuario_id}/reactivar", status_code=status.HTTP_200_OK)
def reactivar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual),
):
    """Reactiva la cuenta de un usuario previamente desconectado."""
    verificar_es_admin(
        db,
        usuario_actual,
        mensaje_error="Solo ADMINISTRACION puede reactivar usuarios"
    )

    usuario_objetivo = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario_objetivo:
        raise HTTPException(404, "Usuario no encontrado")

    usuario_objetivo.activo = True
    db.commit()

    return {
        "ok": True,
        "mensaje": f"{usuario_objetivo.nombre} {usuario_objetivo.apellido} ha sido reactivado"
    }