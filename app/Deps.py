from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.Database import get_db
from app.models import Usuario, Rol
from app.Security import decodificar_token

# tokenUrl solo indica dónde se obtiene el token (para la documentación /docs)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def obtener_usuario_actual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Usuario:
    """
    Lee el token del header 'Authorization: Bearer <token>', lo valida,
    y retorna el Usuario correspondiente. Si el token es inválido, corta
    la petición con un error 401.
    """
    error_credenciales = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o token expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decodificar_token(token)
    if payload is None:
        raise error_credenciales

    idusuario = payload.get("idusuario")
    if idusuario is None:
        raise error_credenciales

    usuario = db.query(Usuario).filter(Usuario.idusuario == idusuario).first()
    if usuario is None or not usuario.activo:
        raise error_credenciales

    return usuario


def requiere_admin(usuario: Usuario = Depends(obtener_usuario_actual), db: Session = Depends(get_db)) -> Usuario:
    """Igual que obtener_usuario_actual, pero además exige que el rol sea 'administrador'."""
    rol = db.query(Rol).filter(Rol.idrol == usuario.idrol).first()
    if rol is None or rol.nombre_rol != "administrador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta acción requiere permisos de administrador",
        )
    return usuario