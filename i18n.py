# -*- coding: utf-8 -*-
"""
i18n.py
=======

Módulo de internacionalización del complemento, independiente de
QGIS/PyQt salvo por la función de detección de idioma (que sí
necesita QSettings/QLocale, pero se protege con try/except para que
el resto del módulo — los diccionarios de texto y ``tr()`` — se pueda
importar y usar con Python estándar, igual que ``core.py``).

Uso típico::

    from . import i18n
    texto = i18n.tr(idioma, "clave", parametro=valor)

``idioma`` es uno de los códigos soportados: "es" (español, idioma
por defecto), "en" (inglés) o "pt_BR" (portugués de Brasil). Si la
clave no existe para ese idioma (o el idioma no es uno de los
soportados), se usa el texto en español como respaldo, para que un
error de tipeo en una clave nunca deje un hueco en la interfaz.
"""

IDIOMA_DEFECTO = "es"
IDIOMAS_SOPORTADOS = ("es", "en", "pt_BR")


def tr(idioma, clave, **kwargs):
    """Traduce ``clave`` al ``idioma`` indicado, con sustitución estilo
    ``str.format`` si se pasan ``kwargs``. Si falta la traducción para
    ese idioma, o el idioma no es soportado, cae a español; si la
    clave tampoco existe en español, retorna la clave tal cual (para
    que un error de tipeo sea visible en vez de silencioso)."""
    textos = _TEXTOS.get(idioma) or _TEXTOS[IDIOMA_DEFECTO]
    plantilla = textos.get(clave)
    if plantilla is None:
        plantilla = _TEXTOS[IDIOMA_DEFECTO].get(clave, clave)
    if kwargs:
        try:
            return plantilla.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return plantilla
    return plantilla


def lang_html(idioma):
    """Código de idioma para el atributo ``lang`` de la etiqueta
    ``<html>`` del reporte técnico."""
    return {"es": "es", "en": "en", "pt_BR": "pt-BR"}.get(idioma, "es")


def nombre_unidad(idioma, nombre):
    """Traduce el nombre de una unidad tal como lo devuelve GDAL/PROJ
    (siempre en inglés, p. ej. "metre", "degree"). Si no se reconoce,
    se muestra tal cual (capitalizado)."""
    if not nombre:
        return tr(idioma, "crs_nd")
    tabla = _NOMBRES_UNIDAD.get(idioma) or _NOMBRES_UNIDAD[IDIOMA_DEFECTO]
    return tabla.get(str(nombre).strip().lower(), str(nombre).capitalize())


def sufijo_hemisferio(idioma, es_longitud, valor_positivo):
    """Sufijo de hemisferio para coordenadas en formato grados-minutos-
    segundos: longitud Este/Oeste (o Leste/Oeste en portugués) y
    latitud Norte/Sur, según el idioma y el signo del valor."""
    tabla = _SUFIJOS_HEMISFERIO.get(idioma) or _SUFIJOS_HEMISFERIO[IDIOMA_DEFECTO]
    if es_longitud:
        return tabla["lon_pos"] if valor_positivo else tabla["lon_neg"]
    return tabla["lat_pos"] if valor_positivo else tabla["lat_neg"]


def detectar_idioma_qgis():
    """Detecta el idioma configurado en la interfaz de QGIS y lo
    traduce a uno de los códigos soportados por este complemento
    ('es', 'en', 'pt_BR'). Usa la misma clave de configuración que usa
    el propio QGIS para decidir qué traducción de su interfaz cargar
    (``locale/userLocale``), y si no está disponible recurre al locale
    del sistema operativo. Cualquier variante de portugués (Brasil,
    Portugal, ...) se resuelve a "pt_BR", que es la única variante de
    portugués que ofrece este complemento. Si no puede determinarse
    (por ejemplo, al usar este módulo fuera de QGIS, con Python
    estándar) retorna ``IDIOMA_DEFECTO``.
    """
    try:
        from qgis.PyQt.QtCore import QSettings, QLocale
    except Exception:
        return IDIOMA_DEFECTO

    codigo = ""
    try:
        codigo = QSettings().value("locale/userLocale", "") or ""
    except Exception:
        codigo = ""
    if not codigo:
        try:
            codigo = QLocale.system().name() or ""
        except Exception:
            codigo = ""

    codigo = str(codigo).strip()
    if not codigo:
        return IDIOMA_DEFECTO

    partes = codigo.replace("-", "_").split("_")
    base = partes[0].lower() if partes else ""
    pais = partes[1].upper() if len(partes) > 1 else ""

    if base == "pt":
        # Se ofrece una sola variante de portugués (pt_BR); se usa para
        # cualquier país (Brasil, Portugal, ...) en vez de caer a
        # español, que sería menos útil para un hablante de portugués.
        return "pt_BR"
    if base == "en":
        return "en"
    if base == "es":
        return "es"
    return IDIOMA_DEFECTO


_SUFIJOS_HEMISFERIO = {
    "es": {"lon_pos": "E", "lon_neg": "O", "lat_pos": "N", "lat_neg": "S"},
    "en": {"lon_pos": "E", "lon_neg": "W", "lat_pos": "N", "lat_neg": "S"},
    "pt_BR": {"lon_pos": "L", "lon_neg": "O", "lat_pos": "N", "lat_neg": "S"},
}

