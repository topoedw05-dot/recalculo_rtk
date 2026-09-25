# -*- coding: utf-8 -*-
"""
core.py
=======

Funciones puras (sin dependencias de QGIS/PyQt) para el recálculo de
coordenadas topográficas desde una base RTK de coordenadas "libres"
(asumidas en campo) hacia las coordenadas "ajustadas" que resultan del
postproceso estático de esa misma base.

Fundamento del método
----------------------
Cuando se levanta una red con RTK usando una sola base, el equipo rover
calcula, para cada punto, un vector de línea base (ΔX, ΔY, ΔZ) respecto
a la base, a partir de la solución de fase portadora. Ese vector no
depende de qué coordenada se le haya asignado a la base en el momento
del levantamiento: depende solo de la geometría real entre la base y el
punto. Por lo tanto, si la base tenía inicialmente una coordenada libre
(arbitraria o autónoma) y luego, mediante postproceso estático, se
obtiene su coordenada ajustada (ligada a la red de referencia, p. ej.
MAGNA-SIRGAS), la coordenada correcta de cualquier punto radiado es:

    punto_ajustado = punto_libre + (base_ajustada - base_libre)

Es decir, una traslación rígida (mismo desplazamiento dx, dy, dz para
todos los puntos), sin rotación ni escala. Esta aproximación es válida
para el caso típico de una sola base y radiaciones RTK de corta/mediana
distancia, que es el escenario que resuelve este complemento.

Este módulo se mantiene independiente de QGIS para poder probarlo con
Python estándar (ver test_core.py) sin necesidad de arrancar la
aplicación.
"""

import csv
import html
import os

try:
    from . import i18n
except ImportError:
    # Permite ejecutar/importar este módulo de forma independiente (p. ej.
    # "import core" desde test_core.py, sin contexto de paquete de QGIS).
    import i18n


class FilaInvalidaError(ValueError):
    """Error al interpretar una fila del CSV de entrada."""


def parse_float(value):
    """Convierte un texto a ``float``.

    Acepta tanto separador decimal punto ("123.45") como coma
    ("123,45"). Lanza ``ValueError`` si el texto no puede
    interpretarse como número.
    """
    if value is None:
        raise ValueError("Valor vacío")
    text = str(value).strip()
    if text == "":
        raise ValueError("Valor vacío")
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return float(text.replace(",", "."))
    except ValueError:
        raise ValueError("No se pudo interpretar '{}' como número".format(value))


def compute_delta(base_libre, base_ajustada):
    """Calcula el vector de traslación (dx, dy, dz).

    ``base_libre`` y ``base_ajustada`` son tuplas ``(X, Y, Z)``. ``Z``
    puede ser ``None`` en ambos casos si no se dispone de elevación;
    en ese caso ``dz`` retorna ``None`` y no debe aplicarse corrección
    de elevación.
    """
    x0, y0, z0 = base_libre
    x1, y1, z1 = base_ajustada
    dx = x1 - x0
    dy = y1 - y0
    if z0 is None or z1 is None:
        dz = None
    else:
        dz = z1 - z0
    return dx, dy, dz


def read_csv_rows(path, encodings=("utf-8-sig", "latin-1", "cp1252")):
    """Lee un CSV delimitado por comas.

    Retorna ``(encabezados, filas)`` donde ``encabezados`` es la
    primera fila (lista de nombres de columna) y ``filas`` es la lista
    de las filas restantes (cada una, una lista de textos).

    Prueba varias codificaciones comunes en archivos exportados desde
    Excel/Access en Colombia, ya que no siempre son UTF-8.
    """
    last_error = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.reader(f, delimiter=",")
                rows = [row for row in reader if row != []]
            if not rows:
                return [], []
            header = rows[0]
            data = rows[1:]
            return header, data
        except (UnicodeDecodeError, UnicodeError) as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise IOError("No se pudo leer el archivo: {}".format(path))


def write_csv_rows(path, header, rows, encoding="utf-8-sig"):
    """Escribe un CSV delimitado por comas con encabezado y filas."""
    with open(path, "w", encoding=encoding, newline="") as f:
        writer = csv.writer(f, delimiter=",")
        writer.writerow(header)
        writer.writerows(rows)


