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
import i18n


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


def test_dms():
    # Longitud negativa (Oeste) y latitud positiva (Norte), caso típico
    # en Colombia.
    assert core._dms(-74.123456789, es_longitud=True) == '74°07\'24.44444"O'
    assert core._dms(4.123456789, es_longitud=False) == '4°07\'24.44444"N'
    assert core._dms(None) == "N/A"
    assert core._dms("") == "N/A"
    assert core._dms("no-numero") == "N/A"
    # Acarreo de segundos/minutos al redondear a 60.
    assert core._dms(-0.999999999, es_longitud=True) == '1°00\'00.00000"O'
    print("OK: test_dms")


def test_fmt_crs_num():
    assert core._fmt_crs_num(5000000.0) == "5000000.0"
    assert core._fmt_crs_num(0.9992) == "0.9992"
    assert core._fmt_crs_num(298.257222101) == "298.257222101"
    assert core._fmt_crs_num(6356752.314140356) == "6356752.314140356"
    assert core._fmt_crs_num(None) == "N/D"
    assert core._fmt_crs_num("") == "N/D"
    print("OK: test_fmt_crs_num")


def test_nombre_unidad_es():
    assert i18n.nombre_unidad("es", "metre") == "Metros"
    assert i18n.nombre_unidad("es", "degree") == "Grados"
    assert i18n.nombre_unidad("es", None) == "N/D"
    # Unidad no reconocida: se muestra tal cual, capitalizada.
    assert i18n.nombre_unidad("es", "furlong") == "Furlong"
    print("OK: test_nombre_unidad_es")


def test_i18n_tr_basico():
    """i18n.tr(): traducción básica, sustitución de parámetros, y
    respaldo a español si falta la clave o el idioma no es soportado."""
    assert i18n.tr("es", "btn_cerrar") == "Cerrar"
    assert i18n.tr("en", "btn_cerrar") == "Close"
    assert i18n.tr("pt_BR", "btn_cerrar") == "Fechar"
    # Idioma no soportado -> respaldo a español.
    assert i18n.tr("fr", "btn_cerrar") == "Cerrar"
    # Sustitución de parámetros estilo str.format.
    assert i18n.tr("en", "log_archivo_generado", ruta="salida.csv") == "File generated: salida.csv"
    # Clave inexistente -> se retorna la clave tal cual (visible, no silencioso).
    assert i18n.tr("es", "clave_que_no_existe") == "clave_que_no_existe"
    print("OK: test_i18n_tr_basico")


def test_i18n_deteccion_idioma_fuera_de_qgis():
    """Fuera de QGIS (sin qgis.PyQt disponible) la detección debe caer
    de forma segura al idioma por defecto, sin lanzar excepciones."""
    assert i18n.detectar_idioma_qgis() == i18n.IDIOMA_DEFECTO
    print("OK: test_i18n_deteccion_idioma_fuera_de_qgis")


def test_dms_multilenguaje():
    # Español: Oeste/Este, Norte/Sur.
    assert core._dms(-74.0, es_longitud=True, idioma="es").endswith('O')
    assert core._dms(74.0, es_longitud=True, idioma="es").endswith('E')
    # Inglés: West/East.
    assert core._dms(-74.0, es_longitud=True, idioma="en").endswith('W')
    assert core._dms(74.0, es_longitud=True, idioma="en").endswith('E')
    # Portugués (Brasil): Leste/Oeste -> L/O.
    assert core._dms(-74.0, es_longitud=True, idioma="pt_BR").endswith('O')
    assert core._dms(74.0, es_longitud=True, idioma="pt_BR").endswith('L')
    # Latitud: N/S igual en los tres idiomas.
    for idioma in ("es", "en", "pt_BR"):
        assert core._dms(4.0, es_longitud=False, idioma=idioma).endswith('N')
        assert core._dms(-4.0, es_longitud=False, idioma=idioma).endswith('S')
    print("OK: test_dms_multilenguaje")


