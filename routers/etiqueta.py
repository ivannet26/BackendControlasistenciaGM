from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import Usuario
from equipo_models import Etiqueta
from equipo_schemas import EtiquetaCrear, EtiquetaEditar, EtiquetaOut
from security import get_usuario_actual

router = APIRouter(prefix="/etiquetas", tags=["Etiquetas"])


# ── Función auxiliar ──────────────────────────────────────────────────────────

def _obtener_etiqueta_o_404(db: Session, etiqueta_id: int) -> Etiqueta:
    etiqueta = db.query(Etiqueta).filter(Etiqueta.id == etiqueta_id).first()
    if not etiqueta:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada")
    return etiqueta


# ════════════════════════════════════════════════════════════════════════════════
# LISTAR
# ════════════════════════════════════════════════════════════════════════════════

@router.get("", response_model=List[EtiquetaOut])
def listar_etiquetas(
    estado: Optional[str] = Query(
        None,
        description="Filtro: 'activo', 'archivado' o 'todo'. Por defecto devuelve activas.",
    ),
    nombre: Optional[str] = Query(None, description="Buscar por nombre (parcial)"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """
    Lista etiquetas con filtros
    - estado=activo → solo no archivadas (default)
    - estado=archivado → solo archivadas
    - estado=todo → todas
    - nombre → búsqueda parcial por nombre
    """
    query = db.query(Etiqueta)

    if estado is None or estado.lower() == "activo":
        query = query.filter(Etiqueta.archivado == False)
    elif estado.lower() == "archivado":
        query = query.filter(Etiqueta.archivado == True)

    if nombre:
        query = query.filter(Etiqueta.nombre.ilike(f"%{nombre}%"))

    return query.order_by(Etiqueta.nombre.asc()).all()


# ════════════════════════════════════════════════════════════════════════════════
# OBTENER UNA
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/{etiqueta_id}", response_model=EtiquetaOut)
def obtener_etiqueta(
    etiqueta_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Devuelve el detalle de una etiqueta por su ID"""
    return _obtener_etiqueta_o_404(db, etiqueta_id)


# ════════════════════════════════════════════════════════════════════════════════
# CREAR
# ════════════════════════════════════════════════════════════════════════════════

@router.post("", response_model=EtiquetaOut, status_code=status.HTTP_201_CREATED)
def crear_etiqueta(
    datos: EtiquetaCrear,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Crea una nueva etiqueta validando que el nombre no esté duplicado"""
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
    db.commit()
    db.refresh(nueva)
    return nueva


# ════════════════════════════════════════════════════════════════════════════════
# EDITAR
# ════════════════════════════════════════════════════════════════════════════════

@router.put("/{etiqueta_id}", response_model=EtiquetaOut)
def editar_etiqueta(
    etiqueta_id: int,
    datos: EtiquetaEditar,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Edita el nombre o el color de una etiqueta"""
    etiqueta = _obtener_etiqueta_o_404(db, etiqueta_id)

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

    db.commit()
    db.refresh(etiqueta)
    return etiqueta


# ════════════════════════════════════════════════════════════════════════════════
# ARCHIVAR / DESARCHIVAR
# ════════════════════════════════════════════════════════════════════════════════

@router.patch("/{etiqueta_id}/archivar", response_model=EtiquetaOut)
def archivar_etiqueta(
    etiqueta_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Archiva una etiqueta activa"""
    etiqueta = _obtener_etiqueta_o_404(db, etiqueta_id)
    if etiqueta.archivado:
        raise HTTPException(status_code=400, detail="La etiqueta ya está archivada")

    etiqueta.archivado = True
    db.commit()
    db.refresh(etiqueta)
    return etiqueta


@router.patch("/{etiqueta_id}/desarchivar", response_model=EtiquetaOut)
def desarchivar_etiqueta(
    etiqueta_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Reactiva una etiqueta archivada"""
    etiqueta = _obtener_etiqueta_o_404(db, etiqueta_id)
    if not etiqueta.archivado:
        raise HTTPException(status_code=400, detail="La etiqueta ya está activa")

    etiqueta.archivado = False
    db.commit()
    db.refresh(etiqueta)
    return etiqueta


# ════════════════════════════════════════════════════════════════════════════════
# ELIMINAR
# ════════════════════════════════════════════════════════════════════════════════

@router.delete("/{etiqueta_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_etiqueta(
    etiqueta_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Elimina permanentemente una etiqueta (solo si está archivada)"""
    etiqueta = _obtener_etiqueta_o_404(db, etiqueta_id)
    if not etiqueta.archivado:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden eliminar etiquetas que estén archivadas primero",
        )

    db.delete(etiqueta)
    db.commit()