def sugerir_ruta_con_extension(ruta_base, nueva_extension):
    """A partir de una ruta de archivo (p. ej. la del CSV de salida),
    sugiere una ruta hermana con otra extensión, p. ej.
    ``sugerir_ruta_con_extension("C:/datos/salida.csv", ".shp")`` ->
    ``"C:/datos/salida.shp"``.

    ``nueva_extension`` puede incluir o no el punto inicial.
    """
    if not nueva_extension.startswith("."):
        nueva_extension = "." + nueva_extension
    base, _ext = os.path.splitext(ruta_base)
    return base + nueva_extension


def etiqueta_punto(id_valor, numero_fila):
    """Etiqueta de texto para un punto, usada como nombre visible y
    como campo "Text" en la exportación a DXF (convención del driver
    DXF de OGR/GDAL: una entidad de texto se dibuja junto al punto
    cuando la capa tiene un campo llamado exactamente "Text").

    Usa el valor de la columna ID si se proporcionó y no está vacío;
    si no, arma un identificador secuencial "P<numero_fila>".
    """
    if id_valor is not None:
        texto = str(id_valor).strip()
        if texto:
            return texto
    return "P{}".format(numero_fila)


def recalcular_filas(header, rows, idx_x, idx_y, idx_z, dx, dy, dz):
    """Aplica la traslación (dx, dy, dz) a cada fila del CSV.

    ``idx_x``/``idx_y`` son obligatorios (índices de columna, base 0).
    ``idx_z`` puede ser ``None`` si el CSV no trae elevación.

    Retorna una lista de diccionarios, uno por fila procesada
    correctamente, con las llaves:
        'fila'      -> número de fila original (1 = primera fila de datos)
        'original'  -> lista de valores originales de la fila
        'x'         -> X original (float)
        'y'         -> Y original (float)
        'z'         -> Z original (float) o None
        'x_adj'     -> X ajustada (float)
        'y_adj'     -> Y ajustada (float)
        'z_adj'     -> Z ajustada (float) o None

    y una segunda lista con los errores encontrados, como tuplas
    ``(numero_de_fila, mensaje)``. Las filas con error se omiten del
    resultado principal pero no detienen el proceso.
    """
    resultados = []
    errores = []
    for i, row in enumerate(rows, start=1):
        try:
            if idx_x >= len(row) or idx_y >= len(row):
                raise FilaInvalidaError("La fila no tiene suficientes columnas")
            x = parse_float(row[idx_x])
            y = parse_float(row[idx_y])
            z = None
            if idx_z is not None:
                if idx_z >= len(row):
                    raise FilaInvalidaError("La fila no tiene columna de elevación")
                z_text = row[idx_z]
                z = parse_float(z_text) if str(z_text).strip() != "" else None
        except ValueError as exc:
            errores.append((i, str(exc)))
            continue

        x_adj = x + dx
        y_adj = y + dy
        if z is not None and dz is not None:
            z_adj = z + dz
        else:
            z_adj = None

        resultados.append({
            "fila": i,
            "original": row,
            "x": x,
            "y": y,
            "z": z,
            "x_adj": x_adj,
            "y_adj": y_adj,
            "z_adj": z_adj,
        })
    return resultados, errores


def _fmt_num(valor, decimales=4):
    """Formatea un número con ``decimales`` cifras, o "N/A" si es
    ``None`` o no es un número interpretable."""
    if valor is None or valor == "":
        return "N/A"
    try:
        return "{:.{}f}".format(float(valor), decimales)
    except (TypeError, ValueError):
        return str(valor)


def _esc(valor):
    """Escapa texto para insertarlo de forma segura dentro del HTML del
    reporte (evita que un ID u otro dato del CSV con "<", ">" o "&"
    rompa el documento)."""
    if valor is None:
        return ""
    return html.escape(str(valor))