_NOMBRES_UNIDAD = {
    "es": {
        "metre": "Metros", "meter": "Metros", "metres": "Metros", "meters": "Metros",
        "degree": "Grados", "degrees": "Grados",
        "us survey foot": "Pies (EE.UU.)", "foot": "Pies", "foot_us": "Pies (EE.UU.)",
        "kilometre": "Kilómetros", "kilometer": "Kilómetros",
        "grad": "Gradianes", "gon": "Gradianes",
    },
    "en": {
        "metre": "Meters", "meter": "Meters", "metres": "Meters", "meters": "Meters",
        "degree": "Degrees", "degrees": "Degrees",
        "us survey foot": "US Survey Feet", "foot": "Feet", "foot_us": "US Survey Feet",
        "kilometre": "Kilometers", "kilometer": "Kilometers",
        "grad": "Gradians", "gon": "Gradians",
    },
    "pt_BR": {
        "metre": "Metros", "meter": "Metros", "metres": "Metros", "meters": "Metros",
        "degree": "Graus", "degrees": "Graus",
        "us survey foot": "Pés (EUA)", "foot": "Pés", "foot_us": "Pés (EUA)",
        "kilometre": "Quilômetros", "kilometer": "Quilômetros",
        "grad": "Gradianos", "gon": "Gradianos",
    },
}

