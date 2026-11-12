from datetime import date, datetime
from pathlib import Path
from typing import List
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from database import SessionLocal, get_db
from justificacion_models import HistorialJustificacion, Justificacion
from justificacion_schemas import (
    JustificacionUpdate,
    JustificacionOut,
    JustificacionResolver,
)
from models import Usuario
from r2_client import subir_archivo_r2
from security import get_usuario_actual, requiere_admin


router = APIRouter(prefix="/justificaciones", tags=["Justificaciones"])
TZ_PERU = ZoneInfo("America/Lima")


def subir_imagen_en_segundo_plano(
    justificacion_id: int,
    contenido_bytes: bytes,
    nombre_objeto: str,
    content_type: str,
) -> None:
    db = SessionLocal()
    try:
        evidencia_url = subir_archivo_r2(
            contenido_bytes=contenido_bytes,
            nombre_objeto=nombre_objeto,
            content_type=content_type,
        )
        justificacion = (
            db.query(Justificacion)
            .filter(Justificacion.id == justificacion_id)
            .first()
        )
        if justificacion is None:
            print(
                "[JUSTIFICACIONES] No se encontró la justificación "
                f"{justificacion_id} al actualizar la evidencia",
            )
            return

        justificacion.evidencia_url = evidencia_url
        db.commit()
    except Exception as error:
        db.rollback()
        print(
            "[JUSTIFICACIONES] Error al subir evidencia en segundo plano: "
            f"{type(error).__name__}: {error}",
            flush=True,
        )
    finally:
        db.close()


def _registrar_historial(
    db: Session,
    justificacion_id: int,
    usuario_id: int,
    accion: str,
    detalle: str,
) -> None:
    db.add(
        HistorialJustificacion(
            justificacion_id=justificacion_id,
            usuario_id=usuario_id,
            accion=accion,
            detalle=detalle,
        )
    )


@router.post("", response_model=JustificacionOut, status_code=status.HTTP_201_CREATED)
async def crear_justificacion(
    tipo: str = Form(...),
    fecha: date = Form(...),
    asunto: str = Form(...),
    mensaje: str = Form(...),
    evidencia: UploadFile = File(None),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    print(
        "[JUSTIFICACIONES] evidencia recibida:",
        None if evidencia is None else {
            "filename": evidencia.filename,
            "content_type": evidencia.content_type,
        },
    )

    tipos_permitidos = {"Falta", "Tardanza", "Olvidé marcar", "Otro"}
    if tipo not in tipos_permitidos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tipo de justificación inválido",
        )

    # Cuenta los intentos del mismo usuario, tipo y fecha sin importar el estado:
    # PENDIENTE, ACEPTADA, RECHAZADA o INJUSTIFICADA.
    intentos_existentes = (
        db.query(func.count(Justificacion.id))
        .filter(
            Justificacion.usuario_id == usuario.id,
            Justificacion.tipo == tipo,
            Justificacion.fecha == fecha,
        )
        .scalar()
        or 0
    )
    if intentos_existentes >= 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Has alcanzado el límite de 2 intentos para esta fecha y tipo",
        )

    contenido_evidencia = None
    nombre_objeto = None
    content_type = None
    if evidencia is not None:
        try:
            extension = Path(evidencia.filename or "").suffix.lower()
            extension_permitidas = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
            if extension not in extension_permitidas:
                raise ValueError(
                    "Formato de imagen no permitido. Usa PNG, JPG, JPEG, WEBP o GIF."
                )

            if not evidencia.content_type or not evidencia.content_type.startswith(
                "image/"
            ):
                raise ValueError("El archivo debe ser una imagen.")

            contenido = await evidencia.read()
            if len(contenido) > 10 * 1024 * 1024:
                raise ValueError("La imagen no debe superar 10 MB.")

            nombre_unico = f"justificaciones/{uuid4().hex}{extension}"
            contenido_evidencia = contenido
            nombre_objeto = nombre_unico
            content_type = evidencia.content_type
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            )
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No se pudo subir la evidencia a Cloudflare R2",
            ) from error

    justificacion = Justificacion(
        usuario_id=usuario.id,
        intento_numero=intentos_existentes + 1,
        tipo=tipo,
        fecha=fecha,
        asunto=asunto.strip(),
        mensaje=mensaje.strip(),
        evidencia_url=None,
        estado="PENDIENTE",
    )
    db.add(justificacion)
    db.flush()

    _registrar_historial(
        db,
        justificacion.id,
        usuario.id,
        "CREACION",
        (
            f"Creó una justificación de tipo {justificacion.tipo} "
            f"el dia de hoy {justificacion.fecha.isoformat()}"
        ),
    )

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if "uq_justificacion_intento" in str(error).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Has alcanzado el límite de 2 intentos para esta fecha y tipo",
            ) from error
        raise
    db.refresh(justificacion)

    if contenido_evidencia is not None and background_tasks is not None:
        background_tasks.add_task(
            subir_imagen_en_segundo_plano,
            justificacion.id,
            contenido_evidencia,
            nombre_objeto,
            content_type,
        )

    return justificacion


