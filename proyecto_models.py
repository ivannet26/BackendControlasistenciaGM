from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Proyecto(Base):
    __tablename__ = "proyectos"

    id = Column(Integer, primary_key=True, autoincrement=True)

    nombre = Column(String(200), nullable=False, index=True)

    descripcion = Column(Text, nullable=True)

    cliente_id = Column(
        Integer,
        ForeignKey("clientes.id"),
        nullable=True,
        index=True
    )

    estado = Column(
        String(20),
        nullable=False,
        default="ACTIVO"
    )

    color = Column(
        String(7),
        nullable=True
    )

    archivado = Column(
        Boolean,
        nullable=False,
        default=False
    )

    creado_en = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    actualizado_en = Column(
        DateTime(timezone=True),
        onupdate=func.now()
    )

    cliente = relationship(
        "Cliente",
        foreign_keys=[cliente_id]
    )