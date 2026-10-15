from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
)

from database import Base


TZ_PERU = ZoneInfo("America/Lima")


class HorarioBloque(Base):
    __tablename__ = "horarios_bloques"
    __table_args__ = (
        UniqueConstraint(
            "usuario_id",
            "dia_semana",
            "hora_inicio",
            name="uk_usuario_dia_hora",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dia_semana = Column(SmallInteger, nullable=False)
    hora_inicio = Column(SmallInteger, nullable=False)
    creado_en = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(TZ_PERU),
    )


class HorarioImagen(Base):
    __tablename__ = "horarios_imagenes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    imagen_url = Column(Text, nullable=False)
    creado_en = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(TZ_PERU),
    )
    actualizado_en = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(TZ_PERU),
        onupdate=lambda: datetime.now(TZ_PERU),
    )
