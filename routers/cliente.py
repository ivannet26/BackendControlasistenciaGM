from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import Usuario
from cliente_models import Cliente
from proyecto_models import Proyecto
from cliente_schemas import ClienteCrear, ClienteEditar, ClienteOut
from security import get_usuario_actual, requiere_admin
from auditoria_helper import registrar_auditoria

router = APIRouter(prefix="/clientes", tags=["Clientes"])


def _construir_cliente_out(cliente: Cliente) -> dict:
    cc_raw = cliente.destinatarios_cc or ""
    cc_lista = [c.strip() for c in cc_raw.split(",") if c.strip()]
    return {
        "id": cliente.id,
        "nombre": cliente.nombre,
        "email": cliente.email,
        "destinatarios_cc": cc_lista,
        "direccion": cliente.direccion,
        "nota": cliente.nota,
        "moneda": cliente.moneda,
        "archivado": cliente.archivado,
        "creado_en": cliente.creado_en,
        "actualizado_en": cliente.actualizado_en,
    }


def _snapshot_cliente(cliente: Cliente) -> dict:
    return {
        "nombre": cliente.nombre,
        "email": cliente.email,
        "destinatarios_cc": cliente.destinatarios_cc,
        "direccion": cliente.direccion,
        "nota": cliente.nota,
        "moneda": cliente.moneda,
        "archivado": cliente.archivado,
    }


# ════════════════════════════════════════════════════════════════════════════════
# LISTAR (cualquier usuario logueado)
# ════════════════════════════════════════════════════════════════════════════════

@router.get("", response_model=List[ClienteOut])
def listar_clientes(
    estado: Optional[str] = Query(None),
    nombre: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    query = db.query(Cliente)

    if estado is None or estado.lower() == "activo":
        query = query.filter(Cliente.archivado == False)
    elif estado.lower() == "archivado":
        query = query.filter(Cliente.archivado == True)

    if nombre:
        query = query.filter(Cliente.nombre.ilike(f"%{nombre}%"))

    clientes = query.order_by(Cliente.nombre).all()
    return [_construir_cliente_out(c) for c in clientes]


# ════════════════════════════════════════════════════════════════════════════════
# OBTENER UNO (cualquier usuario logueado)
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/{cliente_id}", response_model=ClienteOut)
def obtener_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return _construir_cliente_out(cliente)


# ════════════════════════════════════════════════════════════════════════════════
# CREAR (solo admin)
# ════════════════════════════════════════════════════════════════════════════════

@router.post("", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def crear_cliente(
    datos: ClienteCrear,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):
    if db.query(Cliente.id).filter(Cliente.nombre == datos.nombre).first():
        raise HTTPException(status_code=409, detail="Ya existe un cliente con ese nombre")

    cc_str = ",".join(datos.destinatarios_cc) if datos.destinatarios_cc else None

    cliente = Cliente(
        nombre=datos.nombre,
        email=datos.email,
        destinatarios_cc=cc_str,
        direccion=datos.direccion,
        nota=datos.nota,
        moneda=datos.moneda.upper(),
    )
    db.add(cliente)
    db.flush()

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="CREAR",
        entidad="CLIENTE",
        entidad_id=cliente.id,
        entidad_nombre=cliente.nombre,
        detalle=f"Creó el cliente '{cliente.nombre}'",
        datos_nuevos=_snapshot_cliente(cliente),
    )

    db.commit()
    db.refresh(cliente)
    return _construir_cliente_out(cliente)


# ════════════════════════════════════════════════════════════════════════════════
# EDITAR (solo admin)
# ════════════════════════════════════════════════════════════════════════════════

@router.put("/{cliente_id}", response_model=ClienteOut)
def editar_cliente(
    cliente_id: int,
    datos: ClienteEditar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    snapshot_anterior = _snapshot_cliente(cliente)

    if datos.nombre is not None and datos.nombre != cliente.nombre:
        duplicado = db.query(Cliente.id).filter(Cliente.nombre == datos.nombre, Cliente.id != cliente_id).first()
        if duplicado:
            raise HTTPException(status_code=409, detail="Ya existe un cliente con ese nombre")
        cliente.nombre = datos.nombre
    if "email" in datos.model_fields_set:
        cliente.email = datos.email
    if datos.destinatarios_cc is not None:
        cliente.destinatarios_cc = ",".join(datos.destinatarios_cc)
    if "direccion" in datos.model_fields_set:
        cliente.direccion = datos.direccion
    if "nota" in datos.model_fields_set:
        cliente.nota = datos.nota
    if datos.moneda is not None:
        cliente.moneda = datos.moneda.upper()

    db.flush()

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="EDITAR",
        entidad="CLIENTE",
        entidad_id=cliente.id,
        entidad_nombre=cliente.nombre,
        detalle=f"Editó el cliente '{cliente.nombre}'",
        datos_anteriores=snapshot_anterior,
        datos_nuevos=_snapshot_cliente(cliente),
    )

    db.commit()
    db.refresh(cliente)
    return _construir_cliente_out(cliente)


# ════════════════════════════════════════════════════════════════════════════════
# ARCHIVAR / DESARCHIVAR (solo admin)
# ════════════════════════════════════════════════════════════════════════════════

@router.patch("/{cliente_id}/archivar", response_model=ClienteOut)
def archivar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if cliente.archivado:
        raise HTTPException(status_code=400, detail="El cliente ya está archivado")

    snapshot_anterior = _snapshot_cliente(cliente)
    cliente.archivado = True
    db.flush()

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="ARCHIVAR",
        entidad="CLIENTE",
        entidad_id=cliente.id,
        entidad_nombre=cliente.nombre,
        detalle=f"Archivó el cliente '{cliente.nombre}'",
        datos_anteriores=snapshot_anterior,
        datos_nuevos=_snapshot_cliente(cliente),
    )

    db.commit()
    db.refresh(cliente)
    return _construir_cliente_out(cliente)


@router.patch("/{cliente_id}/desarchivar", response_model=ClienteOut)
def desarchivar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if not cliente.archivado:
        raise HTTPException(status_code=400, detail="El cliente ya está activo")

    snapshot_anterior = _snapshot_cliente(cliente)
    cliente.archivado = False
    db.flush()

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="DESARCHIVAR",
        entidad="CLIENTE",
        entidad_id=cliente.id,
        entidad_nombre=cliente.nombre,
        detalle=f"Desarchivó el cliente '{cliente.nombre}'",
        datos_anteriores=snapshot_anterior,
        datos_nuevos=_snapshot_cliente(cliente),
    )

    db.commit()
    db.refresh(cliente)
    return _construir_cliente_out(cliente)


# ════════════════════════════════════════════════════════════════════════════════
# ELIMINAR (solo admin)
# ════════════════════════════════════════════════════════════════════════════════

@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_admin),
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if db.query(Proyecto.id).filter(Proyecto.cliente_id == cliente_id).first():
        raise HTTPException(status_code=409, detail="Desvincula los proyectos de este cliente antes de eliminarlo")

    snapshot_anterior = _snapshot_cliente(cliente)
    nombre = cliente.nombre

    registrar_auditoria(
        db=db,
        usuario=usuario,
        accion="ELIMINAR",
        entidad="CLIENTE",
        entidad_id=cliente.id,
        entidad_nombre=nombre,
        detalle=f"Eliminó permanentemente el cliente '{nombre}'",
        datos_anteriores=snapshot_anterior,
    )

    db.delete(cliente)
    db.commit()