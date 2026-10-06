from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import Usuario
from equipo_models import Etiqueta
from equipo_schemas import EtiquetaCrear, EtiquetaEditar, EtiquetaOut
from security import get_usuario_actual, requiere_admin
from auditoria_helper import registrar_auditoria

router = APIRouter(prefix="/etiquetas", tags=["Etiquetas"])


def _obtener_etiqueta_o_404(db: Session, etiqueta_id: int) -> Etiqueta:
    etiqueta = db.query(Etiqueta).filter(Etiqueta.id == etiqueta_id).first()
    if not etiqueta:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada")
    return etiqueta


def _snapshot_etiqueta(etiqueta: Etiqueta) -> dict:
    return {
        "nombre": etiqueta.nombre,
        "color": etiqueta.color,
        "archivado": etiqueta.archivado,
    }


# ════════════════════════════════════════════════════════════════════════════════
# LISTAR (cualquier usuario logueado)
# ════════════════════════════════════════════════════════════════════════════════

@router.get("", response_model=List[EtiquetaOut])
def listar_etiquetas(
    estado: Optional[str] = Query(None),
    nombre: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    query = db.query(Etiqueta)

    if estado is None or estado.lower() == "activo":
        query = query.filter(Etiqueta.archivado == False)
    elif estado.lower() == "archivado":
        query = query.filter(Etiqueta.archivado == True)

    if nombre:
        query = query.filter(Etiqueta.nombre.ilike(f"%{nombre}%"))

    return query.order_by(Etiqueta.nombre.asc()).all()


# ════════════════════════════════════════════════════════════════════════════════
# OBTENER UNA (cualquier usuario logueado)
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/{etiqueta_id}", response_model=EtiquetaOut)
def obtener_etiqueta(
    etiqueta_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    return _obtener_etiqueta_o_404(db, etiqueta_id)


# ════════════════════════════════════════════════════════════════════════════════
# CREAR (solo admin)
# ════════════════════════════════════════════════════════════════════════════════

@router.post("", response_model=EtiquetaOut, status_code=status.HTTP_201_CREATED)
def crear_etiqueta(
    datos: EtiquetaCrear,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):
    existe = db.query(Etiqueta).filter(Etiqueta.nombre.ilike(datos.nombre)).first()
    if existe:
        raise HTTPException(
            status_code=400,
            detail="Ya existe una etiqueta con ese nombre",
        )

    nueva = Etiqueta(
        nombre=datos.nombre,
        color=datos.color,
        archivado=False,
    )
    db.add(nueva)
    db.flush()

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="CREAR",
        entidad="ETIQUETA",
        entidad_id=nueva.id,
        entidad_nombre=nueva.nombre,
        detalle=f"Creó la etiqueta '{nueva.nombre}'",
        datos_nuevos=_snapshot_etiqueta(nueva),
    )

    db.commit()
    db.refresh(nueva)
    return nueva


# ════════════════════════════════════════════════════════════════════════════════
# EDITAR (solo admin)
# ════════════════════════════════════════════════════════════════════════════════

@router.put("/{etiqueta_id}", response_model=EtiquetaOut)
def editar_etiqueta(
    etiqueta_id: int,
    datos: EtiquetaEditar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):
    etiqueta = _obtener_etiqueta_o_404(db, etiqueta_id)

    snapshot_anterior = _snapshot_etiqueta(etiqueta)

    if datos.nombre is not None:
        duplicado = (
            db.query(Etiqueta)
            .filter(Etiqueta.nombre.ilike(datos.nombre), Etiqueta.id != etiqueta_id)
            .first()
        )
        if duplicado:
            raise HTTPException(
                status_code=400,
                detail="Ese nombre ya está en uso",
            )
        etiqueta.nombre = datos.nombre

    if datos.color is not None:
        etiqueta.color = datos.color

    db.flush()

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="EDITAR",
        entidad="ETIQUETA",
        entidad_id=etiqueta.id,
        entidad_nombre=etiqueta.nombre,
        detalle=f"Editó la etiqueta '{etiqueta.nombre}'",
        datos_anteriores=snapshot_anterior,
        datos_nuevos=_snapshot_etiqueta(etiqueta),
    )

    db.commit()
    db.refresh(etiqueta)
    return etiqueta


# ════════════════════════════════════════════════════════════════════════════════
# ARCHIVAR / DESARCHIVAR (solo admin)
# ════════════════════════════════════════════════════════════════════════════════

@router.patch("/{etiqueta_id}/archivar", response_model=EtiquetaOut)
def archivar_etiqueta(
    etiqueta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):
    etiqueta = _obtener_etiqueta_o_404(db, etiqueta_id)
    if etiqueta.archivado:
        raise HTTPException(status_code=400, detail="La etiqueta ya está archivada")

    snapshot_anterior = _snapshot_etiqueta(etiqueta)
    etiqueta.archivado = True
    db.flush()

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="ARCHIVAR",
        entidad="ETIQUETA",
        entidad_id=etiqueta.id,
        entidad_nombre=etiqueta.nombre,
        detalle=f"Archivó la etiqueta '{etiqueta.nombre}'",
        datos_anteriores=snapshot_anterior,
        datos_nuevos=_snapshot_etiqueta(etiqueta),
    )

    db.commit()
    db.refresh(etiqueta)
    return etiqueta


@router.patch("/{etiqueta_id}/desarchivar", response_model=EtiquetaOut)
def desarchivar_etiqueta(
    etiqueta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):
    etiqueta = _obtener_etiqueta_o_404(db, etiqueta_id)
    if not etiqueta.archivado:
        raise HTTPException(status_code=400, detail="La etiqueta ya está activa")

    snapshot_anterior = _snapshot_etiqueta(etiqueta)
    etiqueta.archivado = False
    db.flush()

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="DESARCHIVAR",
        entidad="ETIQUETA",
        entidad_id=etiqueta.id,
        entidad_nombre=etiqueta.nombre,
        detalle=f"Desarchivó la etiqueta '{etiqueta.nombre}'",
        datos_anteriores=snapshot_anterior,
        datos_nuevos=_snapshot_etiqueta(etiqueta),
    )

    db.commit()
    db.refresh(etiqueta)
    return etiqueta


# ════════════════════════════════════════════════════════════════════════════════
# ELIMINAR (solo admin)
# ════════════════════════════════════════════════════════════════════════════════

@router.delete("/{etiqueta_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_etiqueta(
    etiqueta_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):
    etiqueta = _obtener_etiqueta_o_404(db, etiqueta_id)
    if not etiqueta.archivado:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden eliminar etiquetas que estén archivadas primero",
        )

    snapshot_anterior = _snapshot_etiqueta(etiqueta)
    nombre = etiqueta.nombre

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="ELIMINAR",
        entidad="ETIQUETA",
        entidad_id=etiqueta.id,
        entidad_nombre=nombre,
        detalle=f"Eliminó permanentemente la etiqueta '{nombre}'",
        datos_anteriores=snapshot_anterior,
    )

    db.delete(etiqueta)
    db.commit()