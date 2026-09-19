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
import os


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
