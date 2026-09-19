# -*- coding: utf-8 -*-
"""
test_core.py
============

Pruebas de la lógica pura de recálculo (core.py), ejecutables con
Python estándar, SIN necesidad de arrancar QGIS.

Ejecutar con:  python3 test_core.py
"""

import os
import sys
import tempfile

import core


def test_parse_float():
    assert core.parse_float("123.45") == 123.45
    assert core.parse_float("123,45") == 123.45
    assert core.parse_float(" 100 ") == 100.0
    try:
        core.parse_float("")
        raise AssertionError("Debia fallar con texto vacio")
    except ValueError:
        pass
    try:
        core.parse_float("abc")
        raise AssertionError("Debia fallar con texto no numerico")
    except ValueError:
        pass
    print("OK: test_parse_float")


def test_compute_delta():
    base_libre = (1000000.000, 1000000.000, 2600.000)
    base_ajustada = (1000000.500, 999999.800, 2600.120)
    dx, dy, dz = core.compute_delta(base_libre, base_ajustada)
    assert abs(dx - 0.500) < 1e-9
    assert abs(dy - (-0.200)) < 1e-9
    assert abs(dz - 0.120) < 1e-9

    # Sin elevacion
    dx2, dy2, dz2 = core.compute_delta((0, 0, None), (1, 1, None))
    assert dz2 is None
    print("OK: test_compute_delta")


def test_csv_roundtrip_and_recalculo():
    header, rows = core.read_csv_rows(os.path.join(os.path.dirname(__file__), "puntos_ejemplo.csv"))
    assert header == ["ID", "Este", "Norte", "Elevacion", "Descripcion"]
    assert len(rows) == 5  # incluye la fila con error intencional

    base_libre = (1000000.000, 1000000.000, 2600.000)
    base_ajustada = (1000000.500, 999999.800, 2600.120)
    dx, dy, dz = core.compute_delta(base_libre, base_ajustada)

    idx_x, idx_y, idx_z = 1, 2, 3
    resultados, errores = core.recalcular_filas(header, rows, idx_x, idx_y, idx_z, dx, dy, dz)

    # La fila P5 tiene el Este vacio -> debe reportarse como error y no
    # aparecer en resultados.
    assert len(resultados) == 4
    assert len(errores) == 1
    assert errores[0][0] == 5  # quinta fila de datos

    # Verificar que la traslacion se aplico correctamente al primer punto
    p1 = resultados[0]
    assert abs(p1["x_adj"] - (1000000.000 + dx)) < 1e-9
    assert abs(p1["y_adj"] - (1000000.000 + dy)) < 1e-9
    assert abs(p1["z_adj"] - (2600.000 + dz)) < 1e-9

    # Escribir y releer el CSV de salida para validar write_csv_rows
    with tempfile.TemporaryDirectory() as tmp:
        out_path = os.path.join(tmp, "salida.csv")
        nuevo_header = header + ["X_ajustada", "Y_ajustada", "Z_ajustada"]
        filas_salida = []
        for r in resultados:
            filas_salida.append(list(r["original"]) + [
                "{:.4f}".format(r["x_adj"]),
                "{:.4f}".format(r["y_adj"]),
                "{:.4f}".format(r["z_adj"]),
            ])
        core.write_csv_rows(out_path, nuevo_header, filas_salida)

        header2, rows2 = core.read_csv_rows(out_path)
        assert header2 == nuevo_header
        assert len(rows2) == 4
        assert rows2[0][0] == "P1"

    print("OK: test_csv_roundtrip_and_recalculo")


def test_sugerir_ruta_con_extension():
    assert core.sugerir_ruta_con_extension("C:/datos/salida.csv", ".shp") == "C:/datos/salida.shp"
    assert core.sugerir_ruta_con_extension("/home/user/salida.csv", "dxf") == "/home/user/salida.dxf"
    assert core.sugerir_ruta_con_extension("salida", ".shp") == "salida.shp"
    print("OK: test_sugerir_ruta_con_extension")


def test_etiqueta_punto():
    assert core.etiqueta_punto("P1", 5) == "P1"
    assert core.etiqueta_punto("", 5) == "P5"
    assert core.etiqueta_punto(None, 3) == "P3"
    assert core.etiqueta_punto("  PR-1  ", 2) == "PR-1"
    print("OK: test_etiqueta_punto")


def test_traslacion_es_igual_para_todos_los_puntos():
    """Verifica la propiedad central del metodo: el desplazamiento
    aplicado (X_ajustada - X_original) es identico para todos los
    puntos (es una traslacion rigida, no depende del punto)."""
    header, rows = core.read_csv_rows(os.path.join(os.path.dirname(__file__), "puntos_ejemplo.csv"))
    base_libre = (1000000.000, 1000000.000, 2600.000)
    base_ajustada = (1000000.500, 999999.800, 2600.120)
    dx, dy, dz = core.compute_delta(base_libre, base_ajustada)
    resultados, _ = core.recalcular_filas(header, rows, 1, 2, 3, dx, dy, dz)

    for r in resultados:
        assert abs((r["x_adj"] - r["x"]) - dx) < 1e-9
        assert abs((r["y_adj"] - r["y"]) - dy) < 1e-9
        assert abs((r["z_adj"] - r["z"]) - dz) < 1e-9
    print("OK: test_traslacion_es_igual_para_todos_los_puntos")


if __name__ == "__main__":
    test_parse_float()
    test_compute_delta()
    test_csv_roundtrip_and_recalculo()
    test_sugerir_ruta_con_extension()
    test_etiqueta_punto()
    test_traslacion_es_igual_para_todos_los_puntos()
    print("\nTodas las pruebas pasaron correctamente.")
