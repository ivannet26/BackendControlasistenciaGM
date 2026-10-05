from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class SesionUsuario(Base):
    """
    Una fila por cada login (cada JWT emitido). El JWT lleva un `jti`
    que apunta a esta tabla. Fechas en UTC (naive).
    """

    __tablename__ = "sesiones_usuario"

    id = Column(Integer, primary_key=True, autoincrement=True)

    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    jti = Column(String(36), unique=True, nullable=False, index=True)

    ip = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)

    creado_en = Column(DateTime, nullable=False)
    expira_en = Column(DateTime, nullable=False)
    ultimo_uso = Column(DateTime, nullable=False)

    activa = Column(Boolean, nullable=False, default=True, index=True)
    cerrada_en = Column(DateTime, nullable=True)
    motivo_cierre = Column(String(30), nullable=True)
    # LOGOUT | LIMITE | REMOTO_ADMIN | CUENTA_DESACTIVADA | EXPIRADA

    usuario = relationship("Usuario", foreign_keys=[usuario_id])