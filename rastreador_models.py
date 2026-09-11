from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Tarea(Base):
    __tablename__ = "rastreador_tareas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id"),
        nullable=False,
        index=True
    )
    proyecto_id = Column(
        Integer,
        ForeignKey("proyectos.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    estado = Column(
        String(20),
        nullable=False,
        default="PENDIENTE"
    )
    prioridad = Column(
        String(20),
        nullable=False,
        default="MEDIA"
    )
    fecha_limite = Column(Date, nullable=True)
    creada_en = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    actualizada_en = Column(
        DateTime(timezone=True),
        onupdate=func.now()
    )

    # Relación con Proyecto
    proyecto = relationship(
        "Proyecto",
        foreign_keys=[proyecto_id]
    )

    @property
    def nombre_proyecto(self) -> str | None:
        """Devuelve el nombre del proyecto si existe, o None si no tiene proyecto."""
        return self.proyecto.nombre if self.proyecto else None

    # Relación muchos-a-muchos con Etiqueta (gestionada desde el módulo Equipo)
    etiquetas = relationship(
        "Etiqueta",
        secondary="tarea_etiqueta",
        back_populates="tareas",
    )


class EnlaceRastreador(Base):
    __tablename__ = "rastreador_enlaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id"),
        nullable=False,
        index=True
    )
    token = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True
    )
    activo = Column(
        Boolean,
        default=True,
        nullable=False
    )
    creado_en = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )