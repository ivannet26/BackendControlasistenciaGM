from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


ANCHO_IMAGEN = 2800
MARGEN = 60
DPI_IMPRESION = 300
COLOR_ROJO = "#c02020"
COLOR_AZUL_CHECK = (16, 165, 245)
COLOR_ENCABEZADO = "#f0f0f0"
COLOR_BORDE = "#64748b"
COLOR_DIVISOR = "#94a3b8"
COLOR_TEXTO = "#101b22"
ALTO_LOGO = 130
MARGEN_CABECERA = 30
SEPARACION_LOGO_DATOS = 50
DIAS_SEMANA = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)
TZ_PERU = ZoneInfo("America/Lima")

_RUTAS_FUENTE_REGULAR = (
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
_RUTAS_FUENTE_NEGRITA = (
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _cargar_fuente(tamano: int, negrita: bool = False) -> ImageFont.ImageFont:
    """Carga Arial o DejaVu Sans, con fallback a la fuente predeterminada."""
    rutas = _RUTAS_FUENTE_NEGRITA if negrita else _RUTAS_FUENTE_REGULAR
    for ruta in rutas:
        if Path(ruta).is_file():
            try:
                return ImageFont.truetype(ruta, tamano)
            except OSError:
                continue
    return ImageFont.load_default()


def _cargar_logo() -> Image.Image | None:
    """Carga el logo existente conservando la resolución de origen."""
    rutas_logo = (
        Path(__file__).resolve().parent / "assets" / "logo-mg.png",
        Path(__file__).resolve().parent / "routers" / "assets" / "logo-mg.png",
    )
    ruta_logo = next((ruta for ruta in rutas_logo if ruta.is_file()), None)
    if ruta_logo is None:
        return None

    try:
        with Image.open(ruta_logo) as original:
            return original.convert("RGBA")
    except OSError as error:
        print(f"No se pudo cargar el logo: {error}")
        return None


def dibujar_check_azul(
    dibujo: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    tamaño: int = 40,
    color: tuple[int, int, int] = COLOR_AZUL_CHECK,
    grosor: int = 5,
) -> None:
    """Dibuja un check azul grande con trazos y extremos redondeados."""
    puntos = (
        (round(cx - tamaño * 0.35), round(cy)),
        (round(cx - tamaño * 0.1), round(cy + tamaño * 0.3)),
        (round(cx + tamaño * 0.4), round(cy - tamaño * 0.35)),
    )
    radio = max(2, grosor // 2)
    dibujo.line(puntos, fill=color, width=grosor, joint="curve")
    for x, y in puntos:
        dibujo.ellipse(
            (x - radio, y - radio, x + radio, y + radio),
            fill=color,
        )


def _dibujar_dato(
    dibujo: ImageDraw.ImageDraw,
    x_inicio: int,
    y: int,
    etiqueta: str,
    valor: str,
    fuente_negrita: ImageFont.ImageFont,
    fuente_regular: ImageFont.ImageFont,
) -> None:
    """Dibuja una línea de datos con etiqueta bold y valor regular."""
    ancho_etiqueta = dibujo.textlength(etiqueta, font=fuente_negrita)
    dibujo.text(
        (x_inicio, y),
        etiqueta,
        fill=COLOR_TEXTO,
        font=fuente_negrita,
    )
    dibujo.text(
        (x_inicio + ancho_etiqueta + 12, y),
        valor,
        fill=COLOR_TEXTO,
        font=fuente_regular,
    )


def generar_imagen_horario(
    nombre: str,
    email: str,
    fecha_creacion: datetime,
    bloques: list[dict],
) -> bytes:
    """
    Genera una imagen PNG de alta resolución del horario semanal.
    bloques: [{"dia_semana": 1, "hora_inicio": 8}, ...]
    """
    if fecha_creacion.tzinfo is None:
        fecha_local = fecha_creacion.replace(tzinfo=TZ_PERU)
    else:
        fecha_local = fecha_creacion.astimezone(TZ_PERU)
    fecha_texto = fecha_local.strftime("%d/%m/%Y %H:%M")

    bloques_marcados = {
        (bloque["dia_semana"], bloque["hora_inicio"])
        for bloque in bloques
    }
    horas = sorted({hora for _, hora in bloques_marcados})

    y_cabecera = MARGEN_CABECERA
    y_divisor = y_cabecera + ALTO_LOGO + 20
    y_titulo = y_divisor + 50
    y_inicio_tabla = y_titulo + 70
    alto_encabezado = 80
    alto_fila = 74
    alto_fila_total = 80
    alto_pie = 100
    alto_tabla = alto_encabezado + len(horas) * alto_fila + alto_fila_total
    alto_imagen = y_inicio_tabla + alto_tabla + alto_pie

    imagen = Image.new("RGB", (ANCHO_IMAGEN, alto_imagen), "#ffffff")
    buffer = BytesIO()
    logo = _cargar_logo()
    logo_redimensionado = None
    try:
        dibujo = ImageDraw.Draw(imagen)
        fuente_titulo = _cargar_fuente(72, negrita=True)
        fuente_datos = _cargar_fuente(36)
        fuente_datos_negrita = _cargar_fuente(36, negrita=True)
        fuente_encabezado = _cargar_fuente(32, negrita=True)
        fuente_celda = _cargar_fuente(28)
        fuente_total = _cargar_fuente(36, negrita=True)

        if logo is not None:
            alto_logo = ALTO_LOGO
            ancho_logo = max(1, round(logo.width * alto_logo / logo.height))
            logo_redimensionado = logo.resize(
                (ancho_logo, alto_logo),
                Image.Resampling.LANCZOS,
            )
            imagen.paste(
                logo_redimensionado,
                (MARGEN_CABECERA, y_cabecera),
                logo_redimensionado,
            )
        else:
            dibujo.text(
                (MARGEN_CABECERA, y_cabecera + 20),
                "GM",
                fill=COLOR_ROJO,
                font=_cargar_fuente(64, negrita=True),
            )

        ancho_logo_datos = logo_redimensionado.width if logo_redimensionado else 200
        x_datos = (
            MARGEN_CABECERA
            + ancho_logo_datos
            + SEPARACION_LOGO_DATOS
        )
        y_datos_inicio = y_cabecera + (ALTO_LOGO - 3 * 40) // 2
        _dibujar_dato(
            dibujo,
            x_datos,
            y_datos_inicio,
            "Nombre:",
            nombre,
            fuente_datos_negrita,
            fuente_datos,
        )
        _dibujar_dato(
            dibujo,
            x_datos,
            y_datos_inicio + 40,
            "Email:",
            email,
            fuente_datos_negrita,
            fuente_datos,
        )
        _dibujar_dato(
            dibujo,
            x_datos,
            y_datos_inicio + 80,
            "Fecha:",
            fecha_texto,
            fuente_datos_negrita,
            fuente_datos,
        )

        dibujo.line(
            (MARGEN, y_divisor, ANCHO_IMAGEN - MARGEN, y_divisor),
            fill=COLOR_DIVISOR,
            width=1,
        )
        dibujo.text(
            (ANCHO_IMAGEN // 2, y_titulo),
            "HORARIO DE ACTIVIDAD",
            fill=COLOR_ROJO,
            font=fuente_titulo,
            anchor="mm",
        )

        x_inicio = MARGEN
        ancho_tabla = ANCHO_IMAGEN - 2 * MARGEN
        ancho_columna_hora = 440
        ancho_columna_dia = (ancho_tabla - ancho_columna_hora) / 7
        limites_x = [x_inicio, x_inicio + ancho_columna_hora]
        limites_x.extend(
            round(x_inicio + ancho_columna_hora + ancho_columna_dia * indice)
            for indice in range(1, 8)
        )
        limites_x[-1] = x_inicio + ancho_tabla

        y_actual = y_inicio_tabla
        encabezados = ["HORARIO", *DIAS_SEMANA]
        for columna, texto in enumerate(encabezados):
            izquierda, derecha = limites_x[columna : columna + 2]
            dibujo.rectangle(
                (izquierda, y_actual, derecha, y_actual + alto_encabezado),
                fill=COLOR_ENCABEZADO,
                outline=COLOR_BORDE,
                width=2,
            )
            dibujo.text(
                ((izquierda + derecha) // 2, y_actual + alto_encabezado // 2),
                texto,
                fill="#000000",
                font=fuente_encabezado,
                anchor="mm",
            )

        y_actual += alto_encabezado
        for hora in horas:
            for columna in range(8):
                izquierda, derecha = limites_x[columna : columna + 2]
                dibujo.rectangle(
                    (izquierda, y_actual, derecha, y_actual + alto_fila),
                    fill="#ffffff",
                    outline=COLOR_BORDE,
                    width=2,
                )
                if columna == 0:
                    dibujo.text(
                        ((izquierda + derecha) // 2, y_actual + alto_fila // 2),
                        f"{hora:02d}:00-{hora + 1:02d}:00",
                        fill=COLOR_TEXTO,
                        font=fuente_celda,
                        anchor="mm",
                    )
                elif (columna, hora) in bloques_marcados:
                    dibujar_check_azul(
                        dibujo,
                        (izquierda + derecha) // 2,
                        y_actual + alto_fila // 2,
                        tamaño=40,
                        color=COLOR_AZUL_CHECK,
                        grosor=5,
                    )
            y_actual += alto_fila

        for columna in range(8):
            izquierda, derecha = limites_x[columna : columna + 2]
            dibujo.rectangle(
                (
                    izquierda,
                    y_actual,
                    derecha,
                    y_actual + alto_fila_total,
                ),
                fill=COLOR_ENCABEZADO,
                outline=COLOR_BORDE,
                width=2,
            )
            texto_total = (
                "TOTAL"
                if columna == 0
                else str(
                    sum(
                        1
                        for dia_bloque, _ in bloques_marcados
                        if dia_bloque == columna
                    )
                )
            )
            dibujo.text(
                ((izquierda + derecha) // 2, y_actual + alto_fila_total // 2),
                texto_total,
                fill="#000000",
                font=fuente_encabezado,
                anchor="mm",
            )

        total_semanal = len(bloques_marcados)
        dibujo.text(
            (ANCHO_IMAGEN - MARGEN, y_actual + alto_fila_total + 55),
            f"Total semanal: {total_semanal} horas",
            fill=COLOR_TEXTO,
            font=fuente_total,
            anchor="rm",
        )

        imagen.save(
            buffer,
            format="PNG",
            optimize=True,
            dpi=(DPI_IMPRESION, DPI_IMPRESION),
        )
        return buffer.getvalue()
    finally:
        if logo_redimensionado is not None:
            logo_redimensionado.close()
        if logo is not None:
            logo.close()
        imagen.close()
        buffer.close()