def _dms(valor_decimal, es_longitud=False, decimales=5, idioma=i18n.IDIOMA_DEFECTO):
    """Convierte un valor en grados decimales a formato grados-minutos-
    segundos, p. ej. ``74°12'34.12345"O``. ``decimales`` fija la
    precisión de los segundos. Retorna "N/A" si el valor es ``None`` o
    no puede interpretarse como número.

    El sufijo de hemisferio depende de ``idioma``: longitud
    Oeste/Este (O/E en español, W/E en inglés, O/L en portugués) y
    latitud Norte/Sur (N/S en los tres).
    """
    if valor_decimal is None or valor_decimal == "":
        return "N/A"
    try:
        valor = float(valor_decimal)
    except (TypeError, ValueError):
        return "N/A"

    sufijo = i18n.sufijo_hemisferio(idioma, es_longitud, valor >= 0)

    valor_abs = abs(valor)
    grados = int(valor_abs)
    resto_minutos = (valor_abs - grados) * 60
    minutos = int(resto_minutos)
    segundos = round((resto_minutos - minutos) * 60, decimales)

    # El redondeo de los segundos puede empujarlos a 60 (o los minutos a
    # 60), hay que propagar el acarreo.
    if segundos >= 60:
        segundos -= 60
        minutos += 1
    if minutos >= 60:
        minutos -= 60
        grados += 1

    return "{}°{:02d}'{:0{ancho}.{dec}f}\"{}".format(
        grados, minutos, segundos, sufijo, ancho=decimales + 3, dec=decimales
    )


def _fmt_crs_num(valor):
    """Formatea un parámetro numérico de un CRS (falso este, factor de
    escala, semieje, etc.) mostrando el valor "tal cual" es internamente
    (igual que hacen QGIS/ArcGIS en sus paneles de propiedades de CRS:
    "5000000.0", "0.9992", "298.257222101"), en vez de redondearlo a una
    cantidad fija de decimales que le haría perder precisión o le
    agregaría ceros de más."""
    if valor is None or valor == "":
        return "N/D"
    try:
        return repr(float(valor))
    except (TypeError, ValueError):
        return _esc(valor)


def _filas_pcs_html(pcs, idioma=i18n.IDIOMA_DEFECTO):
    """Filas <tr> (atributo/valor) con el detalle de un sistema de
    coordenadas PROYECTADO (nombre, proyección, EPSG, unidades,
    parámetros de la proyección y área de uso), a partir del dict que
    arma ``_describir_crs_detallado`` en recalculo_dialog.py."""
    if not pcs:
        return ""
    nd = i18n.tr(idioma, "crs_nd")
    filas = [
        (i18n.tr(idioma, "crs_nombre"), _esc(pcs.get("nombre") or nd)),
        (i18n.tr(idioma, "crs_proyeccion"), _esc(pcs.get("proyeccion") or nd)),
        (i18n.tr(idioma, "crs_wkid"), _esc(pcs.get("wkid") or nd)),
        (i18n.tr(idioma, "crs_autoridad"), _esc(pcs.get("autoridad") or nd)),
        (i18n.tr(idioma, "crs_unidad_lineal"), "{} ({})".format(
            i18n.nombre_unidad(idioma, pcs.get("unidad_nombre")), _fmt_crs_num(pcs.get("unidad_factor")))),
        (i18n.tr(idioma, "crs_false_easting"), _fmt_crs_num(pcs.get("false_easting"))),
        (i18n.tr(idioma, "crs_false_northing"), _fmt_crs_num(pcs.get("false_northing"))),
        (i18n.tr(idioma, "crs_meridiano_central"), _fmt_crs_num(pcs.get("meridiano_central"))),
        (i18n.tr(idioma, "crs_factor_escala"), _fmt_crs_num(pcs.get("factor_escala"))),
        (i18n.tr(idioma, "crs_latitud_origen"), _fmt_crs_num(pcs.get("latitud_origen"))),
    ]
    if pcs.get("area_uso"):
        filas.append((i18n.tr(idioma, "crs_area_uso"), _esc(pcs["area_uso"])))
    return "".join(
        '<tr><td class="etq">{}</td><td>{}</td></tr>'.format(k, v) for k, v in filas
    )


