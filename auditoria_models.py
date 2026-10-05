from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class AuditoriaProyecto(Base):
    """
    Registro de auditoría de acciones realizadas sobre un proyecto
    (crear, editar, archivar, desarchivar, eliminar).

    Se guarda el nombre del proyecto en el momento de la acción
    (snapshot) para que el historial siga siendo legible incluso
    si el proyecto termina siendo eliminado físicamente.
    """

    __tablename__ = "auditoria_proyectos"

    id = Column(Integer, primary_key=True, autoincrement=True)

    proyecto_id = Column(
        Integer,
        ForeignKey("proyectos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    proyecto_nombre = Column(String(200), nullable=False)

    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    accion = Column(String(30), nullable=False, index=True)
    # CREAR | EDITAR | ARCHIVAR | DESARCHIVAR | ELIMINAR

    detalle = Column(Text, nullable=True)
    # Descripción legible de qué cambió (ej: "estado: ACTIVO -> PAUSADO")

    creado_en = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    usuario = relationship("Usuario", foreign_keys=[usuario_id])

    @property
    def usuario_nombre(self) -> str | None:
        if not self.usuario:
            return None
        return f"{self.usuario.nombre} {self.usuario.apellido}".strip()

    @property
    def usuario_email(self) -> str | None:
        return self.usuario.email if self.usuario else None