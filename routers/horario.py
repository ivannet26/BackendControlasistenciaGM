from datetime import datetime
from io import BytesIO
import re
import time
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auditoria_helper import registrar_auditoria
from database import get_db
from generador_horario import generar_imagen_horario
from horario_models import HorarioBloque, HorarioImagen
from horario_schemas import BloqueHorario, HorarioGuardar, HorarioOut
from models import Usuario
from r2_client import (
    R2_BUCKET_NAME,
    R2_PUBLIC_URL,
    eliminar_archivo_r2,
    obtener_cliente_r2,
    subir_archivo_r2,
)
from security import get_usuario_actual, requiere_admin


TZ_PERU = ZoneInfo("America/Lima")

router = APIRouter(prefix="/horario", tags=["Horario semanal"])


def _obtener_bloques(db: Session, usuario_id: int) -> list[HorarioBloque]:
    return (
        db.query(HorarioBloque)
        .filter(HorarioBloque.usuario_id == usuario_id)
        .order_by(HorarioBloque.dia_semana, HorarioBloque.hora_inicio)
        .all()
    )


def _extraer_key_r2(imagen_url: Optional[str]) -> Optional[str]:
    if not imagen_url or not R2_PUBLIC_URL:
        return None
    prefijo = f"{R2_PUBLIC_URL}/"
    if imagen_url.startswith(prefijo):
        return imagen_url[len(prefijo) :]
    return None


def _crear_respuesta(
    bloques: list[HorarioBloque],
    imagen: Optional[HorarioImagen],
) -> HorarioOut:
    return HorarioOut(
        bloques=[
            BloqueHorario(
                dia_semana=bloque.dia_semana,
                hora_inicio=bloque.hora_inicio,
            )
            for bloque in bloques
        ],
        imagen_url=imagen.imagen_url if imagen else None,
        creado_en=imagen.creado_en if imagen else None,
        actualizado_en=imagen.actualizado_en if imagen else None,
    )


@router.get("/mi-horario", response_model=HorarioOut)
def obtener_mi_horario(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    bloques = _obtener_bloques(db, usuario.id)
    imagen = (
        db.query(HorarioImagen)
        .filter(HorarioImagen.usuario_id == usuario.id)
        .first()
    )
    return _crear_respuesta(bloques, imagen)


@router.get("/mi-horario/descargar")
def descargar_mi_horario(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    """Descarga el PNG del horario del usuario mediante un proxy a R2."""
    perfil_horario = (
        db.query(HorarioImagen)
        .filter(HorarioImagen.usuario_id == usuario.id)
        .first()
    )
    if not perfil_horario or not perfil_horario.imagen_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tienes un horario generado aún.",
        )

    key = _extraer_key_r2(perfil_horario.imagen_url)
    if not key or not key.startswith("horarios/") or not R2_BUCKET_NAME:
        print(
            f"[DESCARGA] URL de horario inválida o configuración R2 incompleta "
            f"para usuario {usuario.id}",
            flush=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo localizar la imagen del horario.",
        )

    try:
        cliente = obtener_cliente_r2()
        respuesta_r2 = cliente.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        cuerpo = respuesta_r2["Body"]
        try:
            contenido = cuerpo.read()
        finally:
            cuerpo.close()
    except Exception as error:
        print(
            f"[DESCARGA] Error al obtener {key} de R2: "
            f"{type(error).__name__}: {error}",
            flush=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo descargar la imagen del horario.",
        ) from error

    nombre_usuario = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        f"{usuario.nombre}_{usuario.apellido}",
    ).strip("_") or f"usuario_{usuario.id}"
    nombre_descarga = f"horario_{nombre_usuario}.png"

    return StreamingResponse(
        BytesIO(contenido),
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_descarga}"',
            "Cache-Control": "no-cache",
        },
    )


