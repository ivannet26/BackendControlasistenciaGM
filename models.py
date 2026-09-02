from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Rol(Base):
    __tablename__ = "roles"

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(50), unique=True, nullable=False)
    descripcion = Column(String(200))
    creado_en   = Column(DateTime(timezone=True), server_default=func.now())

    # Un rol tiene muchos usuarios
    usuarios = relationship("Usuario", back_populates="rol")


class Usuario(Base):
    __tablename__ = "usuarios"

    id            = Column(Integer, primary_key=True, index=True)
    nombre        = Column(String(100), nullable=False)
    apellido      = Column(String(100), nullable=False)
    email         = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    rol_id        = Column(Integer, ForeignKey("roles.id"), nullable=False, default=3)
    activo        = Column(Boolean, default=True)
    creado_en     = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())

    # Acceso directo al objeto Rol desde un Usuario
    rol = relationship("Rol", back_populates="usuarios")
