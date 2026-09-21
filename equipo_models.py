from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# ── Tabla intermedia: relación muchos-a-muchos entre etiquetas y tareas ───────
tarea_etiqueta = Table(
    "tarea_etiqueta",
    Base.metadata,
    Column("tarea_id", Integer, ForeignKey("rastreador_tareas.id", ondelete="CASCADE"), primary_key=True),
    Column("etiqueta_id", Integer, ForeignKey("etiquetas.id", ondelete="CASCADE"), primary_key=True),
)

# ── Tabla intermedia: relación muchos-a-muchos entre etiquetas y miembros ─────
miembro_etiqueta = Table(
    "miembro_etiqueta",
    Base.metadata,
    Column("miembro_id", Integer, ForeignKey("miembros_equipo.id", ondelete="CASCADE"), primary_key=True),
    Column("etiqueta_id", Integer, ForeignKey("etiquetas.id", ondelete="CASCADE"), primary_key=True),
)


class Grupo(Base):
    __tablename__ = "grupos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), unique=True, nullable=False)
    descripcion = Column(String(255), nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    miembros = relationship("MiembroEquipo", back_populates="grupo")


class Etiqueta(Base):
    __tablename__ = "etiquetas"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(80), unique=True, nullable=False)
    color = Column(String(7), nullable=True)
    archivado = Column(Boolean, default=False, nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    miembros = relationship("MiembroEquipo", secondary="miembro_etiqueta", back_populates="etiquetas")
    tareas = relationship("Tarea", secondary="tarea_etiqueta", back_populates="etiquetas")


class MiembroEquipo(Base):
    __tablename__ = "miembros_equipo"
    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuariosPrueba.id"), nullable=False, index=True)
    grupo_id = Column(Integer, ForeignKey("grupos.id"), nullable=True, index=True)
    tipo_usuario = Column(String(30), nullable=False, default="MIEMBRO")
    estado = Column(String(20), nullable=False, default="ACTIVO")
    clave_temp = Column(String(255), nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())

    grupo = relationship("Grupo", back_populates="miembros")
    usuario = relationship("Usuario", foreign_keys=[usuario_id])
    etiquetas = relationship("Etiqueta", secondary="miembro_etiqueta", back_populates="miembros")

    # ========================================================
    # RELACIÓN MUCHOS A MUCHOS CON TAREAS
    # ========================================================

    tareas = relationship(
        "Tarea",
        secondary="tarea_miembro",
        back_populates="miembros",
    )

    # ========================================================
    # PROPIEDADES: exponen nombre/apellido/email del usuario
    # ========================================================

    @property
    def nombre(self) -> str | None:
        return self.usuario.nombre if self.usuario else None

    @property
    def apellido(self) -> str | None:
        return self.usuario.apellido if self.usuario else None

    @property
    def email(self) -> str | None:
        return self.usuario.email if self.usuario else None