def test_construir_reporte_html_en_ingles_y_portugues():
    """El reporte técnico debe poder generarse completo en los tres
    idiomas soportados, con el <html lang="..."> correcto y los
    títulos/etiquetas traducidos."""
    base_info = {
        "fecha": "2026-09-24 10:00",
        "version_plugin": "1.4.0",
        "proyecto": "Predio La Esperanza",
        "responsable": "Edwin Arley Castellanos Martinez",
        "archivo_entrada": "puntos.csv",
        "archivo_salida": "puntos_ajustado.csv",
        "base_libre": (1000000.000, 1000000.000, 2600.000),
        "base_ajustada": (1000000.500, 999999.800, 2600.120),
        "dx": 0.500, "dy": -0.200, "dz": 0.120,
        "crs_plano": _crs_plano_ejemplo(),
        "crs_geo": _crs_geo_ejemplo(),
        "total_filas": 5,
        "procesados": 4,
        "errores": [(5, "row error")],
        "errores_transform": 0,
        "puntos": [
            {
                "etiqueta": "P1",
                "x": 1000010.0, "y": 1000005.0, "z": 2601.0,
                "x_adj": 1000010.5, "y_adj": 1000004.8, "z_adj": 2601.12,
                "lon": -74.123456789, "lat": 4.123456789,
            },
        ],
    }

    info_en = dict(base_info, idioma="en")
    reporte_en = core.construir_reporte_html(info_en)
    assert '<html lang="en">' in reporte_en
    assert "RTK Recalculation Technical Report" in reporte_en
    assert "1. Reference systems" in reporte_en
    assert "Adjusted X" in reporte_en
    assert "Transverse Mercator" in reporte_en  # el detalle del CRS no se traduce
    assert '74°07\'24.44444"W' in reporte_en

    info_pt = dict(base_info, idioma="pt_BR")
    reporte_pt = core.construir_reporte_html(info_pt)
    assert '<html lang="pt-BR">' in reporte_pt
    assert "Relatório Técnico de Recálculo RTK" in reporte_pt
    assert "1. Sistemas de referência" in reporte_pt
    assert "X ajustado" in reporte_pt
    assert '74°07\'24.44444"O' in reporte_pt

    # Sin 'idioma' explícito -> se mantiene el comportamiento por
    # defecto en español (compatibilidad hacia atrás).
    reporte_es = core.construir_reporte_html(base_info)
    assert '<html lang="es">' in reporte_es
    assert "Reporte técnico de recálculo RTK" in reporte_es
    print("OK: test_construir_reporte_html_en_ingles_y_portugues")


def _crs_plano_ejemplo():
    """Dict con la forma que arma ``_describir_crs_detallado`` en
    recalculo_dialog.py (usando GDAL) para un CRS proyectado real, con
    los mismos valores que EPSG:9377 (MAGNA-SIRGAS 2018 / Origen-
    Nacional), verificados en vivo contra QGIS."""
    return {
        "proyectado": {
            "nombre": "MAGNA-SIRGAS 2018 / Origen-Nacional",
            "proyeccion": "Transverse Mercator",
            "wkid": "9377",
            "autoridad": "EPSG",
            "unidad_nombre": "metre",
            "unidad_factor": 1.0,
            "false_easting": 5000000.0,
            "false_northing": 2000000.0,
            "meridiano_central": -73.0,
            "factor_escala": 0.9992,
            "latitud_origen": 4.0,
            "area_uso": "Colombia - onshore and offshore.",
        },
        "geografico": {
            "nombre": "MAGNA-SIRGAS 2018",
            "wkid": "20046",
            "autoridad": "EPSG",
            "unidad_nombre": "degree",
            "unidad_factor": 0.017453292519943295,
            "primer_meridiano_nombre": "Greenwich",
            "primer_meridiano_valor": 0.0,
            "datum": "Marco Geocentrico Nacional de Referencia 2018",
            "esferoide_nombre": "GRS 1980",
            "semieje_mayor": 6378137.0,
            "semieje_menor": 6356752.314140356,
            "aplanamiento_inverso": 298.257222101,
            "area_uso": None,  # ya se mostró en el bloque "proyectado"
        },
    }


def _crs_geo_ejemplo():
    """Igual que ``_crs_plano_ejemplo`` pero para un CRS puramente
    geográfico (sin bloque "proyectado"), como EPSG:4686."""
    return {
        "proyectado": None,
        "geografico": {
            "nombre": "MAGNA-SIRGAS",
            "wkid": "4686",
            "autoridad": "EPSG",
            "unidad_nombre": "degree",
            "unidad_factor": 0.017453292519943295,
            "primer_meridiano_nombre": "Greenwich",
            "primer_meridiano_valor": 0.0,
            "datum": "Marco Geocentrico Nacional de Referencia",
            "esferoide_nombre": "GRS 1980",
            "semieje_mayor": 6378137.0,
            "semieje_menor": 6356752.314140356,
            "aplanamiento_inverso": 298.257222101,
            "area_uso": "Colombia - onshore and offshore.",
        },
    }


