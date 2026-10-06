# auditoria_helper.py
import json
from typing import Any, Optional
from sqlalchemy.orm import Session
from auditoria_models import Auditoria


def registrar_auditoria(
    db: Session,
    usuario,
    accion: str,
    entidad: str,
    entidad_id: Optional[int] = None,
    entidad_nombre: Optional[str] = None,
    proyecto_id: Optional[int] = None,
    proyecto_nombre: Optional[str] = None,
    detalle: Optional[str] = None,
    datos_anteriores: Optional[Any] = None,
    datos_nuevos: Optional[Any] = None,
):
    """
    Registra una acción en auditoría. NO hace commit.
    El endpoint debe hacer el commit final.
    """
    try:
        usuario_nombre = None
        usuario_email = None
        usuario_id = None

        if usuario:
            usuario_id = getattr(usuario, "id", None)
            nombre = getattr(usuario, "nombre", "") or ""
            apellido = getattr(usuario, "apellido", "") or ""
            usuario_nombre = f"{nombre} {apellido}".strip() or None
            usuario_email = getattr(usuario, "email", None)

        registro = Auditoria(
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            usuario_email=usuario_email,
            accion=accion.upper(),
            entidad=entidad.upper(),
            entidad_id=entidad_id,
            entidad_nombre=(entidad_nombre or "")[:255] or None,
            proyecto_id=proyecto_id,
            proyecto_nombre=proyecto_nombre,
            detalle=detalle,
            datos_anteriores=(
                json.dumps(datos_anteriores, default=str, ensure_ascii=False)
                if datos_anteriores is not None else None
            ),
            datos_nuevos=(
                json.dumps(datos_nuevos, default=str, ensure_ascii=False)
                if datos_nuevos is not None else None
            ),
        )
        db.add(registro)
    except Exception as e:
        # Nunca debe romper la operación principal
        print(f"[AUDITORIA] Error al registrar: {e}")