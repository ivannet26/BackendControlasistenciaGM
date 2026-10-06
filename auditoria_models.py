# auditoria_models.py
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class Auditoria(Base):
    __tablename__ = "auditoria"

    id = Column(Integer, primary_key=True, index=True)

    # ── Quién ──────────────────────────────────────────────
    usuario_id = Column(Integer, nullable=True, index=True)
    usuario_nombre = Column(String(255), nullable=True)
    usuario_email = Column(String(255), nullable=True)

    # ── Qué ────────────────────────────────────────────────
    accion = Column(String(50), nullable=False, index=True)
    entidad = Column(String(50), nullable=False, index=True)
    entidad_id = Column(Integer, nullable=True, index=True)
    entidad_nombre = Column(String(255), nullable=True)

    # ── Contexto de proyecto (opcional) ───────────────────
    proyecto_id = Column(Integer, nullable=True, index=True)
    proyecto_nombre = Column(String(255), nullable=True)

    # ── Detalle ───────────────────────────────────────────
    detalle = Column(Text, nullable=True)
    datos_anteriores = Column(Text, nullable=True)
    datos_nuevos = Column(Text, nullable=True)

    # ── Cuándo ────────────────────────────────────────────
    fecha = Column(DateTime, server_default=func.now(), index=True)