def test_tarjeta_crs_html_detallado():
    tarjeta = core._tarjeta_crs_html("CRS plano / proyectado", _crs_plano_ejemplo())
    # Bloque proyectado: todos los atributos pedidos por el usuario.
    assert "MAGNA-SIRGAS 2018 / Origen-Nacional" in tarjeta
    assert "Transverse Mercator" in tarjeta
    assert ">9377<" in tarjeta
    assert ">EPSG<" in tarjeta
    assert "Metros (1.0)" in tarjeta
    assert "5000000.0" in tarjeta  # false easting
    assert "2000000.0" in tarjeta  # false northing
    assert "-73.0" in tarjeta  # meridiano central
    assert "0.9992" in tarjeta  # factor de escala
    assert "4.0" in tarjeta  # latitud de origen
    assert "Colombia - onshore and offshore." in tarjeta
    # Bloque geográfico base.
    assert "MAGNA-SIRGAS 2018" in tarjeta
    assert ">20046<" in tarjeta
    assert "Grados (0.017453292519943295)" in tarjeta
    assert "Greenwich (0.0)" in tarjeta
    assert "Marco Geocentrico Nacional de Referencia 2018" in tarjeta
    assert "GRS 1980" in tarjeta
    assert "6378137.0" in tarjeta
    assert "6356752.314140356" in tarjeta
    assert "298.257222101" in tarjeta
    # El área de uso del bloque geográfico es None (ya se mostró en el
    # proyectado): no debe repetirse dos veces en la tarjeta.
    assert tarjeta.count("Colombia - onshore and offshore.") == 1
    print("OK: test_tarjeta_crs_html_detallado")


def test_tarjeta_crs_html_solo_geografico():
    tarjeta = core._tarjeta_crs_html("CRS geográfico de salida", _crs_geo_ejemplo())
    assert "Sistema de coordenadas proyectado" not in tarjeta
    assert "Sistema de coordenadas geográfico" in tarjeta
    assert "MAGNA-SIRGAS" in tarjeta
    assert ">4686<" in tarjeta
    assert "Colombia - onshore and offshore." in tarjeta
    print("OK: test_tarjeta_crs_html_solo_geografico")


def test_tarjeta_crs_html_respaldo_simple():
    """Si GDAL no estaba disponible, recalculo_dialog.py cae al dict
    simple anterior (nombre/authid/unidades/...); el reporte debe
    seguir armándose sin romperse."""
    simple = {
        "authid": "EPSG:9377",
        "nombre": "MAGNA-SIRGAS 2018 / Origen-Nacional",
        "unidades": "meters",
        "estatico": True,
        "cuerpo_celeste": "Earth",
        "metodo": "Transverse Mercator",
    }
    tarjeta = core._tarjeta_crs_html("CRS plano", simple)
    assert "MAGNA-SIRGAS 2018 / Origen-Nacional (EPSG:9377)" in tarjeta
    assert "Estático (datum fijo a la placa tectónica)" in tarjeta

    # Y si ni siquiera eso: un texto simple, o None.
    assert "EPSG:3116" in core._tarjeta_crs_html("CRS plano", "EPSG:3116")
    assert "No disponible" in core._tarjeta_crs_html("CRS plano", None)
    print("OK: test_tarjeta_crs_html_respaldo_simple")


