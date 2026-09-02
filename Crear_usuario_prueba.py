"""
Script único para crear un usuario de prueba (o el primer administrador).
Ejecutar con: python crear_usuario_prueba.py

Pide el código de acceso (puede ser el mismo codigoestudiante del
practicante), la contraseña en texto plano (se guarda hasheada, nunca
en texto plano), y el rol.
"""
from app.Database import SessionLocal
from app.models import Usuario, Rol
from app.Security import hash_password


def main():
    db = SessionLocal()

    username = input("Código de acceso (ej. el codigoestudiante del practicante): ").strip()
    idpracticante = int(input("idpracticante (el ID numérico de la tabla practicantes): ").strip())
    password = input("Contraseña: ").strip()
    nombre_rol = input("Rol (practicante / administrador): ").strip().lower()

    rol = db.query(Rol).filter(Rol.nombre_rol == nombre_rol).first()
    if not rol:
        print(f"El rol '{nombre_rol}' no existe. Ejecuta primero crear_usuarios_roles.sql")
        return

    existente = db.query(Usuario).filter(Usuario.username == username).first()
    if existente:
        print(f"Ya existe un usuario con el código de acceso '{username}'.")
        return

    nuevo_usuario = Usuario(
        idpracticante=idpracticante,
        username=username,
        password_hash=hash_password(password),
        idrol=rol.idrol,
        activo=True,
    )
    db.add(nuevo_usuario)
    db.commit()
    print(f"Usuario '{username}' creado con rol '{nombre_rol}'.")


if __name__ == "__main__":
    main()