from sqlalchemy import Column, Integer, String, Date, Time, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.Database import Base


class Practicante(Base):
    """
    Descripción mínima de la tabla 'practicantes' que ya existe en la base
    de datos. No hace falta listar TODAS sus columnas, solo las necesarias
    para que las relaciones (ForeignKey) con otras tablas funcionen.
    """
    __tablename__ = "practicantes"
    idpracticante = Column(Integer, primary_key=True)
    codigoestudiante = Column(String(30))


class Rol(Base):
    __tablename__ = "roles"
    idrol = Column(Integer, primary_key=True, autoincrement=True)
    nombre_rol = Column(String(50), unique=True, nullable=False)


class Usuario(Base):
    __tablename__ = "usuarios"
    idusuario = Column(Integer, primary_key=True, autoincrement=True)
    idpracticante = Column(Integer, ForeignKey("practicantes.idpracticante"), unique=True, nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    idrol = Column(Integer, ForeignKey("roles.idrol"), nullable=False)
    activo = Column(Boolean, default=True)

    rol = relationship("Rol")


class MarcacionAsistencia(Base):
    __tablename__ = "marcaciones_asistencia"
    idmarcaciones_asistencia = Column(Integer, primary_key=True, autoincrement=True)
    idpracticante = Column(Integer, ForeignKey("practicantes.idpracticante"), nullable=False)
    fecha = Column(Date, nullable=False)
    hora_entrada = Column(Time, nullable=True)
    hora_salida = Column(Time, nullable=True)