def test_construir_reporte_html():
    info = {
        "fecha": "2026-09-22 10:00",
        "version_plugin": "1.3.3",
        "proyecto": "Predio La Esperanza",
        "responsable": "Edwin Arley Castellanos Martinez",
        "archivo_entrada": "C:/datos/puntos.csv",
        "archivo_salida": "C:/datos/puntos_ajustado.csv",
        "base_libre": (1000000.000, 1000000.000, 2600.000),
        "base_ajustada": (1000000.500, 999999.800, 2600.120),
        "dx": 0.500, "dy": -0.200, "dz": 0.120,
        "crs_plano": _crs_plano_ejemplo(),
        "crs_geo": _crs_geo_ejemplo(),
        "total_filas": 5,
        "procesados": 4,
        "errores": [(5, "La fila no tiene suficientes columnas")],
        "errores_transform": 0,
        "puntos": [
            {
                "etiqueta": "P1 <especial> & \"raro\"",
                "x": 1000010.0, "y": 1000005.0, "z": 2601.0,
                "x_adj": 1000010.5, "y_adj": 1000004.8, "z_adj": 2601.12,
                "lon": -74.123456789, "lat": 4.123456789,
            },
        ],
    }
    reporte = core.construir_reporte_html(info)
    # Página HTML completa y autocontenida, lista para abrir en un navegador.
    assert reporte.startswith("<!DOCTYPE html>")
    assert "<html" in reporte and "</html>" in reporte
    assert 'charset="UTF-8"' in reporte
    assert "Predio La Esperanza" in reporte
    assert "Edwin Arley Castellanos Martinez" in reporte
    # Detalle completo del CRS (extraído de QGIS, no inventado).
    assert "MAGNA-SIRGAS 2018 / Origen-Nacional" in reporte
    assert "Transverse Mercator" in reporte
    assert "5000000.0" in reporte
    assert "0.9992" in reporte
    assert "Colombia - onshore and offshore." in reporte
    assert "0.5000" in reporte  # dx formateado (tabla de bases, sin cambios: 4 decimales)
    assert "-0.2000" in reporte  # dy formateado
    # El ID del punto con caracteres especiales debe quedar escapado,
    # no romper el HTML (nada de "<especial>" literal sin escapar).
    assert "<especial>" not in reporte
    assert "&lt;especial&gt;" in reporte
    # La fila omitida por error debe listarse.
    assert "La fila no tiene suficientes columnas" in reporte
    # Listado de puntos: 3 decimales en X/Y/Z (no 4).
    assert "1000010.500" in reporte  # x_adj con 3 decimales
    assert "1000010.5000" not in reporte
    # Coordenadas geográficas en grados-minutos-segundos.
    assert '74°07\'24.44444"O' in reporte
    assert '4°07\'24.44444"N' in reporte
    # Títulos: el texto va en formato normal y las mayúsculas las pone
    # el CSS (text-transform), que sí se soporta en un navegador real
    # (a diferencia del motor de texto enriquecido de Qt usado antes).
    assert "Reporte técnico de recálculo RTK" in reporte
    assert "1. Sistemas de referencia" in reporte
    assert "4. Listado de puntos recalculados" in reporte
    assert "text-transform: uppercase" in reporte
    # El listado de puntos debe empezar en una hoja nueva al imprimir.
    assert 'class="pagebreak"' in reporte
    assert reporte.index('class="pagebreak"') < reporte.index("4. Listado de puntos recalculados")
    print("OK: test_construir_reporte_html")


def test_construir_reporte_html_sin_proyecto_ni_responsable():
    """Sin proyecto/responsable (ambos opcionales), el reporte se debe
    poder construir igual, sin esas filas."""
    info = {
        "fecha": "2026-09-22 10:00",
        "version_plugin": "1.3.3",
        "proyecto": None,
        "responsable": "",
        "archivo_entrada": "puntos.csv",
        "archivo_salida": "puntos_ajustado.csv",
        "base_libre": (0, 0, None),
        "base_ajustada": (1, 1, None),
        "dx": 1.0, "dy": 1.0, "dz": None,
        "crs_plano": "EPSG:3116",
        "crs_geo": "EPSG:4686",
        "total_filas": 0,
        "procesados": 0,
        "errores": [],
        "errores_transform": 0,
        "puntos": [],
    }
    reporte = core.construir_reporte_html(info)
    assert "<!DOCTYPE html>" in reporte
    assert "N/A" in reporte  # dz sin valor
    # Compatibilidad: crs_plano/crs_geo pasados como texto simple (sin
    # dict de atributos) no deben romper el reporte.
    assert "EPSG:3116" in reporte
    assert "EPSG:4686" in reporte
    print("OK: test_construir_reporte_html_sin_proyecto_ni_responsable")


if __name__ == "__main__":
    test_parse_float()
    test_compute_delta()
    test_csv_roundtrip_and_recalculo()
    test_sugerir_ruta_con_extension()
    test_etiqueta_punto()
    test_traslacion_es_igual_para_todos_los_puntos()
    test_dms()
    test_fmt_crs_num()
    test_nombre_unidad_es()
    test_i18n_tr_basico()
    test_i18n_deteccion_idioma_fuera_de_qgis()
    test_dms_multilenguaje()
    test_tarjeta_crs_html_detallado()
    test_tarjeta_crs_html_solo_geografico()
    test_tarjeta_crs_html_respaldo_simple()
    test_construir_reporte_html()
    test_construir_reporte_html_sin_proyecto_ni_responsable()
    test_construir_reporte_html_en_ingles_y_portugues()
    print("\nTodas las pruebas pasaron correctamente.")
