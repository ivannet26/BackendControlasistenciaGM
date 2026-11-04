from sqlalchemy import BigInteger, Column, Date, DateTime, Enum, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Justificacion(Base):
    __tablename__ = "justificaciones"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    intento_numero = Column(SmallInteger, nullable=False)
    tipo = Column(
        Enum(
            "Falta",
            "Tardanza",
            "Olvidé marcar",
            "Otro",
            name="tipo_justificacion",
        ),
        nullable=False,
    )
    fecha = Column(Date, nullable=False, index=True)
    asunto = Column(String(255), nullable=False)
    mensaje = Column(Text, nullable=False)
    evidencia_url = Column(String(1000), nullable=True)
    estado = Column(
        Enum(
            "PENDIENTE",
            "ACEPTADA",
            "RECHAZADA",
            "INJUSTIFICADA",
            name="estado_justificacion",
        ),
        nullable=False,
        default="PENDIENTE",
        server_default="PENDIENTE",
    )
    comentario_admin = Column(Text, nullable=True)
    fecha_resolucion = Column(DateTime, nullable=True)
    creado_en = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    usuario = relationship("Usuario", foreign_keys=[usuario_id])
    historial = relationship(
        "HistorialJustificacion",
        foreign_keys="HistorialJustificacion.justificacion_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def usuario_nombre(self):
        if not self.usuario:
            return None
        return f"{self.usuario.nombre} {self.usuario.apellido}".strip()

    @property
    def usuario_email(self):
        return self.usuario.email if self.usuario else None


class HistorialJustificacion(Base):
    __tablename__ = "historial_justificaciones"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    justificacion_id = Column(
        BigInteger,
        ForeignKey("justificaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    accion = Column(
        Enum(
            "CREACION",
            "CAMBIO_ESTADO",
            "COMENTARIO",
            name="accion_historial_justificacion",
        ),
        nullable=False,
    )
    detalle = Column(Text, nullable=True)
    fecha_accion = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    justificacion = relationship(
        "Justificacion",
        foreign_keys=[justificacion_id],
    )
    usuario = relationship("Usuario", foreign_keys=[usuario_id])