def _filas_gcs_html(gcs, idioma=i18n.IDIOMA_DEFECTO):
    """Igual que ``_filas_pcs_html`` pero para el sistema de coordenadas
    GEOGRÁFICO base (datum, esferoide, primer meridiano, unidad
    angular)."""
    if not gcs:
        return ""
    nd = i18n.tr(idioma, "crs_nd")
    filas = [
        (i18n.tr(idioma, "crs_nombre"), _esc(gcs.get("nombre") or nd)),
        (i18n.tr(idioma, "crs_wkid"), _esc(gcs.get("wkid") or nd)),
        (i18n.tr(idioma, "crs_autoridad"), _esc(gcs.get("autoridad") or nd)),
        (i18n.tr(idioma, "crs_unidad_angular"), "{} ({})".format(
            i18n.nombre_unidad(idioma, gcs.get("unidad_nombre")), _fmt_crs_num(gcs.get("unidad_factor")))),
        (i18n.tr(idioma, "crs_primer_meridiano"), "{} ({})".format(
            _esc(gcs.get("primer_meridiano_nombre") or nd),
            _fmt_crs_num(gcs.get("primer_meridiano_valor")))),
        (i18n.tr(idioma, "crs_datum"), _esc(gcs.get("datum") or nd)),
        (i18n.tr(idioma, "crs_esferoide"), _esc(gcs.get("esferoide_nombre") or nd)),
        (i18n.tr(idioma, "crs_semieje_mayor"), _fmt_crs_num(gcs.get("semieje_mayor"))),
        (i18n.tr(idioma, "crs_semieje_menor"), _fmt_crs_num(gcs.get("semieje_menor"))),
        (i18n.tr(idioma, "crs_aplanamiento_inverso"), _fmt_crs_num(gcs.get("aplanamiento_inverso"))),
    ]
    if gcs.get("area_uso"):
        filas.append((i18n.tr(idioma, "crs_area_uso"), _esc(gcs["area_uso"])))
    return "".join(
        '<tr><td class="etq">{}</td><td>{}</td></tr>'.format(k, v) for k, v in filas
    )


def _tarjeta_crs_html(titulo, detalle, idioma=i18n.IDIOMA_DEFECTO):
    """Arma la "tarjeta" HTML con el detalle completo de un CRS para la
    sección "Sistemas de referencia": un sistema proyectado (si aplica)
    y su sistema geográfico base, con todos sus atributos — equivalente
    al panel de propiedades de un CRS en QGIS/ArcGIS.

    Acepta tres formas de ``detalle``, de más a menos completa:
      1. El dict nuevo de ``_describir_crs_detallado``: llaves
         'proyectado' (dict o None) y 'geografico' (dict).
      2. El dict simple anterior (nombre/authid/unidades/...), usado
         como respaldo si GDAL no estaba disponible al generar el
         reporte.
      3. Un texto simple (p. ej. "EPSG:9377"), o None.
    """
    nd = i18n.tr(idioma, "crs_nd")
    cuerpo = ""
    if isinstance(detalle, dict) and "geografico" in detalle:
        pcs = detalle.get("proyectado")
        gcs = detalle.get("geografico")
        if pcs:
            cuerpo += (
                '<p class="subtabla">{}</p>'
                '<table class="detalle-crs">{}</table>'.format(
                    i18n.tr(idioma, "crs_subtabla_proyectado"), _filas_pcs_html(pcs, idioma))
            )
        if gcs:
            cuerpo += (
                '<p class="subtabla">{}</p>'
                '<table class="detalle-crs">{}</table>'.format(
                    i18n.tr(idioma, "crs_subtabla_geografico"), _filas_gcs_html(gcs, idioma))
            )
    elif isinstance(detalle, dict):
        # Respaldo: forma simple (sin GDAL disponible).
        nombre = detalle.get("nombre") or ""
        authid = detalle.get("authid") or ""
        nombre_epsg = "{} ({})".format(_esc(nombre), _esc(authid)) if (nombre and authid) \
            else _esc(nombre or authid or nd)
        filas = [(i18n.tr(idioma, "crs_nombre_epsg"), nombre_epsg)]
        if detalle.get("unidades"):
            filas.append((i18n.tr(idioma, "crs_unidades"), _esc(detalle["unidades"])))
        if detalle.get("estatico") is not None:
            filas.append((i18n.tr(idioma, "crs_datum"),
                          i18n.tr(idioma, "crs_datum_estatico") if detalle["estatico"]
                          else i18n.tr(idioma, "crs_datum_dinamico")))
        if detalle.get("cuerpo_celeste"):
            filas.append((i18n.tr(idioma, "crs_cuerpo_celeste"), _esc(detalle["cuerpo_celeste"])))
        if detalle.get("metodo"):
            filas.append((i18n.tr(idioma, "crs_metodo_proyeccion"), _esc(detalle["metodo"])))
        cuerpo = '<table class="detalle-crs">{}</table>'.format("".join(
            '<tr><td class="etq">{}</td><td>{}</td></tr>'.format(k, v) for k, v in filas
        ))
    elif detalle:
        cuerpo = '<table class="detalle-crs"><tr><td class="etq">{}</td><td>{}</td></tr></table>'.format(
            i18n.tr(idioma, "crs_nombre"), _esc(detalle))
    else:
        cuerpo = '<p class="nota">{}</p>'.format(i18n.tr(idioma, "crs_no_disponible"))

    return '<div class="tarjeta-crs"><h3>{}</h3>{}</div>'.format(_esc(titulo), cuerpo)


