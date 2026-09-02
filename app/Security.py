import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from jose import jwt, JWTError
import bcrypt

load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "cambia-esto")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))


def _truncar_para_bcrypt(password: str) -> bytes:
    """bcrypt no acepta más de 72 bytes; recorta de forma segura si hace falta."""
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    """Convierte una contraseña en texto plano a un hash seguro para guardar en la BD."""
    hash_bytes = bcrypt.hashpw(_truncar_para_bcrypt(password), bcrypt.gensalt())
    return hash_bytes.decode("utf-8")


def verificar_password(password_plano: str, password_hash: str) -> bool:
    """Compara una contraseña en texto plano contra su hash guardado."""
    return bcrypt.checkpw(_truncar_para_bcrypt(password_plano), password_hash.encode("utf-8"))


def crear_token(data: dict) -> str:
    """Crea un token JWT firmado con los datos del usuario (dura JWT_EXPIRE_MINUTES)."""
    datos_a_codificar = data.copy()
    expira = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    datos_a_codificar.update({"exp": expira})
    return jwt.encode(datos_a_codificar, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decodificar_token(token: str):
    """Decodifica un token JWT. Retorna el payload o None si es inválido/expiró."""
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None