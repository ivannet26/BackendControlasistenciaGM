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

router = APIRouter(prefix="/equipo", tags=["Equipo"])


# ── Función auxiliar para construir MiembroOut ────────────────────────────────

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
    """Devuelve todos los grupos existentes."""
    return db.query(Grupo).order_by(Grupo.nombre).all()


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
    Solo un ADMINISTRACION puede agregar miembros.
    """
    # Verificar que quien hace la petición es ADMINISTRACION
    miembro_actual = (
        db.query(MiembroEquipo)
        .filter(MiembroEquipo.usuario_id == usuario_actual.id)
        .first()
    )
    es_admin = miembro_actual and miembro_actual.tipo_usuario.upper() == "ADMINISTRACION"
    if not es_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un usuario con tipo ADMINISTRACION puede agregar miembros al equipo",
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
        miembro_actual = (
            db.query(MiembroEquipo)
            .filter(MiembroEquipo.usuario_id == usuario_actual.id)
            .first()
        )
        es_admin = miembro_actual and miembro_actual.tipo_usuario.upper() == "ADMINISTRACION"
        if not es_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo un usuario con tipo ADMINISTRACION puede cambiar el tipo, estado o grupo de un miembro",
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
    Solo un ADMINISTRACION puede eliminar miembros.
    """
    # Verificar que quien hace la petición es ADMINISTRACION
    miembro_actual = (
        db.query(MiembroEquipo)
        .filter(MiembroEquipo.usuario_id == usuario_actual.id)
        .first()
    )
    es_admin = miembro_actual and miembro_actual.tipo_usuario.upper() == "ADMINISTRACION"
    if not es_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un usuario con tipo ADMINISTRACION puede eliminar miembros del equipo",
        )

    miembro = db.query(MiembroEquipo).filter(MiembroEquipo.id == miembro_id).first()
    if not miembro:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")

    db.delete(miembro)
    db.commit()


# ── Endpoint especial: ver clave temporal en asteriscos ───────────────────────

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