_TEXTOS = {
    "es": {
        # --- Diálogo: títulos, grupos, campos ---------------------------
        "window_title": "Recálculo de coordenadas RTK (libre → ajustada)",
        "intro_text": (
            "Recalcula un archivo de puntos levantados con una base RTK de "
            "coordenadas libres, trasladándolos a coordenadas ajustadas a "
            "partir del postproceso estático de esa misma base. Se "
            "recalculan tanto las coordenadas planas (proyectadas) como "
            "las geográficas."
        ),
        "grp_base_libre": "Base RTK libre (tomada en campo)",
        "grp_base_ajustada": "Base ajustada (postproceso estático)",
        "lbl_x": "X / Este:",
        "lbl_y": "Y / Norte:",
        "lbl_z": "Z / Elevación:",
        "placeholder_num": "0.000",
        "grp_csv": "Archivo CSV de puntos a recalcular (delimitado por comas)",
        "placeholder_csv_path": "Seleccione el archivo .csv de entrada...",
        "btn_examinar": "Examinar...",
        "lbl_col_id": "Columna ID (opcional):",
        "lbl_col_x": "Columna X / Este:",
        "lbl_col_y": "Columna Y / Norte:",
        "lbl_col_z": "Columna Z / Elevación (opcional):",
        "placeholder_col": "-- Seleccione una columna --",
        "placeholder_col_opcional": "-- No aplica / usar número de fila --",
        "grp_crs": "Sistemas de referencia",
        "lbl_crs_plano": "CRS plano/proyectado de las coordenadas X, Y:",
        "lbl_crs_geo": "CRS geográfico de salida (lon/lat):",
        "grp_resultado": "Resultado",
        "placeholder_out_path": "Ruta del CSV de salida...",
        "btn_guardar_como": "Guardar como...",
        "chk_capa_ajustada": "Agregar capa de puntos AJUSTADOS al proyecto",
        "chk_capa_libre": "Agregar capa de puntos LIBRES (originales) al proyecto",
        "grp_export_adicional": "Exportar puntos ajustados también en otros formatos",
        "chk_export_shp": "Exportar a Shapefile (.shp)",
        "chk_export_dxf": "Exportar a DXF (.dxf)",
        "nota_dxf": (
            "Nota: el formato DXF no maneja una tabla de atributos como tal; se exporta la "
            "geometría de los puntos (con elevación si está disponible) junto con una etiqueta "
            "de texto por punto (la columna ID si fue seleccionada, o un consecutivo P1, P2...)."
        ),
        "grp_reporte": "Reporte técnico (opcional)",
        "placeholder_proyecto": "Nombre del predio/proyecto (opcional)",
        "placeholder_responsable": "Responsable del levantamiento (opcional)",
        "lbl_proyecto": "Proyecto:",
        "lbl_responsable": "Responsable:",
        "chk_reporte": "Generar reporte técnico (HTML)",
        "nota_reporte": (
            "El reporte es una página HTML (se abre con cualquier navegador) con las "
            "coordenadas de ambas bases, el vector de traslación aplicado, el detalle "
            "completo de los sistemas de referencia usados (equivalente y las mismas "
            "propiedades que muestra QGIS/ArcGIS para un CRS) y el listado completo de "
            "puntos recalculados. Es opcional: solo se genera si el usuario lo requiere, "
            "por ejemplo como soporte técnico del trabajo realizado."
        ),
        "placeholder_log": "Aquí aparecerá el resultado del proceso...",
        "btn_calcular": "Calcular y exportar",
        "btn_cerrar": "Cerrar",

        # --- Diálogos de archivo -----------------------------------------
        "dlg_sel_csv_titulo": "Seleccionar archivo CSV",
        "filtro_csv": "Archivos CSV (*.csv);;Todos los archivos (*)",
        "dlg_guardar_csv_titulo": "Guardar CSV recalculado",
        "filtro_csv_solo": "Archivos CSV (*.csv)",
        "dlg_guardar_shp_titulo": "Guardar Shapefile",
        "filtro_shp": "Shapefile (*.shp)",
        "dlg_guardar_dxf_titulo": "Guardar DXF",
        "filtro_dxf": "DXF (*.dxf)",
        "dlg_guardar_reporte_titulo": "Guardar reporte técnico",
        "filtro_html": "HTML (*.html)",

        # --- Mensajes (QMessageBox) ---------------------------------------
        "err_leer_csv_titulo": "Error al leer CSV",
        "err_leer_csv_msg": "No se pudo leer el archivo:\n{error}",
        "warn_archivo_vacio_titulo": "Archivo vacío",
        "warn_archivo_vacio_msg": "El archivo CSV no contiene datos.",
        "warn_datos_incompletos_titulo": "Datos incompletos",
        "warn_falta_csv_titulo": "Falta el CSV",
        "warn_falta_csv_msg": "Seleccione primero el archivo CSV de puntos a recalcular.",
        "warn_columnas_incompletas_titulo": "Columnas incompletas",
        "warn_columnas_incompletas_msg": "Debe seleccionar la columna X/Este y la columna Y/Norte del CSV.",
        "warn_columnas_repetidas_titulo": "Columnas repetidas",
        "warn_columnas_repetidas_msg": "Las columnas X, Y y Z deben ser distintas entre sí.",
        "warn_falta_salida_titulo": "Falta ruta de salida",
        "warn_falta_salida_msg": "Indique dónde guardar el CSV recalculado.",
        "warn_falta_shp_titulo": "Falta ruta de Shapefile",
        "warn_falta_shp_msg": "Indique dónde guardar el Shapefile (.shp).",
        "warn_falta_dxf_titulo": "Falta ruta de DXF",
        "warn_falta_dxf_msg": "Indique dónde guardar el DXF (.dxf).",
        "warn_falta_reporte_titulo": "Falta ruta del reporte",
        "warn_falta_reporte_msg": "Indique dónde guardar el reporte técnico (.html).",
        "warn_crs_invalido_titulo": "CRS inválido",
        "warn_crs_invalido_msg": "Seleccione un sistema de referencia plano y uno geográfico válidos.",
        "err_sin_datos_validos_titulo": "Sin datos válidos",
        "err_sin_datos_validos_msg": "Ninguna fila del CSV pudo procesarse. Revise las columnas seleccionadas.",
        "err_guardar_titulo": "Error al guardar",
        "err_guardar_msg": "No se pudo escribir el archivo de salida:\n{error}",
        "info_proceso_terminado_titulo": "Proceso terminado",

        "err_base_xy_invalida": "Coordenadas X/Y de la {nombre_base} inválidas: {error}",
        "err_base_z_invalida": "Elevación Z de la {nombre_base} inválida: {error}",
        "nombre_base_libre": "base libre",
        "nombre_base_ajustada": "base ajustada",

        # --- Registro de estado (log) --------------------------------------
        "log_columnas_cargadas": "Se cargaron {n_col} columnas y {n_filas} filas de datos desde: {archivo}",
        "log_vector_calculado": "Vector de traslación calculado:  ΔX = {dx}   ΔY = {dy}   ΔZ = {dz}",
        "log_dz_na": "N/A (sin elevación en ambas bases)",
        "log_recalculo_ok": "Se recalcularon {ok} de {total} puntos correctamente.",
        "log_filas_omitidas": "{n} fila(s) se omitieron por errores de formato (ver detalle abajo).",
        "log_fila_error": "  Fila {num}: {msg}",
        "log_mas_errores": "  ... y {n} error(es) más.",
        "log_errores_transform": "{n} punto(s) no pudieron reproyectarse a coordenadas geográficas.",
        "log_archivo_generado": "Archivo generado: {ruta}",
        "log_no_capa_shp": "No se pudo preparar la capa para exportar a Shapefile.",
        "log_shp_generado": "Shapefile generado: {ruta}",
        "log_shp_error": "No se pudo generar el Shapefile: {msg}",
        "log_dxf_generado": "DXF generado: {ruta}",
        "log_dxf_error": "No se pudo generar el DXF: {msg}",
        "log_reporte_generado": "Reporte técnico generado: {ruta}",
        "log_reporte_error": "No se pudo generar el reporte técnico: {msg}",

        # --- Resumen final (QMessageBox.information) ------------------------
        "resumen_principal": "Se generó el archivo:\n{ruta}\n\nPuntos procesados: {procesados}\nPuntos omitidos: {omitidos}",
        "resumen_shp": "\nShapefile: {ruta}",
        "resumen_dxf": "\nDXF: {ruta}",
        "resumen_reporte": "\nReporte técnico: {ruta}",
        "resumen_reporte_no_generado": "no se pudo generar (ver registro)",

        # --- Nombres de capas ------------------------------------------------
        "capa_ajustada_nombre": "Puntos ajustados (RTK)",
        "capa_libre_nombre": "Puntos libres (originales)",

        # --- plugin.py: menú, acción, tooltip -------------------------------
        "plugin_menu": "&Recálculo RTK a Ajustada",
        "plugin_accion": "Recalcular coordenadas RTK (libre → ajustada)",
        "plugin_whatsthis": (
            "Recalcula un CSV de puntos levantados con RTK, trasladándolos "
            "desde una base de coordenadas libres hacia la coordenada "
            "ajustada obtenida por postproceso estático."
        ),

        # --- Reporte técnico (core.py) --------------------------------------
        "rpt_titulo": "Reporte técnico de recálculo RTK",
        "rpt_subtitulo": "Traslación de coordenadas de base libre a base ajustada (postproceso estático)",
        "rpt_fecha": "Fecha del reporte",
        "rpt_complemento": "Complemento",
        "rpt_nombre_plugin": "Recálculo RTK a Coordenadas Ajustadas",
        "rpt_archivo_entrada": "Archivo de entrada",
        "rpt_archivo_salida": "Archivo de salida",
        "rpt_proyecto": "Proyecto",
        "rpt_responsable": "Responsable",
        "rpt_h2_1": "1. Sistemas de referencia",
        "rpt_h2_2": "2. Coordenadas de la base y vector de traslación",
        "rpt_h2_3": "3. Resumen del proceso",
        "rpt_h2_4": "4. Listado de puntos recalculados",
        "rpt_crs_plano_titulo": "CRS plano / proyectado (usado en X, Y)",
        "rpt_crs_geo_titulo": "CRS geográfico de salida (usado en Longitud, Latitud)",
        "rpt_tabla_base_header_base": "Base",
        "rpt_tabla_base_header_x": "X / Este",
        "rpt_tabla_base_header_y": "Y / Norte",
        "rpt_tabla_base_header_z": "Z / Elevación",
        "rpt_base_libre_row": "Libre (tomada en campo)",
        "rpt_base_ajustada_row": "Ajustada (postproceso estático)",
        "rpt_vector_row": "Vector de traslación (Δ)",
        "rpt_metodo_parrafo": (
            "Método: traslación rígida, con el mismo vector (&Delta;X, &Delta;Y, &Delta;Z) "
            "aplicado a todos los puntos, según:&nbsp; <i>punto_ajustado = punto_libre + "
            "(base_ajustada &minus; base_libre)</i>. Válido para una sola base RTK con "
            "radiaciones de corta/mediana distancia (sin rotación ni escala)."
        ),
        "rpt_resumen_filas_csv": "Filas de datos en el CSV de entrada",
        "rpt_resumen_procesados": "Puntos recalculados correctamente",
        "rpt_resumen_omitidos": "Filas omitidas por error de formato",
        "rpt_resumen_errores_transform": "Puntos no reproyectados a geográficas",
        "rpt_errores_h2": "Filas omitidas por error de formato",
        "rpt_errores_item": "Fila {num}: {msg}",
        "rpt_nota_puntos": (
            "Coordenadas X, Y, Z en las unidades del CRS plano/proyectado indicado "
            "en la sección 1, con 3 decimales. Coordenadas geográficas en formato "
            "grados-minutos-segundos (5 decimales en los segundos)."
        ),
        "rpt_col_punto": "Punto",
        "rpt_col_x": "X",
        "rpt_col_y": "Y",
        "rpt_col_z": "Z",
        "rpt_col_x_adj": "X ajustada",
        "rpt_col_y_adj": "Y ajustada",
        "rpt_col_z_adj": "Z ajustada",
        "rpt_col_lon": "Longitud",
        "rpt_col_lat": "Latitud",
        "rpt_cierre": (
            'Fin del reporte — generado automáticamente por el complemento '
            '"{nombre_plugin}" (v{version}) para QGIS.'
        ),

        # --- Tarjeta de detalle de CRS ---------------------------------------
        "crs_nombre": "Nombre",
        "crs_proyeccion": "Proyección",
        "crs_wkid": "WKID",
        "crs_autoridad": "Autoridad",
        "crs_unidad_lineal": "Unidad lineal",
        "crs_false_easting": "Falso este (False Easting)",
        "crs_false_northing": "Falso norte (False Northing)",
        "crs_meridiano_central": "Meridiano central",
        "crs_factor_escala": "Factor de escala",
        "crs_latitud_origen": "Latitud de origen",
        "crs_area_uso": "Área de uso",
        "crs_unidad_angular": "Unidad angular",
        "crs_primer_meridiano": "Primer meridiano",
        "crs_datum": "Datum",
        "crs_esferoide": "Esferoide",
        "crs_semieje_mayor": "Semieje mayor",
        "crs_semieje_menor": "Semieje menor",
        "crs_aplanamiento_inverso": "Aplanamiento inverso",
        "crs_subtabla_proyectado": "Sistema de coordenadas proyectado",
        "crs_subtabla_geografico": "Sistema de coordenadas geográfico",
        "crs_nombre_epsg": "Nombre (EPSG)",
        "crs_unidades": "Unidades",
        "crs_datum_estatico": "Estático (datum fijo a la placa tectónica)",
        "crs_datum_dinamico": "Dinámico (datum no fijo a la placa tectónica)",
        "crs_cuerpo_celeste": "Cuerpo celeste",
        "crs_metodo_proyeccion": "Método de proyección",
        "crs_no_disponible": "No disponible.",
        "crs_nd": "N/D",
    },

    "en": {
        "window_title": "RTK Coordinate Recalculation (free → adjusted)",
        "intro_text": (
            "Recalculates a file of points surveyed from an RTK base with free "
            "coordinates, translating them to adjusted coordinates based on that "
            "same base's static post-processing. Both plane (projected) and "
            "geographic coordinates are recalculated."
        ),
        "grp_base_libre": "Free RTK base (taken in the field)",
        "grp_base_ajustada": "Adjusted base (static post-processing)",
        "lbl_x": "X / Easting:",
        "lbl_y": "Y / Northing:",
        "lbl_z": "Z / Elevation:",
        "placeholder_num": "0.000",
        "grp_csv": "CSV file of points to recalculate (comma-delimited)",
        "placeholder_csv_path": "Select the input .csv file...",
        "btn_examinar": "Browse...",
        "lbl_col_id": "ID column (optional):",
        "lbl_col_x": "X / Easting column:",
        "lbl_col_y": "Y / Northing column:",
        "lbl_col_z": "Z / Elevation column (optional):",
        "placeholder_col": "-- Select a column --",
        "placeholder_col_opcional": "-- Not applicable / use row number --",
        "grp_crs": "Reference systems",
        "lbl_crs_plano": "Plane/projected CRS for X, Y coordinates:",
        "lbl_crs_geo": "Output geographic CRS (lon/lat):",
        "grp_resultado": "Result",
        "placeholder_out_path": "Output CSV path...",
        "btn_guardar_como": "Save as...",
        "chk_capa_ajustada": "Add ADJUSTED points layer to the project",
        "chk_capa_libre": "Add FREE (original) points layer to the project",
        "grp_export_adicional": "Also export adjusted points in other formats",
        "chk_export_shp": "Export to Shapefile (.shp)",
        "chk_export_dxf": "Export to DXF (.dxf)",
        "nota_dxf": (
            "Note: the DXF format does not handle an attribute table as such; the "
            "point geometry is exported (with elevation if available) along with "
            "a text label per point (the ID column if selected, or a sequential "
            "P1, P2...)."
        ),
        "grp_reporte": "Technical report (optional)",
        "placeholder_proyecto": "Property/project name (optional)",
        "placeholder_responsable": "Person responsible for the survey (optional)",
        "lbl_proyecto": "Project:",
        "lbl_responsable": "Responsible:",
        "chk_reporte": "Generate technical report (HTML)",
        "nota_reporte": (
            "The report is an HTML page (opens with any browser) with the "
            "coordinates of both bases, the applied translation vector, the full "
            "detail of the reference systems used (equivalent to, and with the "
            "same properties as, what QGIS/ArcGIS shows for a CRS) and the full "
            "list of recalculated points. It is optional: it is only generated if "
            "the user requests it, for example as technical support for the work "
            "performed."
        ),
        "placeholder_log": "The process result will appear here...",
        "btn_calcular": "Calculate and export",
        "btn_cerrar": "Close",

        "dlg_sel_csv_titulo": "Select CSV file",
        "filtro_csv": "CSV files (*.csv);;All files (*)",
        "dlg_guardar_csv_titulo": "Save recalculated CSV",
        "filtro_csv_solo": "CSV files (*.csv)",
        "dlg_guardar_shp_titulo": "Save Shapefile",
        "filtro_shp": "Shapefile (*.shp)",
        "dlg_guardar_dxf_titulo": "Save DXF",
        "filtro_dxf": "DXF (*.dxf)",
        "dlg_guardar_reporte_titulo": "Save technical report",
        "filtro_html": "HTML (*.html)",

        "err_leer_csv_titulo": "Error reading CSV",
        "err_leer_csv_msg": "The file could not be read:\n{error}",
        "warn_archivo_vacio_titulo": "Empty file",
        "warn_archivo_vacio_msg": "The CSV file has no data.",
        "warn_datos_incompletos_titulo": "Incomplete data",
        "warn_falta_csv_titulo": "CSV missing",
        "warn_falta_csv_msg": "First select the CSV file of points to recalculate.",
        "warn_columnas_incompletas_titulo": "Incomplete columns",
        "warn_columnas_incompletas_msg": "You must select the X/Easting column and the Y/Northing column of the CSV.",
        "warn_columnas_repetidas_titulo": "Repeated columns",
        "warn_columnas_repetidas_msg": "The X, Y and Z columns must all be different from each other.",
        "warn_falta_salida_titulo": "Output path missing",
        "warn_falta_salida_msg": "Indicate where to save the recalculated CSV.",
        "warn_falta_shp_titulo": "Shapefile path missing",
        "warn_falta_shp_msg": "Indicate where to save the Shapefile (.shp).",
        "warn_falta_dxf_titulo": "DXF path missing",
        "warn_falta_dxf_msg": "Indicate where to save the DXF (.dxf).",
        "warn_falta_reporte_titulo": "Report path missing",
        "warn_falta_reporte_msg": "Indicate where to save the technical report (.html).",
        "warn_crs_invalido_titulo": "Invalid CRS",
        "warn_crs_invalido_msg": "Select a valid plane reference system and a valid geographic one.",
        "err_sin_datos_validos_titulo": "No valid data",
        "err_sin_datos_validos_msg": "No row in the CSV could be processed. Check the selected columns.",
        "err_guardar_titulo": "Error saving",
        "err_guardar_msg": "The output file could not be written:\n{error}",
        "info_proceso_terminado_titulo": "Process finished",

        "err_base_xy_invalida": "Invalid X/Y coordinates for the {nombre_base}: {error}",
        "err_base_z_invalida": "Invalid Z elevation for the {nombre_base}: {error}",
        "nombre_base_libre": "free base",
        "nombre_base_ajustada": "adjusted base",

        "log_columnas_cargadas": "Loaded {n_col} columns and {n_filas} data rows from: {archivo}",
        "log_vector_calculado": "Translation vector calculated:  ΔX = {dx}   ΔY = {dy}   ΔZ = {dz}",
        "log_dz_na": "N/A (no elevation on both bases)",
        "log_recalculo_ok": "Successfully recalculated {ok} of {total} points.",
        "log_filas_omitidas": "{n} row(s) were skipped due to formatting errors (see detail below).",
        "log_fila_error": "  Row {num}: {msg}",
        "log_mas_errores": "  ... and {n} more error(s).",
        "log_errores_transform": "{n} point(s) could not be reprojected to geographic coordinates.",
        "log_archivo_generado": "File generated: {ruta}",
        "log_no_capa_shp": "The layer for exporting to Shapefile could not be prepared.",
        "log_shp_generado": "Shapefile generated: {ruta}",
        "log_shp_error": "The Shapefile could not be generated: {msg}",
        "log_dxf_generado": "DXF generated: {ruta}",
        "log_dxf_error": "The DXF could not be generated: {msg}",
        "log_reporte_generado": "Technical report generated: {ruta}",
        "log_reporte_error": "The technical report could not be generated: {msg}",

        "resumen_principal": "The file was generated:\n{ruta}\n\nPoints processed: {procesados}\nPoints skipped: {omitidos}",
        "resumen_shp": "\nShapefile: {ruta}",
        "resumen_dxf": "\nDXF: {ruta}",
        "resumen_reporte": "\nTechnical report: {ruta}",
        "resumen_reporte_no_generado": "could not be generated (see log)",

        "capa_ajustada_nombre": "Adjusted points (RTK)",
        "capa_libre_nombre": "Free points (original)",

        "plugin_menu": "&RTK Recalculation to Adjusted",
        "plugin_accion": "Recalculate RTK coordinates (free → adjusted)",
        "plugin_whatsthis": (
            "Recalculates a CSV of points surveyed with RTK, translating them "
            "from a free-coordinates base to the adjusted coordinate obtained by "
            "static post-processing."
        ),

        "rpt_titulo": "RTK Recalculation Technical Report",
        "rpt_subtitulo": "Translation of coordinates from free base to adjusted base (static post-processing)",
        "rpt_fecha": "Report date",
        "rpt_complemento": "Plugin",
        "rpt_nombre_plugin": "RTK Recalculation to Adjusted Coordinates",
        "rpt_archivo_entrada": "Input file",
        "rpt_archivo_salida": "Output file",
        "rpt_proyecto": "Project",
        "rpt_responsable": "Responsible",
        "rpt_h2_1": "1. Reference systems",
        "rpt_h2_2": "2. Base coordinates and translation vector",
        "rpt_h2_3": "3. Process summary",
        "rpt_h2_4": "4. List of recalculated points",
        "rpt_crs_plano_titulo": "Plane / projected CRS (used for X, Y)",
        "rpt_crs_geo_titulo": "Output geographic CRS (used for Longitude, Latitude)",
        "rpt_tabla_base_header_base": "Base",
        "rpt_tabla_base_header_x": "X / Easting",
        "rpt_tabla_base_header_y": "Y / Northing",
        "rpt_tabla_base_header_z": "Z / Elevation",
        "rpt_base_libre_row": "Free (taken in the field)",
        "rpt_base_ajustada_row": "Adjusted (static post-processing)",
        "rpt_vector_row": "Translation vector (Δ)",
        "rpt_metodo_parrafo": (
            "Method: rigid translation, with the same vector (&Delta;X, &Delta;Y, "
            "&Delta;Z) applied to all points, according to:&nbsp; <i>adjusted_point "
            "= free_point + (adjusted_base &minus; free_base)</i>. Valid for a "
            "single RTK base with short/medium-distance radiations (no rotation or "
            "scale)."
        ),
        "rpt_resumen_filas_csv": "Data rows in the input CSV",
        "rpt_resumen_procesados": "Points recalculated correctly",
        "rpt_resumen_omitidos": "Rows skipped due to formatting errors",
        "rpt_resumen_errores_transform": "Points not reprojected to geographic",
        "rpt_errores_h2": "Rows skipped due to formatting error",
        "rpt_errores_item": "Row {num}: {msg}",
        "rpt_nota_puntos": (
            "X, Y, Z coordinates in the units of the plane/projected CRS indicated "
            "in section 1, with 3 decimals. Geographic coordinates in "
            "degrees-minutes-seconds format (5 decimals on the seconds)."
        ),
        "rpt_col_punto": "Point",
        "rpt_col_x": "X",
        "rpt_col_y": "Y",
        "rpt_col_z": "Z",
        "rpt_col_x_adj": "Adjusted X",
        "rpt_col_y_adj": "Adjusted Y",
        "rpt_col_z_adj": "Adjusted Z",
        "rpt_col_lon": "Longitude",
        "rpt_col_lat": "Latitude",
        "rpt_cierre": (
            'End of report — automatically generated by the "{nombre_plugin}" '
            'plugin (v{version}) for QGIS.'
        ),

        "crs_nombre": "Name",
        "crs_proyeccion": "Projection",
        "crs_wkid": "WKID",
        "crs_autoridad": "Authority",
        "crs_unidad_lineal": "Linear unit",
        "crs_false_easting": "False Easting",
        "crs_false_northing": "False Northing",
        "crs_meridiano_central": "Central meridian",
        "crs_factor_escala": "Scale factor",
        "crs_latitud_origen": "Latitude of origin",
        "crs_area_uso": "Area of use",
        "crs_unidad_angular": "Angular unit",
        "crs_primer_meridiano": "Prime meridian",
        "crs_datum": "Datum",
        "crs_esferoide": "Spheroid",
        "crs_semieje_mayor": "Semi-major axis",
        "crs_semieje_menor": "Semi-minor axis",
        "crs_aplanamiento_inverso": "Inverse flattening",
        "crs_subtabla_proyectado": "Projected coordinate system",
        "crs_subtabla_geografico": "Geographic coordinate system",
        "crs_nombre_epsg": "Name (EPSG)",
        "crs_unidades": "Units",
        "crs_datum_estatico": "Static (datum fixed to the tectonic plate)",
        "crs_datum_dinamico": "Dynamic (datum not fixed to the tectonic plate)",
        "crs_cuerpo_celeste": "Celestial body",
        "crs_metodo_proyeccion": "Projection method",
        "crs_no_disponible": "Not available.",
        "crs_nd": "N/A",
    },

    "pt_BR": {
        "window_title": "Recálculo de coordenadas RTK (livre → ajustada)",
        "intro_text": (
            "Recalcula um arquivo de pontos levantados com uma base RTK de "
            "coordenadas livres, transladando-os para coordenadas ajustadas a "
            "partir do pós-processamento estático dessa mesma base. São "
            "recalculadas tanto as coordenadas planas (projetadas) quanto as "
            "geográficas."
        ),
        "grp_base_libre": "Base RTK livre (tomada em campo)",
        "grp_base_ajustada": "Base ajustada (pós-processamento estático)",
        "lbl_x": "X / Este:",
        "lbl_y": "Y / Norte:",
        "lbl_z": "Z / Elevação:",
        "placeholder_num": "0.000",
        "grp_csv": "Arquivo CSV de pontos a recalcular (delimitado por vírgulas)",
        "placeholder_csv_path": "Selecione o arquivo .csv de entrada...",
        "btn_examinar": "Procurar...",
        "lbl_col_id": "Coluna ID (opcional):",
        "lbl_col_x": "Coluna X / Este:",
        "lbl_col_y": "Coluna Y / Norte:",
        "lbl_col_z": "Coluna Z / Elevação (opcional):",
        "placeholder_col": "-- Selecione uma coluna --",
        "placeholder_col_opcional": "-- Não aplicável / usar número da linha --",
        "grp_crs": "Sistemas de referência",
        "lbl_crs_plano": "SRC plano/projetado das coordenadas X, Y:",
        "lbl_crs_geo": "SRC geográfico de saída (lon/lat):",
        "grp_resultado": "Resultado",
        "placeholder_out_path": "Caminho do CSV de saída...",
        "btn_guardar_como": "Salvar como...",
        "chk_capa_ajustada": "Adicionar camada de pontos AJUSTADOS ao projeto",
        "chk_capa_libre": "Adicionar camada de pontos LIVRES (originais) ao projeto",
        "grp_export_adicional": "Exportar também os pontos ajustados em outros formatos",
        "chk_export_shp": "Exportar para Shapefile (.shp)",
        "chk_export_dxf": "Exportar para DXF (.dxf)",
        "nota_dxf": (
            "Observação: o formato DXF não possui uma tabela de atributos como "
            "tal; é exportada a geometria dos pontos (com elevação, se "
            "disponível) junto com um rótulo de texto por ponto (a coluna ID, se "
            "selecionada, ou um sequencial P1, P2...)."
        ),
        "grp_reporte": "Relatório técnico (opcional)",
        "placeholder_proyecto": "Nome do imóvel/projeto (opcional)",
        "placeholder_responsable": "Responsável pelo levantamento (opcional)",
        "lbl_proyecto": "Projeto:",
        "lbl_responsable": "Responsável:",
        "chk_reporte": "Gerar relatório técnico (HTML)",
        "nota_reporte": (
            "O relatório é uma página HTML (abre em qualquer navegador) com as "
            "coordenadas de ambas as bases, o vetor de translação aplicado, o "
            "detalhe completo dos sistemas de referência usados (equivalente às "
            "mesmas propriedades que o QGIS/ArcGIS mostra para um SRC) e a lista "
            "completa dos pontos recalculados. É opcional: só é gerado se o "
            "usuário solicitar, por exemplo como suporte técnico do trabalho "
            "realizado."
        ),
        "placeholder_log": "O resultado do processo aparecerá aqui...",
        "btn_calcular": "Calcular e exportar",
        "btn_cerrar": "Fechar",

        "dlg_sel_csv_titulo": "Selecionar arquivo CSV",
        "filtro_csv": "Arquivos CSV (*.csv);;Todos os arquivos (*)",
        "dlg_guardar_csv_titulo": "Salvar CSV recalculado",
        "filtro_csv_solo": "Arquivos CSV (*.csv)",
        "dlg_guardar_shp_titulo": "Salvar Shapefile",
        "filtro_shp": "Shapefile (*.shp)",
        "dlg_guardar_dxf_titulo": "Salvar DXF",
        "filtro_dxf": "DXF (*.dxf)",
        "dlg_guardar_reporte_titulo": "Salvar relatório técnico",
        "filtro_html": "HTML (*.html)",

        "err_leer_csv_titulo": "Erro ao ler CSV",
        "err_leer_csv_msg": "Não foi possível ler o arquivo:\n{error}",
        "warn_archivo_vacio_titulo": "Arquivo vazio",
        "warn_archivo_vacio_msg": "O arquivo CSV não contém dados.",
        "warn_datos_incompletos_titulo": "Dados incompletos",
        "warn_falta_csv_titulo": "Falta o CSV",
        "warn_falta_csv_msg": "Selecione primeiro o arquivo CSV de pontos a recalcular.",
        "warn_columnas_incompletas_titulo": "Colunas incompletas",
        "warn_columnas_incompletas_msg": "Você deve selecionar a coluna X/Este e a coluna Y/Norte do CSV.",
        "warn_columnas_repetidas_titulo": "Colunas repetidas",
        "warn_columnas_repetidas_msg": "As colunas X, Y e Z devem ser diferentes entre si.",
        "warn_falta_salida_titulo": "Falta o caminho de saída",
        "warn_falta_salida_msg": "Indique onde salvar o CSV recalculado.",
        "warn_falta_shp_titulo": "Falta o caminho do Shapefile",
        "warn_falta_shp_msg": "Indique onde salvar o Shapefile (.shp).",
        "warn_falta_dxf_titulo": "Falta o caminho do DXF",
        "warn_falta_dxf_msg": "Indique onde salvar o DXF (.dxf).",
        "warn_falta_reporte_titulo": "Falta o caminho do relatório",
        "warn_falta_reporte_msg": "Indique onde salvar o relatório técnico (.html).",
        "warn_crs_invalido_titulo": "SRC inválido",
        "warn_crs_invalido_msg": "Selecione um sistema de referência plano e um geográfico válidos.",
        "err_sin_datos_validos_titulo": "Nenhum dado válido",
        "err_sin_datos_validos_msg": "Nenhuma linha do CSV pôde ser processada. Verifique as colunas selecionadas.",
        "err_guardar_titulo": "Erro ao salvar",
        "err_guardar_msg": "Não foi possível gravar o arquivo de saída:\n{error}",
        "info_proceso_terminado_titulo": "Processo concluído",

        "err_base_xy_invalida": "Coordenadas X/Y da {nombre_base} inválidas: {error}",
        "err_base_z_invalida": "Elevação Z da {nombre_base} inválida: {error}",
        "nombre_base_libre": "base livre",
        "nombre_base_ajustada": "base ajustada",

        "log_columnas_cargadas": "Foram carregadas {n_col} colunas e {n_filas} linhas de dados de: {archivo}",
        "log_vector_calculado": "Vetor de translação calculado:  ΔX = {dx}   ΔY = {dy}   ΔZ = {dz}",
        "log_dz_na": "N/D (sem elevação em ambas as bases)",
        "log_recalculo_ok": "Foram recalculados {ok} de {total} pontos corretamente.",
        "log_filas_omitidas": "{n} linha(s) foram omitidas por erros de formato (ver detalhe abaixo).",
        "log_fila_error": "  Linha {num}: {msg}",
        "log_mas_errores": "  ... e mais {n} erro(s).",
        "log_errores_transform": "{n} ponto(s) não puderam ser reprojetados para coordenadas geográficas.",
        "log_archivo_generado": "Arquivo gerado: {ruta}",
        "log_no_capa_shp": "Não foi possível preparar a camada para exportar para Shapefile.",
        "log_shp_generado": "Shapefile gerado: {ruta}",
        "log_shp_error": "Não foi possível gerar o Shapefile: {msg}",
        "log_dxf_generado": "DXF gerado: {ruta}",
        "log_dxf_error": "Não foi possível gerar o DXF: {msg}",
        "log_reporte_generado": "Relatório técnico gerado: {ruta}",
        "log_reporte_error": "Não foi possível gerar o relatório técnico: {msg}",

        "resumen_principal": "O arquivo foi gerado:\n{ruta}\n\nPontos processados: {procesados}\nPontos omitidos: {omitidos}",
        "resumen_shp": "\nShapefile: {ruta}",
        "resumen_dxf": "\nDXF: {ruta}",
        "resumen_reporte": "\nRelatório técnico: {ruta}",
        "resumen_reporte_no_generado": "não foi possível gerar (ver registro)",

        "capa_ajustada_nombre": "Pontos ajustados (RTK)",
        "capa_libre_nombre": "Pontos livres (originais)",

        "plugin_menu": "&Recálculo RTK para Ajustada",
        "plugin_accion": "Recalcular coordenadas RTK (livre → ajustada)",
        "plugin_whatsthis": (
            "Recalcula um CSV de pontos levantados com RTK, transladando-os "
            "de uma base de coordenadas livres para a coordenada ajustada "
            "obtida por pós-processamento estático."
        ),

        "rpt_titulo": "Relatório Técnico de Recálculo RTK",
        "rpt_subtitulo": "Translação de coordenadas de base livre para base ajustada (pós-processamento estático)",
        "rpt_fecha": "Data do relatório",
        "rpt_complemento": "Complemento",
        "rpt_nombre_plugin": "Recálculo RTK para Coordenadas Ajustadas",
        "rpt_archivo_entrada": "Arquivo de entrada",
        "rpt_archivo_salida": "Arquivo de saída",
        "rpt_proyecto": "Projeto",
        "rpt_responsable": "Responsável",
        "rpt_h2_1": "1. Sistemas de referência",
        "rpt_h2_2": "2. Coordenadas da base e vetor de translação",
        "rpt_h2_3": "3. Resumo do processo",
        "rpt_h2_4": "4. Lista de pontos recalculados",
        "rpt_crs_plano_titulo": "SRC plano / projetado (usado em X, Y)",
        "rpt_crs_geo_titulo": "SRC geográfico de saída (usado em Longitude, Latitude)",
        "rpt_tabla_base_header_base": "Base",
        "rpt_tabla_base_header_x": "X / Este",
        "rpt_tabla_base_header_y": "Y / Norte",
        "rpt_tabla_base_header_z": "Z / Elevação",
        "rpt_base_libre_row": "Livre (tomada em campo)",
        "rpt_base_ajustada_row": "Ajustada (pós-processamento estático)",
        "rpt_vector_row": "Vetor de translação (Δ)",
        "rpt_metodo_parrafo": (
            "Método: translação rígida, com o mesmo vetor (&Delta;X, &Delta;Y, "
            "&Delta;Z) aplicado a todos os pontos, segundo:&nbsp; "
            "<i>ponto_ajustado = ponto_livre + (base_ajustada &minus; "
            "base_livre)</i>. Válido para uma única base RTK com radiações de "
            "curta/média distância (sem rotação nem escala)."
        ),
        "rpt_resumen_filas_csv": "Linhas de dados no CSV de entrada",
        "rpt_resumen_procesados": "Pontos recalculados corretamente",
        "rpt_resumen_omitidos": "Linhas omitidas por erro de formato",
        "rpt_resumen_errores_transform": "Pontos não reprojetados para geográficas",
        "rpt_errores_h2": "Linhas omitidas por erro de formato",
        "rpt_errores_item": "Linha {num}: {msg}",
        "rpt_nota_puntos": (
            "Coordenadas X, Y, Z nas unidades do SRC plano/projetado indicado na "
            "seção 1, com 3 decimais. Coordenadas geográficas em formato "
            "graus-minutos-segundos (5 decimais nos segundos)."
        ),
        "rpt_col_punto": "Ponto",
        "rpt_col_x": "X",
        "rpt_col_y": "Y",
        "rpt_col_z": "Z",
        "rpt_col_x_adj": "X ajustado",
        "rpt_col_y_adj": "Y ajustado",
        "rpt_col_z_adj": "Z ajustado",
        "rpt_col_lon": "Longitude",
        "rpt_col_lat": "Latitude",
        "rpt_cierre": (
            'Fim do relatório — gerado automaticamente pelo complemento '
            '"{nombre_plugin}" (v{version}) para o QGIS.'
        ),

        "crs_nombre": "Nome",
        "crs_proyeccion": "Projeção",
        "crs_wkid": "WKID",
        "crs_autoridad": "Autoridade",
        "crs_unidad_lineal": "Unidade linear",
        "crs_false_easting": "Falso Este (False Easting)",
        "crs_false_northing": "Falso Norte (False Northing)",
        "crs_meridiano_central": "Meridiano central",
        "crs_factor_escala": "Fator de escala",
        "crs_latitud_origen": "Latitude de origem",
        "crs_area_uso": "Área de uso",
        "crs_unidad_angular": "Unidade angular",
        "crs_primer_meridiano": "Primeiro meridiano",
        "crs_datum": "Datum",
        "crs_esferoide": "Esferoide",
        "crs_semieje_mayor": "Semieixo maior",
        "crs_semieje_menor": "Semieixo menor",
        "crs_aplanamiento_inverso": "Achatamento inverso",
        "crs_subtabla_proyectado": "Sistema de coordenadas projetado",
        "crs_subtabla_geografico": "Sistema de coordenadas geográfico",
        "crs_nombre_epsg": "Nome (EPSG)",
        "crs_unidades": "Unidades",
        "crs_datum_estatico": "Estático (datum fixo à placa tectônica)",
        "crs_datum_dinamico": "Dinâmico (datum não fixo à placa tectônica)",
        "crs_cuerpo_celeste": "Corpo celeste",
        "crs_metodo_proyeccion": "Método de projeção",
        "crs_no_disponible": "Não disponível.",
        "crs_nd": "N/D",
    },
}
