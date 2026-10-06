# routers/auditoria.py
from datetime import datetime, time, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, func, distinct
from sqlalchemy.orm import Session

import auditoria_schemas as schemas
from auditoria_models import Auditoria
from proyecto_auditoria_models import ProyectoAuditoria
from database import get_db
from models import Usuario
from security import requiere_auditoria

TZ_PERU = ZoneInfo("America/Lima")

router = APIRouter(prefix="/auditoria", tags=["Auditoría"])


@router.get("", response_model=List[schemas.AuditoriaOut])
def listar_auditoria(
    usuario_id: Optional[int] = Query(None),
    proyecto_id: Optional[int] = Query(None),
    accion: Optional[str] = Query(None),
    entidad: Optional[str] = Query(None),
    fecha_inicio: Optional[str] = Query(None, description="YYYY-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="YYYY-MM-DD"),
    buscar: Optional[str] = Query(None),
    limite: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_auditoria),
):
    query_gen = db.query(Auditoria)
    query_proy = db.query(ProyectoAuditoria)

    # ── Filtros comunes ─────────────────────────────────────
    if usuario_id:
        query_gen = query_gen.filter(Auditoria.usuario_id == usuario_id)
        query_proy = query_proy.filter(ProyectoAuditoria.usuario_id == usuario_id)

    if proyecto_id:
        query_gen = query_gen.filter(Auditoria.proyecto_id == proyecto_id)
        query_proy = query_proy.filter(ProyectoAuditoria.proyecto_id == proyecto_id)

    if accion:
        a = accion.strip().upper()
        query_gen = query_gen.filter(Auditoria.accion == a)
        query_proy = query_proy.filter(ProyectoAuditoria.accion == a)

    if entidad:
        entidad_u = entidad.strip().upper()
        query_gen = query_gen.filter(Auditoria.entidad == entidad_u)
        if entidad_u != "PROYECTO":
            query_proy = query_proy.filter(False)

    if fecha_inicio:
        fi = datetime.combine(
            datetime.strptime(fecha_inicio, "%Y-%m-%d").date(),
            time.min, tzinfo=TZ_PERU,
        )
        query_gen = query_gen.filter(Auditoria.fecha >= fi)
        query_proy = query_proy.filter(ProyectoAuditoria.fecha >= fi)

    if fecha_fin:
        ff = datetime.combine(
            datetime.strptime(fecha_fin, "%Y-%m-%d").date(),
            time.max, tzinfo=TZ_PERU,
        )
        query_gen = query_gen.filter(Auditoria.fecha <= ff)
        query_proy = query_proy.filter(ProyectoAuditoria.fecha <= ff)

    if buscar:
        patron = f"%{buscar}%"
        query_gen = query_gen.filter(
            or_(
                Auditoria.detalle.ilike(patron),
                Auditoria.entidad_nombre.ilike(patron),
                Auditoria.usuario_nombre.ilike(patron),
                Auditoria.proyecto_nombre.ilike(patron),
            )
        )
        query_proy = query_proy.filter(
            or_(
                ProyectoAuditoria.detalle.ilike(patron),
                ProyectoAuditoria.proyecto_nombre.ilike(patron),
                ProyectoAuditoria.usuario_nombre.ilike(patron),
            )
        )

    # ── Combinar resultados ─────────────────────────────────
    resultados = []

    for r in query_gen.order_by(Auditoria.fecha.desc()).limit(limite).all():
        resultados.append({
            "id": r.id,
            "origen": "auditoria",
            "usuario_id": r.usuario_id,
            "usuario_nombre": r.usuario_nombre,
            "usuario_email": r.usuario_email,
            "accion": r.accion,
            "entidad": r.entidad,
            "entidad_id": r.entidad_id,
            "entidad_nombre": r.entidad_nombre,
            "proyecto_id": r.proyecto_id,
            "proyecto_nombre": r.proyecto_nombre,
            "detalle": r.detalle,
            "datos_anteriores": r.datos_anteriores,
            "datos_nuevos": r.datos_nuevos,
            "fecha": r.fecha,
        })

    for r in query_proy.order_by(ProyectoAuditoria.fecha.desc()).limit(limite).all():
        resultados.append({
            "id": r.id,
            "origen": "proyecto",
            "usuario_id": r.usuario_id,
            "usuario_nombre": r.usuario_nombre,
            "usuario_email": None,
            "accion": r.accion,
            "entidad": "PROYECTO",
            "entidad_id": r.proyecto_id,
            "entidad_nombre": r.proyecto_nombre,
            "proyecto_id": r.proyecto_id,
            "proyecto_nombre": r.proyecto_nombre,
            "detalle": r.detalle,
            "datos_anteriores": r.datos_anteriores,
            "datos_nuevos": r.datos_nuevos,
            "fecha": r.fecha,
        })

    resultados.sort(key=lambda x: x["fecha"], reverse=True)

    return resultados[:limite]


@router.get("/resumen", response_model=schemas.AuditoriaResumen)
def resumen_auditoria(
    dias: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_auditoria),
):
    desde = datetime.now(TZ_PERU) - timedelta(days=dias)

    # ── Tabla 'auditoria' (nueva) ──────────────────────────
    total_gen = db.query(Auditoria).filter(Auditoria.fecha >= desde).count()
    por_accion_gen = dict(
        db.query(Auditoria.accion, func.count(Auditoria.id))
        .filter(Auditoria.fecha >= desde)
        .group_by(Auditoria.accion).all()
    )
    usuarios_gen = (
        db.query(func.count(distinct(Auditoria.usuario_id)))
        .filter(Auditoria.fecha >= desde).scalar()
    ) or 0

    # ── Tabla 'proyecto_auditoria' (antigua) ───────────────
    total_proy = (
        db.query(ProyectoAuditoria)
        .filter(ProyectoAuditoria.fecha >= desde).count()
    )
    por_accion_proy = dict(
        db.query(ProyectoAuditoria.accion, func.count(ProyectoAuditoria.id))
        .filter(ProyectoAuditoria.fecha >= desde)
        .group_by(ProyectoAuditoria.accion).all()
    )
    usuarios_proy = (
        db.query(func.count(distinct(ProyectoAuditoria.usuario_id)))
        .filter(ProyectoAuditoria.fecha >= desde).scalar()
    ) or 0

    # ── Combinar ───────────────────────────────────────────
    por_accion = {}
    for k, v in por_accion_gen.items():
        por_accion[k] = por_accion.get(k, 0) + v
    for k, v in por_accion_proy.items():
        por_accion[k] = por_accion.get(k, 0) + v

    return {
        "total": total_gen + total_proy,
        "por_accion": por_accion,
        "por_entidad": {},
        "usuarios_activos": max(usuarios_gen, usuarios_proy),
    }