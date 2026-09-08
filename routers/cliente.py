from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import Usuario
from cliente_models import Cliente
from cliente_schemas import ClienteCrear, ClienteEditar, ClienteOut
from security import get_usuario_actual

router = APIRouter(prefix="/clientes", tags=["Clientes"])


# ── Función auxiliar ──────────────────────────────────────────────────────────

def _construir_cliente_out(cliente: Cliente) -> dict:
    """Convierte el campo destinatarios_cc de string a lista al responder."""
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


# ════════════════════════════════════════════════════════════════════════════════
# LISTAR
# ════════════════════════════════════════════════════════════════════════════════

@router.get("", response_model=List[ClienteOut])
def listar_clientes(
    estado: Optional[str] = Query(
        None,
        description="Filtro: 'activo', 'archivado' o 'todo'. Por defecto devuelve activos.",
    ),
    nombre: Optional[str] = Query(None, description="Buscar por nombre (parcial)"),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """
    Lista clientes con filtros opcionales.
    - estado=activo → solo no archivados (default)
    - estado=archivado → solo archivados
    - estado=todo → todos
    - nombre → búsqueda parcial por nombre
    """
    query = db.query(Cliente)

    # Filtro de estado
    if estado is None or estado.lower() == "activo":
        query = query.filter(Cliente.archivado == False)
    elif estado.lower() == "archivado":
        query = query.filter(Cliente.archivado == True)
    # "todo" no aplica filtro adicional

    # Búsqueda por nombre
    if nombre:
        query = query.filter(Cliente.nombre.ilike(f"%{nombre}%"))

    clientes = query.order_by(Cliente.nombre).all()
    return [_construir_cliente_out(c) for c in clientes]


# ════════════════════════════════════════════════════════════════════════════════
# OBTENER UNO
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/{cliente_id}", response_model=ClienteOut)
def obtener_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Devuelve el detalle de un cliente por su ID."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return _construir_cliente_out(cliente)


# ════════════════════════════════════════════════════════════════════════════════
# CREAR
# ════════════════════════════════════════════════════════════════════════════════

@router.post("", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def crear_cliente(
    datos: ClienteCrear,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Crea un nuevo cliente."""
    # Guardar destinatarios_cc como string separado por comas
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
    db.commit()
    db.refresh(cliente)
    return _construir_cliente_out(cliente)


# ════════════════════════════════════════════════════════════════════════════════
# EDITAR
# ════════════════════════════════════════════════════════════════════════════════

@router.put("/{cliente_id}", response_model=ClienteOut)
def editar_cliente(
    cliente_id: int,
    datos: ClienteEditar,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Edita los datos de un cliente."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if datos.nombre is not None:
        cliente.nombre = datos.nombre
    if datos.email is not None:
        cliente.email = datos.email
    if datos.destinatarios_cc is not None:
        cliente.destinatarios_cc = ",".join(datos.destinatarios_cc)
    if datos.direccion is not None:
        cliente.direccion = datos.direccion
    if datos.nota is not None:
        cliente.nota = datos.nota
    if datos.moneda is not None:
        cliente.moneda = datos.moneda.upper()

    db.commit()
    db.refresh(cliente)
    return _construir_cliente_out(cliente)


# ════════════════════════════════════════════════════════════════════════════════
# ARCHIVAR / DESARCHIVAR
# ════════════════════════════════════════════════════════════════════════════════

@router.patch("/{cliente_id}/archivar", response_model=ClienteOut)
def archivar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Archiva un cliente activo."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if cliente.archivado:
        raise HTTPException(status_code=400, detail="El cliente ya está archivado")

    cliente.archivado = True
    db.commit()
    db.refresh(cliente)
    return _construir_cliente_out(cliente)


@router.patch("/{cliente_id}/desarchivar", response_model=ClienteOut)
def desarchivar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Reactiva un cliente archivado."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if not cliente.archivado:
        raise HTTPException(status_code=400, detail="El cliente ya está activo")

    cliente.archivado = False
    db.commit()
    db.refresh(cliente)
    return _construir_cliente_out(cliente)


# ════════════════════════════════════════════════════════════════════════════════
# ELIMINAR
# ════════════════════════════════════════════════════════════════════════════════

@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_usuario_actual),
):
    """Elimina permanentemente un cliente."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    db.delete(cliente)
    db.commit()
