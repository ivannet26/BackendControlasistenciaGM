# refresh_models.py
"""Refresh tokens opacos. En BD solo se guarda el SHA-256 del token."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)

    usuario_id = Column(
        Integer,
        ForeignKey("usuariosPrueba.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SHA-256 hexadecimal (64 chars) del token en claro.
    token_hash = Column(String(64), unique=True, nullable=False, index=True)

    creado_en = Column(DateTime, nullable=False, server_default=func.now())
    expira_en = Column(DateTime, nullable=False, index=True)
    revocado_en = Column(DateTime, nullable=True)

    # id del refresh que sustituyó a este en la rotación.
    reemplazado_por = Column(Integer, nullable=True, index=True)

    ip = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
