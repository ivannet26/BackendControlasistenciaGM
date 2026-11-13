from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


TZ_PERU = ZoneInfo("America/Lima")


class RegistroAsistencia(Base):
    __tablename__ = "registros_asistencia"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo = Column(String(20), nullable=False, index=True)
    hora = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(TZ_PERU),
        index=True,
    )
    ip_address = Column(String(45), nullable=True)
    notas = Column(Text, nullable=True)
    creado_en = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(TZ_PERU),
    )

    usuario = relationship("Usuario", foreign_keys=[usuario_id])


class HistorialHorasPracticas(Base):
    __tablename__ = "historial_horas_practicas"
    __table_args__ = (
        UniqueConstraint(
            "usuario_id",
            name="uq_historial_horas_practicas_usuario",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    horas_acumuladas = Column(Numeric(10, 2), nullable=False, default=0)
    actualizado_en = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(TZ_PERU),
        onupdate=lambda: datetime.now(TZ_PERU),
    )