@router.put("/mi-horario", response_model=HorarioOut)
def guardar_mi_horario(
    datos: HorarioGuardar,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    if not datos.bloques:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El horario debe incluir al menos un bloque",
        )

    pares_bloque = {
        (bloque.dia_semana, bloque.hora_inicio)
        for bloque in datos.bloques
    }
    if len(pares_bloque) != len(datos.bloques):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten bloques duplicados",
        )

    usuario_bloqueado = (
        db.query(Usuario)
        .filter(Usuario.id == usuario.id)
        .with_for_update()
        .first()
    )
    if usuario_bloqueado is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    imagen_anterior = (
        db.query(HorarioImagen)
        .filter(HorarioImagen.usuario_id == usuario.id)
        .first()
    )
    key_anterior = _extraer_key_r2(
        imagen_anterior.imagen_url if imagen_anterior else None
    )
    fecha_creacion = datetime.now(TZ_PERU)

    print(f"[HORARIO] Generando imagen para usuario {usuario.id}...", flush=True)
    try:
        contenido_png = generar_imagen_horario(
            nombre=f"{usuario_bloqueado.nombre} {usuario_bloqueado.apellido}".strip(),
            email=usuario_bloqueado.email,
            fecha_creacion=fecha_creacion,
            bloques=[
                bloque.model_dump()
                for bloque in datos.bloques
            ],
        )
    except Exception as error:
        print(
            f"[HORARIO] ERROR al generar imagen: {type(error).__name__}: {error}",
            flush=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar la imagen del horario: {error}",
        ) from error
    print(
        f"[HORARIO] Imagen generada. Tamaño: {len(contenido_png)} bytes",
        flush=True,
    )

    timestamp = int(time.time() * 1000)
    nombre_archivo = f"horario_usuario_{usuario.id}_{timestamp}.png"
    key = f"horarios/{nombre_archivo}"
    print(f"[HORARIO] Subiendo a R2: key={key}", flush=True)
    try:
        nueva_url = subir_archivo_r2(
            contenido_png,
            key,
            "image/png",
        )
        print(f"[HORARIO] URL pública: {nueva_url}", flush=True)
    except Exception as error:
        print(
            f"[HORARIO] ERROR al subir: {type(error).__name__}: {error}",
            flush=True,
        )
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al subir a R2: {error}",
        ) from error

    try:
        db.query(HorarioBloque).filter(
            HorarioBloque.usuario_id == usuario.id
        ).delete(synchronize_session=False)
        db.add_all(
            [
                HorarioBloque(
                    usuario_id=usuario.id,
                    dia_semana=bloque.dia_semana,
                    hora_inicio=bloque.hora_inicio,
                )
                for bloque in datos.bloques
            ]
        )

        imagen = imagen_anterior
        if imagen is None:
            imagen = HorarioImagen(usuario_id=usuario.id, imagen_url=nueva_url)
            db.add(imagen)
        else:
            imagen.imagen_url = nueva_url

        db.flush()
        registrar_auditoria(
            db=db,
            usuario=usuario_bloqueado,
            accion="EDITAR",
            entidad="HORARIO",
            entidad_id=usuario.id,
            entidad_nombre=f"{usuario_bloqueado.nombre} {usuario_bloqueado.apellido}".strip(),
            detalle="Actualizó su horario semanal",
            datos_nuevos={
                "bloques": [bloque.model_dump() for bloque in datos.bloques],
                "imagen_url": nueva_url,
            },
        )
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        eliminar_archivo_r2(key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo guardar el horario en la base de datos",
        ) from error

    db.refresh(imagen)
    print(f"[HORARIO] URL guardada en BD: {nueva_url}", flush=True)
    if key_anterior:
        eliminar_archivo_r2(key_anterior)

    return _crear_respuesta(_obtener_bloques(db, usuario.id), imagen)


@router.delete(
    "/mi-horario",
    status_code=status.HTTP_204_NO_CONTENT,
)
def eliminar_mi_horario(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    imagen = (
        db.query(HorarioImagen)
        .filter(HorarioImagen.usuario_id == usuario.id)
        .first()
    )
    key_anterior = _extraer_key_r2(imagen.imagen_url if imagen else None)

    try:
        db.query(HorarioBloque).filter(
            HorarioBloque.usuario_id == usuario.id
        ).delete(synchronize_session=False)
        if imagen:
            db.delete(imagen)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo eliminar el horario",
        ) from error

    if key_anterior:
        eliminar_archivo_r2(key_anterior)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/usuarios/{usuario_id}/imagen", response_model=dict)
def obtener_imagen_horario_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    imagen = (
        db.query(HorarioImagen)
        .filter(HorarioImagen.usuario_id == usuario_id)
        .first()
    )
    if imagen is None or not imagen.imagen_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ese usuario aún no ha creado su horario",
        )
    return {
        "usuario_id": usuario_id,
        "nombre": f"{usuario.nombre} {usuario.apellido}".strip(),
        "imagen_url": imagen.imagen_url,
    }
