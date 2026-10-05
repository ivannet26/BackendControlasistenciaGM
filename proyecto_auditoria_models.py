# proyecto_auditoria_models.py
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class ProyectoAuditoria(Base):
    __tablename__ = "proyecto_auditoria"

    id = Column(Integer, primary_key=True, index=True)

    # Sin ForeignKey a propósito: al eliminar el proyecto,
    # el registro de auditoría debe conservarse.
    proyecto_id = Column(Integer, nullable=True, index=True)
    proyecto_nombre = Column(String(255), nullable=True)

    usuario_id = Column(Integer, nullable=True, index=True)
    usuario_nombre = Column(String(255), nullable=True)

    accion = Column(String(50), nullable=False, index=True)
    detalle = Column(Text, nullable=True)

    datos_anteriores = Column(Text, nullable=True)
    datos_nuevos = Column(Text, nullable=True)

    fecha = Column(DateTime, server_default=func.now(), index=True)
