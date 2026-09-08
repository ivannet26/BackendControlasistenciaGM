from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Datos principales
    nombre = Column(String(150), nullable=False)
    email = Column(String(150), nullable=True)

    # Destinatarios en copia (máximo 3, guardados separados por coma)
    destinatarios_cc = Column(String(450), nullable=True)

    direccion = Column(Text, nullable=True)
    nota = Column(Text, nullable=True)

    # Moneda, ej: "USD", "PEN", "EUR"
    moneda = Column(String(10), nullable=False, default="USD")

    # False = activo, True = archivado
    archivado = Column(Boolean, nullable=False, default=False)

    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())
