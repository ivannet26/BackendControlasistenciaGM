from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    Numeric
)
from sqlalchemy.orm import relationship
from database import Base


TZ_PERU = ZoneInfo("America/Lima")


# ============================================================
# TABLA INTERMEDIA: TAREA <-> MIEMBRO_EQUIPO (muchos a muchos)
# ============================================================

tarea_miembro = Table(
    "tarea_miembro",
    Base.metadata,
    Column(
        "tarea_id",
        Integer,
        ForeignKey("rastreador_tareas.id", ondelete="CASCADE"),
        primary_key=True
    ),
    Column(
        "miembro_id",
        Integer,
        ForeignKey("miembros_equipo.id", ondelete="CASCADE"),
        primary_key=True
    )
)


class Tarea(Base):
    __tablename__ = "rastreador_tareas"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

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

    titulo = Column(
        String(200),
        nullable=False
    )

    descripcion = Column(
        Text,
        nullable=True
    )

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

    fecha_limite = Column(
        Date,
        nullable=True
    )

    horas = Column(
        Numeric(7, 2),
        nullable=False,
        default=0.00
    )

    creada_en = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(TZ_PERU)
    )

    actualizada_en = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(TZ_PERU),
        onupdate=lambda: datetime.now(TZ_PERU)
    )

    # ========================================================
    # RELACIÓN CON PROYECTO
    # ========================================================

    proyecto = relationship(
        "Proyecto",
        foreign_keys=[proyecto_id]
    )

    @property
    def nombre_proyecto(self) -> str | None:
        """Devuelve el nombre del proyecto si existe."""
        return self.proyecto.nombre if self.proyecto else None

    @property
    def color_proyecto(self) -> str | None:
        """Devuelve el color hex del proyecto si existe."""
        return self.proyecto.color if self.proyecto else None

    # ========================================================
    # RELACIÓN MUCHOS A MUCHOS CON ETIQUETAS
    # ========================================================

    etiquetas = relationship(
        "Etiqueta",
        secondary="tarea_etiqueta",
        back_populates="tareas",
    )

    # ========================================================
    # RELACIÓN MUCHOS A MUCHOS CON MIEMBROS DEL EQUIPO
    # ========================================================

    miembros = relationship(
        "MiembroEquipo",
        secondary="tarea_miembro",
        back_populates="tareas",
    )


class EnlaceRastreador(Base):
    __tablename__ = "rastreador_enlaces"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

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
        default=lambda: datetime.now(TZ_PERU)
    )


# ============================================================
# TEMPORIZADOR EN VIVO / REGISTRO DE TIEMPO
# ============================================================

class TiempoRegistro(Base):
    __tablename__ = "tiempo_registros"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    usuario_id = Column(
        Integer,
        ForeignKey(
            "usuariosPrueba.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    proyecto_id = Column(
        Integer,
        ForeignKey(
            "proyectos.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    tarea_id = Column(
        Integer,
        ForeignKey(
            "rastreador_tareas.id",
            ondelete="SET NULL"
        ),
        nullable=True,
        index=True
    )

    descripcion = Column(
        String(255),
        nullable=True
    )

    inicio = Column(
        DateTime,
        nullable=False
    )

    fin = Column(
        DateTime,
        nullable=True
    )

    duracion_segundos = Column(
        Integer,
        nullable=False,
        default=0
    )

    creado_en = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(TZ_PERU)
    )

    # ========================================================
    # RELACIONES
    # ========================================================

    proyecto = relationship(
        "Proyecto",
        foreign_keys=[proyecto_id]
    )

    tarea = relationship(
        "Tarea",
        foreign_keys=[tarea_id]
    )

    # ========================================================
    # PROPIEDADES
    # ========================================================

    @property
    def nombre_proyecto(self) -> str | None:
        """Devuelve el nombre del proyecto."""
        return self.proyecto.nombre if self.proyecto else None

    @property
    def color_proyecto(self) -> str | None:
        """Devuelve el color del proyecto."""
        return self.proyecto.color if self.proyecto else None

    @property
    def titulo_tarea(self) -> str | None:
        """Devuelve el título de la tarea."""
        return self.tarea.titulo if self.tarea else None