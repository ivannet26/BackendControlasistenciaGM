import os

import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "").rstrip("/")
R2_REGION = os.getenv("R2_REGION", "auto")

_client = None


def obtener_cliente_r2():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name=R2_REGION,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
    return _client


def subir_archivo_r2(
    contenido_bytes: bytes,
    nombre_objeto: str,
    content_type: str,
) -> str:
    """Sube un archivo a R2 y devuelve la URL pública."""
    if not all(
        (
            R2_ACCESS_KEY_ID,
            R2_SECRET_ACCESS_KEY,
            R2_ENDPOINT_URL,
            R2_BUCKET_NAME,
            R2_PUBLIC_URL,
        )
    ):
        raise RuntimeError("La configuración de Cloudflare R2 está incompleta")

    cliente = obtener_cliente_r2()
    cliente.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=nombre_objeto,
        Body=contenido_bytes,
        ContentType=content_type,
        CacheControl="public, max-age=31536000, immutable",
    )
    return f"{R2_PUBLIC_URL}/{nombre_objeto}"


def eliminar_archivo_r2(nombre_objeto: str) -> None:
    """Elimina un archivo de R2. Silencia errores si no existe."""
    try:
        cliente = obtener_cliente_r2()
        cliente.delete_object(Bucket=R2_BUCKET_NAME, Key=nombre_objeto)
    except Exception as e:
        print(f"[R2] Error al eliminar {nombre_objeto}: {e}")
