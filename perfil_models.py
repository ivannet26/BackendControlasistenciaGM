from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class PerfilUsuario(Base):
    __tablename__ = "perfiles_usuario"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    telefono = Column(String(30), nullable=True)
    dni = Column(String(20), nullable=True)
    direccion = Column(String(255), nullable=True)
    fecha_nacimiento = Column(Date, nullable=True)
    puesto = Column(String(100), nullable=True)
    avatar_url = Column(Text, nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())

    usuario = relationship("Usuario", foreign_keys=[usuario_id])