@router.put("/{justificacion_id}", response_model=JustificacionOut)
def editar_justificacion(
    justificacion_id: int,
    datos: JustificacionUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    justificacion = (
        db.query(Justificacion)
        .filter(
            Justificacion.id == justificacion_id,
            Justificacion.usuario_id == usuario.id,
        )
        .first()
    )
    if not justificacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificación no encontrada",
        )

    hoy = datetime.now(TZ_PERU).date()
    if justificacion.fecha != hoy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo puedes editar una justificación el mismo día de la fecha",
        )
    if justificacion.estado != "PENDIENTE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La justificación ya fue procesada",
        )

    cambios = datos.model_dump(exclude_unset=True)
    if "fecha" in cambios and cambios["fecha"] != hoy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo puedes mantener la fecha de hoy al editar",
        )
    for campo, valor in cambios.items():
        setattr(justificacion, campo, valor)

    _registrar_historial(
        db,
        justificacion.id,
        usuario.id,
        "COMENTARIO",
        "Editó los datos de la justificación",
    )
    db.commit()
    db.refresh(justificacion)
    return justificacion


@router.get("/mias", response_model=List[JustificacionOut])
def listar_mis_justificaciones(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return (
        db.query(Justificacion)
        .filter(Justificacion.usuario_id == usuario.id)
        .order_by(Justificacion.fecha.desc(), Justificacion.id.desc())
        .all()
    )


@router.get("/pendientes", response_model=List[JustificacionOut])
def listar_justificaciones_pendientes(
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    return (
        db.query(Justificacion)
        .options(joinedload(Justificacion.usuario), joinedload(Justificacion.historial))
        .filter(Justificacion.estado == "PENDIENTE")
        .order_by(Justificacion.fecha.asc(), Justificacion.creado_en.asc())
        .all()
    )


@router.get("/historial", response_model=List[JustificacionOut])
def listar_justificaciones_procesadas(
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    return (
        db.query(Justificacion)
        .filter(Justificacion.estado != "PENDIENTE")
        .order_by(Justificacion.fecha_resolucion.desc(), Justificacion.id.desc())
        .all()
    )


@router.put("/{justificacion_id}/resolver", response_model=JustificacionOut)
def resolver_justificacion(
    justificacion_id: int,
    datos: JustificacionResolver,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    justificacion = (
        db.query(Justificacion)
        .filter(Justificacion.id == justificacion_id)
        .first()
    )

    if not justificacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Justificación no encontrada",
        )

    if justificacion.estado != "PENDIENTE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La justificación ya fue procesada",
        )

    estado_anterior = justificacion.estado
    justificacion.estado = datos.estado
    justificacion.comentario_admin = datos.comentario_admin.strip()
    justificacion.fecha_resolucion = datetime.now()

    _registrar_historial(
        db,
        justificacion.id,
        admin.id,
        "CAMBIO_ESTADO",
        (
            f"Cambio de estado {estado_anterior} a {justificacion.estado}. "
            f"Comentario: {justificacion.comentario_admin}"
        ),
    )

    db.commit()
    db.refresh(justificacion)
    return justificacion


@router.get("/contar-pendientes")
def contar_justificaciones_pendientes(
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    cantidad = (
        db.query(func.count(Justificacion.id))
        .filter(Justificacion.estado == "PENDIENTE")
        .scalar()
        or 0
    )
    return {"pendientes": cantidad}
