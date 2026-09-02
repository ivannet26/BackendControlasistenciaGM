from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.Database import get_db
from app.models import Usuario, Rol
from app.Schemas import LoginRequest, TokenResponse, UsuarioActual
from app.Security import verificar_password, crear_token
from app.Deps import obtener_usuario_actual

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=TokenResponse)
def login(datos: LoginRequest, db: Session = Depends(get_db)):
    """Valida código de acceso + contraseña y devuelve un token JWT."""
    usuario = db.query(Usuario).filter(Usuario.username == datos.username).first()

    if not usuario or not usuario.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código de acceso o contraseña incorrectos")

    if not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código de acceso o contraseña incorrectos")

    rol = db.query(Rol).filter(Rol.idrol == usuario.idrol).first()

    token = crear_token({
        "idusuario": usuario.idusuario,
        "idpracticante": usuario.idpracticante,
        "rol": rol.nombre_rol,
    })

    return TokenResponse(access_token=token, rol=rol.nombre_rol)


@router.get("/me", response_model=UsuarioActual)
def me(usuario: Usuario = Depends(obtener_usuario_actual), db: Session = Depends(get_db)):
    """Devuelve la info del usuario actualmente logueado (según el token enviado)."""
    rol = db.query(Rol).filter(Rol.idrol == usuario.idrol).first()
    return UsuarioActual(
        username=usuario.username,
        rol=rol.nombre_rol,
        idpracticante=usuario.idpracticante,
    )