def construir_reporte_html(info):
    """Arma el contenido HTML del reporte técnico de recálculo RTK — una
    página HTML autocontenida (sin dependencias externas: todo el CSS va
    incluido), pensada para abrirse directamente con un navegador.

    ``info`` es un diccionario con las llaves:
        'fecha'              -> texto ya formateado (p. ej. "2026-09-22 10:15")
        'version_plugin'     -> texto de la versión del complemento
        'proyecto'           -> texto opcional (o None/"")
        'responsable'        -> texto opcional (o None/"")
        'archivo_entrada'    -> ruta/nombre del CSV de entrada
        'archivo_salida'     -> ruta del CSV de salida generado
        'base_libre'         -> tupla (x, y, z) — z puede ser None
        'base_ajustada'      -> tupla (x, y, z) — z puede ser None
        'dx', 'dy', 'dz'     -> vector de traslación calculado (dz puede ser None)
        'crs_plano'          -> dict con el detalle completo del CRS plano/proyectado
                                 (ver ``_describir_crs_detallado`` en recalculo_dialog.py:
                                 llaves 'proyectado' y 'geografico'); también acepta, como
                                 respaldo, el dict simple anterior o un texto (p. ej. "EPSG:9377")
        'crs_geo'            -> mismo formato que 'crs_plano', para el CRS geográfico de salida
        'total_filas'        -> número total de filas de datos del CSV de entrada
        'procesados'         -> número de puntos recalculados correctamente
        'errores'            -> lista de tuplas (numero_fila, mensaje) omitidas por error
        'errores_transform'  -> número de puntos que no pudieron reproyectarse
        'puntos'             -> lista de dicts, cada uno con:
                                 'etiqueta', 'x', 'y', 'z', 'x_adj', 'y_adj', 'z_adj',
                                 'lon' (o None), 'lat' (o None)
        'idioma'             -> código de idioma opcional del reporte ('es', 'en',
                                 'pt_BR'; ver i18n.py); si se omite, se usa
                                 i18n.IDIOMA_DEFECTO ('es')

    Devuelve un string HTML autocontenido y completo (con su propio
    ``<!DOCTYPE html>``), listo para escribirse directamente a un
    archivo .html. No depende de QGIS ni de PyQt, así que se puede
    probar con Python estándar.
    """
    idioma = info.get("idioma") or i18n.IDIOMA_DEFECTO

    def _t(clave, **kwargs):
        return i18n.tr(idioma, clave, **kwargs)

    bx, by, bz = info["base_libre"]
    ax, ay, az = info["base_ajustada"]
    dx, dy, dz = info["dx"], info["dy"], info["dz"]

    proyecto = _esc(info.get("proyecto") or "")
    responsable = _esc(info.get("responsable") or "")
    omitidos = len(info.get("errores") or [])

    filas_meta = [
        (_t("rpt_fecha"), _esc(info.get("fecha", ""))),
        (_t("rpt_complemento"), "{} (v{})".format(
            _t("rpt_nombre_plugin"), _esc(info.get("version_plugin", "")))),
        (_t("rpt_archivo_entrada"), _esc(os.path.basename(str(info.get("archivo_entrada", ""))))),
        (_t("rpt_archivo_salida"), _esc(os.path.basename(str(info.get("archivo_salida", ""))))),
    ]
    if proyecto:
        filas_meta.insert(0, (_t("rpt_proyecto"), proyecto))
    if responsable:
        filas_meta.insert(1 if proyecto else 0, (_t("rpt_responsable"), responsable))

    filas_meta_html = "".join(
        '<tr><td class="etq">{}</td><td>{}</td></tr>'.format(k, v) for k, v in filas_meta
    )

    filas_bases_html = """
      <tr><th>{h_base}</th><th>{h_x}</th><th>{h_y}</th><th>{h_z}</th></tr>
      <tr><td>{fila_libre}</td><td>{bx}</td><td>{by}</td><td>{bz}</td></tr>
      <tr><td>{fila_ajustada}</td><td>{ax}</td><td>{ay}</td><td>{az}</td></tr>
      <tr><td><b>{fila_vector}</b></td><td><b>{dx}</b></td><td><b>{dy}</b></td><td><b>{dz}</b></td></tr>
    """.format(
        h_base=_t("rpt_tabla_base_header_base"), h_x=_t("rpt_tabla_base_header_x"),
        h_y=_t("rpt_tabla_base_header_y"), h_z=_t("rpt_tabla_base_header_z"),
        fila_libre=_t("rpt_base_libre_row"), fila_ajustada=_t("rpt_base_ajustada_row"),
        fila_vector=_t("rpt_vector_row"),
        bx=_fmt_num(bx), by=_fmt_num(by), bz=_fmt_num(bz),
        ax=_fmt_num(ax), ay=_fmt_num(ay), az=_fmt_num(az),
        dx=_fmt_num(dx), dy=_fmt_num(dy), dz=_fmt_num(dz),
    )

    # Sección 1: una "tarjeta" con el detalle completo por cada CRS (el
    # plano/proyectado usado en X,Y y el geográfico usado en Lon/Lat),
    # con nombre, proyección, EPSG, unidades, parámetros de la
    # proyección, datum, esferoide y área de uso — equivalente al panel
    # de propiedades/detalle de un CRS en QGIS o ArcGIS.
    tarjetas_crs_html = (
        _tarjeta_crs_html(_t("rpt_crs_plano_titulo"), info.get("crs_plano"), idioma)
        + _tarjeta_crs_html(_t("rpt_crs_geo_titulo"), info.get("crs_geo"), idioma)
    )

    filas_puntos_html = []
    for i, p in enumerate(info.get("puntos") or []):
        clase_fila = ' class="par"' if i % 2 == 1 else ""
        filas_puntos_html.append(
            "<tr{clase}><td>{etq}</td><td>{x}</td><td>{y}</td><td>{z}</td>"
            "<td>{xa}</td><td>{ya}</td><td>{za}</td><td>{lon}</td><td>{lat}</td></tr>".format(
                clase=clase_fila,
                etq=_esc(p.get("etiqueta", "")),
                x=_fmt_num(p.get("x"), 3), y=_fmt_num(p.get("y"), 3), z=_fmt_num(p.get("z"), 3),
                xa=_fmt_num(p.get("x_adj"), 3), ya=_fmt_num(p.get("y_adj"), 3), za=_fmt_num(p.get("z_adj"), 3),
                lon=_dms(p.get("lon"), es_longitud=True, idioma=idioma),
                lat=_dms(p.get("lat"), es_longitud=False, idioma=idioma),
            )
        )

    errores_html = ""
    errores = info.get("errores") or []
    if errores:
        items = "".join(
            "<li>{}</li>".format(_t("rpt_errores_item", num=num, msg=_esc(msg))) for num, msg in errores
        )
        errores_html = (
            '<h2>{}</h2><ul>{}</ul>'.format(_t("rpt_errores_h2"), items)
        )

    titulo_pagina = _t("rpt_titulo")
    if info.get("proyecto"):
        titulo_pagina += " — {}".format(info["proyecto"])

    html_doc = """<!DOCTYPE html>
<html lang="{lang_html}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo_pagina}</title>
<style>
    :root {{
        --azul: #1f3864;
        --azul-claro: #dde6f0;
        --borde: #c3cbd6;
        --texto: #202632;
        --texto-suave: #5a6472;
    }}
    * {{ box-sizing: border-box; }}
    body {{
        font-family: "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
        font-size: 15px; color: var(--texto); margin: 0;
        background: #eef1f5;
    }}
    .hoja {{
        max-width: 1100px; margin: 0 auto; background: #ffffff;
        padding: 36px 48px 48px; box-shadow: 0 1px 4px rgba(0,0,0,0.12);
    }}
    h1 {{
        font-size: 26px; text-align: center; text-transform: uppercase;
        letter-spacing: 1px; color: var(--azul); margin: 0 0 8px 0;
    }}
    .linea-titulo {{
        height: 3px; background: var(--azul); width: 120px; margin: 0 auto 14px;
        border-radius: 2px;
    }}
    .subtitulo {{
        text-align: center; color: var(--texto-suave); font-size: 15px;
        margin: 0 0 30px 0; font-style: italic;
    }}
    h2 {{
        font-size: 18px; text-align: center; text-transform: uppercase;
        letter-spacing: 0.5px; color: var(--azul);
        margin: 42px 0 16px 0; padding-bottom: 8px;
        border-bottom: 2px solid var(--azul-claro);
    }}
    h3 {{
        font-size: 15px; text-transform: uppercase; letter-spacing: 0.3px;
        color: var(--azul); margin: 0 0 10px 0;
    }}
    table {{ border-collapse: collapse; width: 100%; margin: 8px 0 20px 0; }}
    th, td {{ border: 1px solid var(--borde); padding: 8px 12px; text-align: left; font-size: 14px; }}
    th {{ background: var(--azul-claro); color: var(--azul); }}
    td.etq {{ background: #f6f7f9; width: 30%; font-weight: 600; color: #3a4453; }}
    .resumen td {{ padding: 9px 12px; }}

    .tarjetas-crs {{
        display: grid; grid-template-columns: 1fr 1fr; gap: 24px;
        margin: 8px 0 20px 0;
    }}
    .tarjeta-crs {{
        border: 1px solid var(--borde); border-radius: 8px; padding: 18px 20px;
        background: #fbfcfd;
    }}
    .tarjeta-crs .subtabla {{
        font-size: 13px; font-weight: 600; text-transform: uppercase;
        color: var(--texto-suave); margin: 16px 0 6px 0; letter-spacing: 0.3px;
    }}
    .tarjeta-crs .subtabla:first-of-type {{ margin-top: 0; }}
    table.detalle-crs {{ margin: 0 0 4px 0; }}
    table.detalle-crs td {{ font-size: 13.5px; padding: 6px 10px; }}
    table.detalle-crs td.etq {{ width: 44%; }}

    .puntos-wrap {{ overflow-x: auto; }}
    table.puntos {{ min-width: 900px; }}
    table.puntos th {{ background: var(--azul); color: #ffffff; white-space: nowrap; }}
    table.puntos td {{ font-size: 13.5px; white-space: nowrap; }}
    table.puntos tr:nth-child(even) td {{ background: #f2f5f9; }}

    .nota {{ color: var(--texto-suave); font-size: 13px; margin: -10px 0 16px 0; }}
    .cierre {{
        text-align: center; color: #97a0ac; font-size: 13px;
        margin-top: 26px; border-top: 1px solid #e2e6ea; padding-top: 12px;
    }}
    @media (max-width: 800px) {{
        .hoja {{ padding: 24px 18px; }}
        .tarjetas-crs {{ grid-template-columns: 1fr; }}
    }}
    @media print {{
        body {{ background: #ffffff; }}
        .hoja {{ box-shadow: none; max-width: none; padding: 0; }}
        .pagebreak {{ page-break-before: always; }}
        table.puntos {{ min-width: 0; }}
    }}
</style>
</head>
<body>
<div class="hoja">
    <h1>{h1_titulo}</h1>
    <div class="linea-titulo"></div>
    <p class="subtitulo">{subtitulo}</p>

    <table>{filas_meta_html}</table>

    <h2>{h2_1}</h2>
    <div class="tarjetas-crs">
        {tarjetas_crs_html}
    </div>

    <h2>{h2_2}</h2>
    <table>{filas_bases_html}</table>
    <p>{metodo_parrafo}</p>

    <h2>{h2_3}</h2>
    <table class="resumen">
        <tr><td class="etq">{resumen_filas_csv}</td><td>{total_filas}</td></tr>
        <tr><td class="etq">{resumen_procesados}</td><td>{procesados}</td></tr>
        <tr><td class="etq">{resumen_omitidos}</td><td>{omitidos}</td></tr>
        <tr><td class="etq">{resumen_errores_transform}</td><td>{errores_transform}</td></tr>
    </table>
    {errores_html}

    <div class="pagebreak"></div>
    <h2>{h2_4}</h2>
    <p class="nota">{nota_puntos}</p>
    <div class="puntos-wrap">
    <table class="puntos">
        <tr>
            <th>{col_punto}</th><th>{col_x}</th><th>{col_y}</th><th>{col_z}</th>
            <th>{col_x_adj}</th><th>{col_y_adj}</th><th>{col_z_adj}</th>
            <th>{col_lon}</th><th>{col_lat}</th>
        </tr>
        {filas_puntos_html}
    </table>
    </div>
    <p class="cierre">{cierre}</p>
</div>
</body>
</html>
""".format(
        lang_html=i18n.lang_html(idioma),
        titulo_pagina=_esc(titulo_pagina),
        h1_titulo=_esc(_t("rpt_titulo")),
        subtitulo=_t("rpt_subtitulo"),
        filas_meta_html=filas_meta_html,
        h2_1=_t("rpt_h2_1"), h2_2=_t("rpt_h2_2"), h2_3=_t("rpt_h2_3"), h2_4=_t("rpt_h2_4"),
        tarjetas_crs_html=tarjetas_crs_html,
        filas_bases_html=filas_bases_html,
        metodo_parrafo=_t("rpt_metodo_parrafo"),
        resumen_filas_csv=_t("rpt_resumen_filas_csv"),
        resumen_procesados=_t("rpt_resumen_procesados"),
        resumen_omitidos=_t("rpt_resumen_omitidos"),
        resumen_errores_transform=_t("rpt_resumen_errores_transform"),
        total_filas=info.get("total_filas", 0),
        procesados=info.get("procesados", 0),
        omitidos=omitidos,
        errores_transform=info.get("errores_transform", 0),
        errores_html=errores_html,
        nota_puntos=_t("rpt_nota_puntos"),
        col_punto=_t("rpt_col_punto"), col_x=_t("rpt_col_x"), col_y=_t("rpt_col_y"), col_z=_t("rpt_col_z"),
        col_x_adj=_t("rpt_col_x_adj"), col_y_adj=_t("rpt_col_y_adj"), col_z_adj=_t("rpt_col_z_adj"),
        col_lon=_t("rpt_col_lon"), col_lat=_t("rpt_col_lat"),
        filas_puntos_html="".join(filas_puntos_html),
        cierre=_t("rpt_cierre", nombre_plugin=_t("rpt_nombre_plugin"), version=_esc(info.get("version_plugin", ""))),
        version_plugin=_esc(info.get("version_plugin", "")),
    )
    return html_doc
