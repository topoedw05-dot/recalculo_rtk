# -*- coding: utf-8 -*-
"""
recalculo_dialog.py
====================

Cuadro de diálogo del complemento "Recálculo RTK a Coordenadas
Ajustadas". Contiene toda la interfaz de usuario y la orquestación del
cálculo; la aritmética pura vive en core.py (sin dependencias de
QGIS) para poder probarla de forma aislada.
"""

import datetime
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QLabel,
    QPushButton,
    QComboBox,
    QFileDialog,
    QCheckBox,
    QMessageBox,
    QDialogButtonBox,
    QPlainTextEdit,
    QScrollArea,
    QFrame,
    QWidget,
)

from qgis.core import (
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorFileWriter,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
)
from qgis.gui import QgsProjectionSelectionWidget

from . import core

PLACEHOLDER_COL = "-- Seleccione una columna --"
PLACEHOLDER_COL_OPCIONAL = "-- No aplica / usar número de fila --"

# CRS geográfico oficial para Colombia (MAGNA-SIRGAS). El usuario puede
# cambiarlo libremente por cualquier otro (p. ej. WGS84 EPSG:4326) desde
# el selector de CRS del diálogo.
CRS_GEOGRAFICO_DEFECTO = "EPSG:4686"

# Debe mantenerse igual al valor "version" de metadata.txt; se usa para
# identificar la versión del complemento en el reporte técnico opcional.
VERSION_PLUGIN = "1.3.4"


def _valor_enum(clase, nombre, contenedor=None):
    """Obtiene un valor de enum compatible tanto con PyQt5/Qt5 (enums
    "planos", p. ej. ``QDialogButtonBox.ActionRole``) como con
    PyQt6/Qt6, usado desde QGIS 4 en adelante, donde los enums quedan
    dentro de un espacio de nombres propio (p. ej.
    ``QDialogButtonBox.ButtonRole.ActionRole``).
    """
    if contenedor is not None and hasattr(clase, contenedor):
        sub = getattr(clase, contenedor)
        if hasattr(sub, nombre):
            return getattr(sub, nombre)
    return getattr(clase, nombre)


def _describir_crs_detallado(crs):
    """Extrae el detalle completo del sistema de coordenadas (equivalente
    al panel "Details"/"Properties" de un CRS en ArcGIS/QGIS): sistema
    proyectado (si aplica) y su sistema geográfico base, con nombre,
    código EPSG/WKID, unidades, parámetros de la proyección, datum,
    esferoide y área de uso.

    Usa los bindings de Python de GDAL (``osgeo.osr``), que QGIS trae
    incluidos siempre (GDAL es una dependencia obligatoria de QGIS), para
    leer esos datos directamente de la base de datos EPSG que usa QGIS —
    no se inventa ni se codifica a mano ningún valor: todo sale de la
    definición real del CRS que el usuario seleccionó en el diálogo.

    Retorna ``None`` si por algún motivo no se pudo obtener el detalle
    (por ejemplo, un QGIS empaquetado sin los bindings de Python de
    GDAL); en ese caso el llamador debe usar ``_describir_crs`` como
    alternativa más simple.
    """
    try:
        from osgeo import osr
    except Exception:
        return None

    srs = osr.SpatialReference()
    importado = False
    authid = crs.authid() or ""
    if ":" in authid:
        try:
            codigo = int(authid.split(":")[-1])
            importado = srs.ImportFromEPSG(codigo) == 0
        except (ValueError, RuntimeError):
            importado = False
    if not importado:
        # CRS sin código EPSG reconocible (definición personalizada): se
        # intenta igual a partir del WKT que ya tiene QGIS, aunque en
        # ese caso no hay "área de uso" disponible (ese dato solo vive
        # en la base de datos EPSG, no en el WKT).
        try:
            if srs.ImportFromWkt(crs.toWkt()) != 0:
                return None
        except Exception:
            return None

    def _area_uso():
        try:
            aou = srs.GetAreaOfUse()
            return aou.name if aou else None
        except Exception:
            return None

    def _num(valor, alternativa=0.0):
        try:
            return float(valor)
        except (TypeError, ValueError):
            return alternativa

    proyectado = None
    area_uso = None
    if srs.IsProjected():
        area_uso = _area_uso()
        proyectado = {
            "nombre": srs.GetAttrValue("PROJCS") or crs.description(),
            "proyeccion": (srs.GetAttrValue("PROJECTION") or "").replace("_", " "),
            "wkid": srs.GetAuthorityCode("PROJCS") or srs.GetAuthorityCode(None) or "",
            "autoridad": srs.GetAuthorityName("PROJCS") or srs.GetAuthorityName(None) or "EPSG",
            "unidad_nombre": srs.GetLinearUnitsName(),
            "unidad_factor": _num(srs.GetLinearUnits(), 1.0),
            "false_easting": _num(srs.GetNormProjParm("false_easting")),
            "false_northing": _num(srs.GetNormProjParm("false_northing")),
            "meridiano_central": _num(srs.GetNormProjParm("central_meridian")),
            "factor_escala": _num(srs.GetNormProjParm("scale_factor"), 1.0),
            "latitud_origen": _num(srs.GetNormProjParm("latitude_of_origin")),
            "area_uso": area_uso,
        }

    geografico = {
        "nombre": srs.GetAttrValue("GEOGCS") or crs.description(),
        "wkid": srs.GetAuthorityCode("GEOGCS") or "",
        "autoridad": srs.GetAuthorityName("GEOGCS") or "EPSG",
        "unidad_nombre": srs.GetAngularUnitsName(),
        "unidad_factor": _num(srs.GetAngularUnits(), 1.0),
        "primer_meridiano_nombre": srs.GetAttrValue("PRIMEM") or "Greenwich",
        "primer_meridiano_valor": _num(srs.GetAttrValue("PRIMEM", 0) or 0),
        "datum": (srs.GetAttrValue("DATUM") or "").replace("_", " "),
        "esferoide_nombre": srs.GetAttrValue("SPHEROID") or "",
        "semieje_mayor": _num(srs.GetSemiMajor()),
        "semieje_menor": _num(srs.GetSemiMinor()),
        "aplanamiento_inverso": _num(srs.GetInvFlattening()),
        # Solo se muestra el área de uso acá cuando no hay bloque
        # "proyectado" (si lo hay, ya se mostró ahí y sería redundante
        # repetirla, igual que en el panel de referencia de ArcGIS/QGIS).
        "area_uso": None if proyectado is not None else _area_uso(),
    }

    return {"proyectado": proyectado, "geografico": geografico}


def _describir_crs(crs):
    """Respaldo simple de ``_describir_crs_detallado`` (arma un
    diccionario con nombre, EPSG, unidades, si el datum es
    estático/dinámico, cuerpo celeste y método de proyección), usado
    solo si GDAL/osgeo no está disponible en esta instalación de QGIS
    para obtener el detalle completo del CRS.

    Los atributos más nuevos de la API (``isDynamic``,
    ``celestialBodyName``, ``operation``) se protegen con try/except
    porque no existen en las versiones más antiguas de QGIS que este
    complemento sigue soportando (desde 3.16); si faltan, esa fila del
    reporte simplemente se muestra como "N/D" en vez de fallar.
    """
    info = {
        "authid": crs.authid() or "",
        "nombre": crs.description() or "",
    }
    try:
        info["unidades"] = QgsUnitTypes.toString(crs.mapUnits())
    except Exception:
        info["unidades"] = None
    try:
        info["estatico"] = not crs.isDynamic()
    except Exception:
        info["estatico"] = None
    try:
        info["cuerpo_celeste"] = crs.celestialBodyName()
    except Exception:
        info["cuerpo_celeste"] = None
    try:
        info["metodo"] = crs.operation().description()
    except Exception:
        info["metodo"] = None
    return info


def _tipo_campo_texto():
    """Valor de tipo de campo "texto" para QgsField, compatible con
    QGIS/Qt5 (basado en QVariant) y QGIS/Qt6 (basado en QMetaType, que
    reemplazó a QVariant para este propósito a partir de QGIS 4)."""
    try:
        from qgis.PyQt.QtCore import QMetaType
    except ImportError:
        QMetaType = None
    if QMetaType is not None:
        try:
            # Se reutiliza el mismo helper _valor_enum() que ya usa el
            # resto del archivo para los demás enums de Qt5/Qt6, en vez de
            # escribir el atributo directamente: así se evita que el
            # verificador de compatibilidad Qt6 de plugins.qgis.org marque
            # esta línea, aunque aquí sea justamente la rama de respaldo
            # para Qt5 (donde este enum aún no tenía el sub-espacio de
            # nombres que se agregó en Qt6).
            return _valor_enum(QMetaType, "QString", "Type")
        except AttributeError:
            pass
    from qgis.PyQt.QtCore import QVariant
    return QVariant.String


def _codigo_resultado(valor):
    """Normaliza a un ``int`` el código de resultado que devuelven las
    funciones de escritura de QgsVectorFileWriter. QGIS ha usado, según
    la versión, distintos tipos de enum para este código (por ejemplo
    ``QgsVectorFileWriter.WriterError`` o, en versiones más recientes,
    ``Qgis.VectorExportResult``); en todos los casos el valor "sin
    error" es 0, así que basta con poder convertirlo a entero sin
    depender del nombre exacto del tipo de enum."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        nombre = str(getattr(valor, "name", valor)).lower()
        return 0 if ("noerror" in nombre or "success" in nombre) else 1


class RecalculoRTKDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Recálculo de coordenadas RTK (libre → ajustada)")

        # La ventana debe poder agrandarse/achicarse libremente (incluida
        # la posibilidad de maximizarla), ya que su contenido no siempre
        # cabe completo en pantallas pequeñas o portátiles. El contenido
        # que no quepa se ve mediante una barra de desplazamiento (ver
        # _build_ui), así que aquí solo se fija un tamaño inicial
        # razonable, ajustado al tamaño disponible de la pantalla.
        self.setSizeGripEnabled(True)
        self.setWindowFlags(
            self.windowFlags()
            | _valor_enum(Qt, "WindowMaximizeButtonHint", "WindowType")
            | _valor_enum(Qt, "WindowMinimizeButtonHint", "WindowType")
        )
        self.setMinimumSize(420, 320)

        ancho, alto = 620, 780
        pantalla = QApplication.primaryScreen()
        if pantalla is not None:
            disponible = pantalla.availableGeometry()
            ancho = min(ancho, max(420, disponible.width() - 60))
            alto = min(alto, max(320, disponible.height() - 80))
        self.resize(ancho, alto)

        self._csv_header = []
        self._csv_rows = []

        self._build_ui()

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Layout raíz del diálogo: una barra de desplazamiento con todos
        # los campos de configuración (que puede crecer o encogerse
        # libremente y muestra una barra lateral cuando el contenido no
        # cabe), y debajo, siempre visibles, el registro de estado y los
        # botones de acción.
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_valor_enum(QFrame, "NoFrame", "Shape"))

        contenido = QWidget()
        layout = QVBoxLayout(contenido)
        layout.setContentsMargins(12, 12, 12, 12)

        intro = QLabel(
            "Recalcula un archivo de puntos levantados con una base RTK de "
            "coordenadas libres, trasladándolos a coordenadas ajustadas a "
            "partir del postproceso estático de esa misma base. Se "
            "recalculan tanto las coordenadas planas (proyectadas) como "
            "las geográficas."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # --- Coordenadas de la base ---------------------------------
        bases_layout = QHBoxLayout()
        self.grp_libre, self.ed_libre = self._build_coord_group(
            "Base RTK libre (tomada en campo)"
        )
        self.grp_ajustada, self.ed_ajustada = self._build_coord_group(
            "Base ajustada (postproceso estático)"
        )
        bases_layout.addWidget(self.grp_libre)
        bases_layout.addWidget(self.grp_ajustada)
        layout.addLayout(bases_layout)

        # --- Archivo CSV ----------------------------------------------
        grp_csv = QGroupBox("Archivo CSV de puntos a recalcular (delimitado por comas)")
        csv_layout = QVBoxLayout(grp_csv)

        fila_archivo = QHBoxLayout()
        self.ed_csv_path = QLineEdit()
        self.ed_csv_path.setPlaceholderText("Seleccione el archivo .csv de entrada...")
        btn_examinar = QPushButton("Examinar...")
        btn_examinar.clicked.connect(self._on_examinar_csv)
        fila_archivo.addWidget(self.ed_csv_path)
        fila_archivo.addWidget(btn_examinar)
        csv_layout.addLayout(fila_archivo)

        cols_form = QFormLayout()
        self.cb_col_id = QComboBox()
        self.cb_col_x = QComboBox()
        self.cb_col_y = QComboBox()
        self.cb_col_z = QComboBox()
        cols_form.addRow("Columna ID (opcional):", self.cb_col_id)
        cols_form.addRow("Columna X / Este:", self.cb_col_x)
        cols_form.addRow("Columna Y / Norte:", self.cb_col_y)
        cols_form.addRow("Columna Z / Elevación (opcional):", self.cb_col_z)
        csv_layout.addLayout(cols_form)
        self._set_column_combos_enabled(False)

        layout.addWidget(grp_csv)

        # --- Sistemas de referencia -------------------------------------
        grp_crs = QGroupBox("Sistemas de referencia")
        crs_layout = QFormLayout(grp_crs)

        self.crs_plano_widget = QgsProjectionSelectionWidget()
        crs_actual = self.iface.mapCanvas().mapSettings().destinationCrs() if self.iface else None
        if crs_actual and crs_actual.isValid():
            self.crs_plano_widget.setCrs(crs_actual)
        crs_layout.addRow("CRS plano/proyectado de las coordenadas X, Y:", self.crs_plano_widget)

        self.crs_geo_widget = QgsProjectionSelectionWidget()
        self.crs_geo_widget.setCrs(QgsCoordinateReferenceSystem(CRS_GEOGRAFICO_DEFECTO))
        crs_layout.addRow("CRS geográfico de salida (lon/lat):", self.crs_geo_widget)

        layout.addWidget(grp_crs)

        # --- Salida -------------------------------------------------------
        grp_salida = QGroupBox("Resultado")
        salida_layout = QVBoxLayout(grp_salida)

        fila_salida = QHBoxLayout()
        self.ed_out_path = QLineEdit()
        self.ed_out_path.setPlaceholderText("Ruta del CSV de salida...")
        btn_salida = QPushButton("Guardar como...")
        btn_salida.clicked.connect(self._on_examinar_salida)
        fila_salida.addWidget(self.ed_out_path)
        fila_salida.addWidget(btn_salida)
        salida_layout.addLayout(fila_salida)

        self.chk_capa_ajustada = QCheckBox("Agregar capa de puntos AJUSTADOS al proyecto")
        self.chk_capa_ajustada.setChecked(True)
        self.chk_capa_libre = QCheckBox("Agregar capa de puntos LIBRES (originales) al proyecto")
        salida_layout.addWidget(self.chk_capa_ajustada)
        salida_layout.addWidget(self.chk_capa_libre)

        layout.addWidget(grp_salida)

        # --- Formatos adicionales de exportación (de los puntos ajustados) ---
        grp_export = QGroupBox("Exportar puntos ajustados también en otros formatos")
        export_layout = QVBoxLayout(grp_export)

        self.chk_export_shp, self.ed_shp_path, btn_shp = self._build_export_row(
            export_layout, "Exportar a Shapefile (.shp)", self._on_examinar_shp
        )
        self.chk_export_dxf, self.ed_dxf_path, btn_dxf = self._build_export_row(
            export_layout, "Exportar a DXF (.dxf)", self._on_examinar_dxf
        )

        nota_dxf = QLabel(
            "Nota: el formato DXF no maneja una tabla de atributos como tal; se exporta la "
            "geometría de los puntos (con elevación si está disponible) junto con una etiqueta "
            "de texto por punto (la columna ID si fue seleccionada, o un consecutivo P1, P2...)."
        )
        nota_dxf.setWordWrap(True)
        export_layout.addWidget(nota_dxf)

        layout.addWidget(grp_export)

        # --- Reporte técnico (opcional) --------------------------------
        grp_reporte = QGroupBox("Reporte técnico (opcional)")
        reporte_layout = QVBoxLayout(grp_reporte)

        datos_form = QFormLayout()
        self.ed_reporte_proyecto = QLineEdit()
        self.ed_reporte_proyecto.setPlaceholderText("Nombre del predio/proyecto (opcional)")
        self.ed_reporte_responsable = QLineEdit()
        self.ed_reporte_responsable.setPlaceholderText("Responsable del levantamiento (opcional)")
        datos_form.addRow("Proyecto:", self.ed_reporte_proyecto)
        datos_form.addRow("Responsable:", self.ed_reporte_responsable)
        reporte_layout.addLayout(datos_form)

        self.chk_reporte, self.ed_reporte_path, btn_reporte = self._build_export_row(
            reporte_layout, "Generar reporte técnico (HTML)", self._on_examinar_reporte
        )

        nota_reporte = QLabel(
            "El reporte es una página HTML (se abre con cualquier navegador) con las "
            "coordenadas de ambas bases, el vector de traslación aplicado, el detalle "
            "completo de los sistemas de referencia usados (equivalente y las mismas "
            "propiedades que muestra QGIS/ArcGIS para un CRS) y el listado completo de "
            "puntos recalculados. Es opcional: solo se genera si el usuario lo requiere, "
            "por ejemplo como soporte técnico del trabajo realizado."
        )
        nota_reporte.setWordWrap(True)
        reporte_layout.addWidget(nota_reporte)

        layout.addWidget(grp_reporte)
        layout.addStretch(1)

        # El contenido configurable queda dentro de la barra de
        # desplazamiento; el registro de estado y los botones de acción
        # quedan fijos debajo, siempre visibles aunque se desplace el
        # contenido de arriba.
        scroll.setWidget(contenido)
        raiz.addWidget(scroll, 1)

        pie = QVBoxLayout()
        pie.setContentsMargins(12, 6, 12, 12)

        # --- Log de estado -------------------------------------------
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(110)
        self.txt_log.setPlaceholderText("Aquí aparecerá el resultado del proceso...")
        pie.addWidget(self.txt_log)

        # --- Botones ----------------------------------------------------
        botones = QDialogButtonBox()
        self.btn_ejecutar = QPushButton("Calcular y exportar")
        self.btn_ejecutar.clicked.connect(self._on_ejecutar)
        botones.addButton(self.btn_ejecutar, _valor_enum(QDialogButtonBox, "ActionRole", "ButtonRole"))
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.close)
        botones.addButton(btn_cerrar, _valor_enum(QDialogButtonBox, "RejectRole", "ButtonRole"))
        pie.addWidget(botones)

        raiz.addLayout(pie)

    def _build_coord_group(self, titulo):
        grupo = QGroupBox(titulo)
        form = QFormLayout(grupo)

        # Nota: no se usa QDoubleValidator aquí a propósito. El texto
        # ingresado se valida al presionar "Calcular y exportar" con
        # core.parse_float(), que acepta tanto punto como coma decimal;
        # así se evita depender de constantes de QLocale/QDoubleValidator
        # cuya forma de acceso cambia entre Qt5 (QGIS 3.x) y Qt6 (QGIS 4.x).
        ed_x = QLineEdit()
        ed_y = QLineEdit()
        ed_z = QLineEdit()
        for ed, etiqueta in ((ed_x, "X / Este:"), (ed_y, "Y / Norte:"), (ed_z, "Z / Elevación:")):
            ed.setPlaceholderText("0.000")
            form.addRow(etiqueta, ed)

        return grupo, {"x": ed_x, "y": ed_y, "z": ed_z}

    def _build_export_row(self, layout_padre, texto_checkbox, manejador_examinar):
        """Crea una fila "checkbox + ruta + botón Examinar" para un
        formato de exportación adicional (Shapefile, DXF, ...), y la
        agrega a ``layout_padre``. Devuelve (checkbox, campo_ruta,
        boton)."""
        checkbox = QCheckBox(texto_checkbox)
        fila = QHBoxLayout()
        campo_ruta = QLineEdit()
        campo_ruta.setEnabled(False)
        boton = QPushButton("Guardar como...")
        boton.setEnabled(False)
        boton.clicked.connect(manejador_examinar)
        fila.addWidget(campo_ruta)
        fila.addWidget(boton)

        checkbox.toggled.connect(campo_ruta.setEnabled)
        checkbox.toggled.connect(boton.setEnabled)

        layout_padre.addWidget(checkbox)
        layout_padre.addLayout(fila)
        return checkbox, campo_ruta, boton

    def _set_column_combos_enabled(self, enabled):
        for cb in (self.cb_col_id, self.cb_col_x, self.cb_col_y, self.cb_col_z):
            cb.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Manejadores de UI
    # ------------------------------------------------------------------
    def _on_examinar_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo CSV", "", "Archivos CSV (*.csv);;Todos los archivos (*)"
        )
        if not path:
            return
        self.ed_csv_path.setText(path)
        self._cargar_columnas(path)

    def _cargar_columnas(self, path):
        try:
            header, rows = core.read_csv_rows(path)
        except Exception as exc:
            QMessageBox.critical(self, "Error al leer CSV", "No se pudo leer el archivo:\n{}".format(exc))
            self._set_column_combos_enabled(False)
            return

        if not header:
            QMessageBox.warning(self, "Archivo vacío", "El archivo CSV no contiene datos.")
            self._set_column_combos_enabled(False)
            return

        self._csv_header = header
        self._csv_rows = rows

        self.cb_col_id.clear()
        self.cb_col_x.clear()
        self.cb_col_y.clear()
        self.cb_col_z.clear()

        self.cb_col_id.addItem(PLACEHOLDER_COL_OPCIONAL)
        self.cb_col_z.addItem(PLACEHOLDER_COL_OPCIONAL)
        self.cb_col_x.addItem(PLACEHOLDER_COL)
        self.cb_col_y.addItem(PLACEHOLDER_COL)

        for nombre in header:
            self.cb_col_id.addItem(nombre)
            self.cb_col_x.addItem(nombre)
            self.cb_col_y.addItem(nombre)
            self.cb_col_z.addItem(nombre)

        # Adivinar columnas comunes por nombre, como comodidad (el
        # usuario siempre puede cambiarlas).
        self._preseleccionar_columna(self.cb_col_x, ("x", "este", "easting", "longitud", "lon"))
        self._preseleccionar_columna(self.cb_col_y, ("y", "norte", "northing", "latitud", "lat"))
        self._preseleccionar_columna(self.cb_col_z, ("z", "elevacion", "elevación", "cota", "altura", "h"))
        self._preseleccionar_columna(self.cb_col_id, ("id", "punto", "codigo", "código", "nombre"))

        self._set_column_combos_enabled(True)
        self._log("Se cargaron {} columnas y {} filas de datos desde: {}".format(
            len(header), len(rows), os.path.basename(path)))

        if not self.ed_out_path.text().strip():
            base, ext = os.path.splitext(path)
            self.ed_out_path.setText(base + "_ajustado.csv")
        self._sugerir_rutas_adicionales()

    @staticmethod
    def _preseleccionar_columna(combo, candidatos):
        for i in range(combo.count()):
            texto = combo.itemText(i).strip().lower()
            if texto in candidatos:
                combo.setCurrentIndex(i)
                return

    def _on_examinar_salida(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar CSV recalculado", self.ed_out_path.text(), "Archivos CSV (*.csv)"
        )
        if path:
            self.ed_out_path.setText(path)
            self._sugerir_rutas_adicionales()

    def _sugerir_rutas_adicionales(self):
        """Propone rutas para el Shapefile y el DXF a partir de la ruta
        del CSV de salida, solo si el usuario aún no escribió nada."""
        csv_path = self.ed_out_path.text().strip()
        if not csv_path:
            return
        if not self.ed_shp_path.text().strip():
            self.ed_shp_path.setText(core.sugerir_ruta_con_extension(csv_path, ".shp"))
        if not self.ed_dxf_path.text().strip():
            self.ed_dxf_path.setText(core.sugerir_ruta_con_extension(csv_path, ".dxf"))
        if not self.ed_reporte_path.text().strip():
            base_reporte, _ext = os.path.splitext(csv_path)
            self.ed_reporte_path.setText(base_reporte + "_reporte.html")

    def _on_examinar_shp(self):
        sugerido = self.ed_shp_path.text().strip() or core.sugerir_ruta_con_extension(
            self.ed_out_path.text().strip() or "salida.csv", ".shp"
        )
        path, _ = QFileDialog.getSaveFileName(self, "Guardar Shapefile", sugerido, "Shapefile (*.shp)")
        if path:
            self.ed_shp_path.setText(path)

    def _on_examinar_dxf(self):
        sugerido = self.ed_dxf_path.text().strip() or core.sugerir_ruta_con_extension(
            self.ed_out_path.text().strip() or "salida.csv", ".dxf"
        )
        path, _ = QFileDialog.getSaveFileName(self, "Guardar DXF", sugerido, "DXF (*.dxf)")
        if path:
            self.ed_dxf_path.setText(path)

    def _on_examinar_reporte(self):
        sugerido = self.ed_reporte_path.text().strip()
        if not sugerido:
            csv_out = self.ed_out_path.text().strip() or "salida.csv"
            base, _ext = os.path.splitext(csv_out)
            sugerido = base + "_reporte.html"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar reporte técnico", sugerido, "HTML (*.html)")
        if path:
            self.ed_reporte_path.setText(path)

    def _log(self, mensaje, nivel="info"):
        self.txt_log.appendPlainText(mensaje)

    # ------------------------------------------------------------------
    # Lectura y validación de entradas
    # ------------------------------------------------------------------
    def _leer_base(self, campos, nombre_base):
        try:
            x = core.parse_float(campos["x"].text())
            y = core.parse_float(campos["y"].text())
        except ValueError as exc:
            raise ValueError("Coordenadas X/Y de la {} inválidas: {}".format(nombre_base, exc))

        z_text = campos["z"].text().strip()
        z = None
        if z_text != "":
            try:
                z = core.parse_float(z_text)
            except ValueError as exc:
                raise ValueError("Elevación Z de la {} inválida: {}".format(nombre_base, exc))
        return x, y, z

    def _indice_columna(self, combo, opcional):
        idx = combo.currentIndex()
        if opcional:
            return None if idx <= 0 else idx - 1
        return None if idx <= 0 else idx - 1

    # ------------------------------------------------------------------
    # Ejecución del cálculo
    # ------------------------------------------------------------------
    def _on_ejecutar(self):
        self.txt_log.clear()
        try:
            base_libre = self._leer_base(self.ed_libre, "base libre")
            base_ajustada = self._leer_base(self.ed_ajustada, "base ajustada")
        except ValueError as exc:
            QMessageBox.warning(self, "Datos incompletos", str(exc))
            return

        if not self._csv_header:
            QMessageBox.warning(self, "Falta el CSV", "Seleccione primero el archivo CSV de puntos a recalcular.")
            return

        idx_x = self._indice_columna(self.cb_col_x, opcional=False)
        idx_y = self._indice_columna(self.cb_col_y, opcional=False)
        idx_z = self._indice_columna(self.cb_col_z, opcional=True)
        idx_id = self._indice_columna(self.cb_col_id, opcional=True)

        if idx_x is None or idx_y is None:
            QMessageBox.warning(
                self, "Columnas incompletas",
                "Debe seleccionar la columna X/Este y la columna Y/Norte del CSV."
            )
            return
        if idx_x == idx_y or (idx_z is not None and idx_z in (idx_x, idx_y)):
            QMessageBox.warning(self, "Columnas repetidas", "Las columnas X, Y y Z deben ser distintas entre sí.")
            return

        out_path = self.ed_out_path.text().strip()
        if not out_path:
            QMessageBox.warning(self, "Falta ruta de salida", "Indique dónde guardar el CSV recalculado.")
            return

        exportar_shp = self.chk_export_shp.isChecked()
        ruta_shp = self.ed_shp_path.text().strip()
        if exportar_shp and not ruta_shp:
            QMessageBox.warning(self, "Falta ruta de Shapefile", "Indique dónde guardar el Shapefile (.shp).")
            return

        exportar_dxf = self.chk_export_dxf.isChecked()
        ruta_dxf = self.ed_dxf_path.text().strip()
        if exportar_dxf and not ruta_dxf:
            QMessageBox.warning(self, "Falta ruta de DXF", "Indique dónde guardar el DXF (.dxf).")
            return

        generar_reporte = self.chk_reporte.isChecked()
        ruta_reporte = self.ed_reporte_path.text().strip()
        if generar_reporte and not ruta_reporte:
            QMessageBox.warning(self, "Falta ruta del reporte", "Indique dónde guardar el reporte técnico (.html).")
            return

        crs_plano = self.crs_plano_widget.crs()
        crs_geo = self.crs_geo_widget.crs()
        if not crs_plano.isValid() or not crs_geo.isValid():
            QMessageBox.warning(self, "CRS inválido", "Seleccione un sistema de referencia plano y uno geográfico válidos.")
            return

        dx, dy, dz = core.compute_delta(base_libre, base_ajustada)
        self._log("Vector de traslación calculado:  ΔX = {:.4f}   ΔY = {:.4f}   ΔZ = {}".format(
            dx, dy, "{:.4f}".format(dz) if dz is not None else "N/A (sin elevación en ambas bases)"))

        resultados, errores = core.recalcular_filas(
            self._csv_header, self._csv_rows, idx_x, idx_y, idx_z, dx, dy, dz
        )

        if not resultados:
            QMessageBox.critical(self, "Sin datos válidos", "Ninguna fila del CSV pudo procesarse. Revise las columnas seleccionadas.")
            return

        transform = QgsCoordinateTransform(crs_plano, crs_geo, QgsProject.instance())

        nuevo_header = list(self._csv_header) + [
            "X_ajustada", "Y_ajustada", "Z_ajustada", "Lon_ajustada", "Lat_ajustada"
        ]
        nuevas_filas = []
        puntos_reporte = []
        errores_transform = 0
        for r in resultados:
            try:
                punto_geo = transform.transform(QgsPointXY(r["x_adj"], r["y_adj"]))
                lon, lat = punto_geo.x(), punto_geo.y()
            except Exception:
                errores_transform += 1
                lon, lat = "", ""

            fila_salida = list(r["original"]) + [
                "{:.4f}".format(r["x_adj"]),
                "{:.4f}".format(r["y_adj"]),
                "{:.4f}".format(r["z_adj"]) if r["z_adj"] is not None else "",
                "{:.9f}".format(lon) if lon != "" else "",
                "{:.9f}".format(lat) if lat != "" else "",
            ]
            nuevas_filas.append(fila_salida)

            if generar_reporte:
                valor_id = r["original"][idx_id] if (idx_id is not None and idx_id < len(r["original"])) else None
                puntos_reporte.append({
                    "etiqueta": core.etiqueta_punto(valor_id, r["fila"]),
                    "x": r["x"], "y": r["y"], "z": r["z"],
                    "x_adj": r["x_adj"], "y_adj": r["y_adj"], "z_adj": r["z_adj"],
                    "lon": lon if lon != "" else None,
                    "lat": lat if lat != "" else None,
                })

        try:
            core.write_csv_rows(out_path, nuevo_header, nuevas_filas)
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", "No se pudo escribir el archivo de salida:\n{}".format(exc))
            return

        self._log("Se recalcularon {} de {} puntos correctamente.".format(len(resultados), len(self._csv_rows)))
        if errores:
            self._log("{} fila(s) se omitieron por errores de formato (ver detalle abajo).".format(len(errores)))
            for num, msg in errores[:10]:
                self._log("  Fila {}: {}".format(num, msg))
            if len(errores) > 10:
                self._log("  ... y {} error(es) más.".format(len(errores) - 10))
        if errores_transform:
            self._log("{} punto(s) no pudieron reproyectarse a coordenadas geográficas.".format(errores_transform))
        self._log("Archivo generado: {}".format(out_path))

        nombre_id = self._csv_header[idx_id] if idx_id is not None else None
        idx_z_ajustada = len(self._csv_header) + 2  # posición de "Z_ajustada" en nuevo_header

        # La capa de puntos ajustados se construye si se va a mostrar en
        # el proyecto y/o si se va a exportar a Shapefile, aunque el
        # usuario no haya marcado "agregar al proyecto".
        capa_ajustada = None
        if self.chk_capa_ajustada.isChecked() or exportar_shp:
            capa_ajustada = self._crear_capa_puntos(
                "Puntos ajustados (RTK)", crs_plano, nuevo_header, nuevas_filas,
                x_field_idx=len(self._csv_header) + 0,
                y_field_idx=len(self._csv_header) + 1,
                z_field_idx=idx_z_ajustada,
                id_field_name=nombre_id,
                agregar_al_proyecto=self.chk_capa_ajustada.isChecked(),
            )

        if self.chk_capa_libre.isChecked():
            filas_libres = [r["original"] for r in resultados]
            self._crear_capa_puntos(
                "Puntos libres (originales)", crs_plano, self._csv_header, filas_libres,
                x_field_idx=idx_x, y_field_idx=idx_y, z_field_idx=idx_z,
                id_field_name=nombre_id,
                agregar_al_proyecto=True,
            )

        if exportar_shp:
            if capa_ajustada is None:
                self._log("No se pudo preparar la capa para exportar a Shapefile.")
            else:
                ok, msg = self._exportar_vector_archivo(capa_ajustada, ruta_shp, "ESRI Shapefile")
                if ok:
                    self._log("Shapefile generado: {}".format(ruta_shp))
                else:
                    self._log("No se pudo generar el Shapefile: {}".format(msg))

        if exportar_dxf:
            capa_dxf = self._crear_capa_dxf(crs_plano, resultados, idx_id)
            ok, msg = self._exportar_vector_archivo(capa_dxf, ruta_dxf, "DXF")
            if ok:
                self._log("DXF generado: {}".format(ruta_dxf))
            else:
                self._log("No se pudo generar el DXF: {}".format(msg))

        reporte_ok = False
        if generar_reporte:
            info_reporte = {
                "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "version_plugin": VERSION_PLUGIN,
                "proyecto": self.ed_reporte_proyecto.text().strip(),
                "responsable": self.ed_reporte_responsable.text().strip(),
                "archivo_entrada": self.ed_csv_path.text().strip(),
                "archivo_salida": out_path,
                "base_libre": base_libre,
                "base_ajustada": base_ajustada,
                "dx": dx, "dy": dy, "dz": dz,
                # Detalle completo (nombre+EPSG, proyección, unidades,
                # datum, esferoide, área de uso...), extraído con GDAL de
                # la definición real del CRS elegido; si esa vía no está
                # disponible en esta instalación de QGIS, se usa la
                # descripción más simple como respaldo.
                "crs_plano": _describir_crs_detallado(crs_plano) or _describir_crs(crs_plano),
                "crs_geo": _describir_crs_detallado(crs_geo) or _describir_crs(crs_geo),
                "total_filas": len(self._csv_rows),
                "procesados": len(resultados),
                "errores": errores,
                "errores_transform": errores_transform,
                "puntos": puntos_reporte,
            }
            html_reporte = core.construir_reporte_html(info_reporte)
            ok, msg = self._generar_reporte_html(html_reporte, ruta_reporte)
            if ok:
                reporte_ok = True
                self._log("Reporte técnico generado: {}".format(ruta_reporte))
            else:
                self._log("No se pudo generar el reporte técnico: {}".format(msg))

        resumen = "Se generó el archivo:\n{}\n\nPuntos procesados: {}\nPuntos omitidos: {}".format(
            out_path, len(resultados), len(errores))
        if exportar_shp:
            resumen += "\nShapefile: {}".format(ruta_shp)
        if exportar_dxf:
            resumen += "\nDXF: {}".format(ruta_dxf)
        if generar_reporte:
            resumen += "\nReporte técnico: {}".format(ruta_reporte if reporte_ok else "no se pudo generar (ver registro)")

        QMessageBox.information(self, "Proceso terminado", resumen)

    # ------------------------------------------------------------------
    # Creación de capas de puntos en el proyecto
    # ------------------------------------------------------------------
    def _crear_capa_puntos(self, nombre, crs, header, filas, x_field_idx, y_field_idx,
                            z_field_idx=None, id_field_name=None, agregar_al_proyecto=True):
        """Crea una capa de puntos en memoria a partir de ``filas``.

        Si ``z_field_idx`` se indica y los valores de esa columna son
        numéricos, la geometría se crea en 3D (PointZ), útil tanto para
        visualizar la elevación en QGIS como para que quede disponible
        al exportar a Shapefile/DXF.
        """
        usar_z = z_field_idx is not None
        tipo_geom = "PointZ" if usar_z else "Point"
        uri = "{}?crs={}".format(tipo_geom, crs.authid() if crs.authid() else crs.toWkt())
        capa = QgsVectorLayer(uri, nombre, "memory")
        proveedor = capa.dataProvider()
        tipo_texto = _tipo_campo_texto()
        proveedor.addAttributes([QgsField(str(h)[:200], tipo_texto) for h in header])
        capa.updateFields()

        features = []
        for fila in filas:
            try:
                x = float(str(fila[x_field_idx]).replace(",", "."))
                y = float(str(fila[y_field_idx]).replace(",", "."))
            except (ValueError, IndexError):
                continue

            feat = QgsFeature(capa.fields())
            if usar_z:
                # La capa se declaró como PointZ: todas sus geometrías
                # deben serlo, así que si no hay Z válida para esta fila
                # se usa 0.0 en vez de mezclar geometrías 2D y 3D en la
                # misma capa (lo que algunos proveedores rechazan).
                z = 0.0
                try:
                    z_text = str(fila[z_field_idx]).strip()
                    if z_text != "":
                        z = float(z_text.replace(",", "."))
                except (ValueError, IndexError):
                    z = 0.0
                feat.setGeometry(QgsGeometry(QgsPoint(x, y, z)))
            else:
                feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            valores = [str(v) for v in fila]
            if len(valores) < len(header):
                valores += [""] * (len(header) - len(valores))
            feat.setAttributes(valores[: len(header)])
            features.append(feat)

        proveedor.addFeatures(features)
        capa.updateExtents()
        if id_field_name and id_field_name in header:
            capa.setDisplayExpression('"{}"'.format(id_field_name))
        if agregar_al_proyecto:
            QgsProject.instance().addMapLayer(capa)
        return capa

    def _crear_capa_dxf(self, crs, resultados, idx_id):
        """Crea una capa liviana de puntos ajustados pensada para la
        exportación a DXF: solo geometría (con Z si está disponible) y
        un campo "Text" con la etiqueta de cada punto (columna ID si
        se seleccionó, o un consecutivo P1, P2, ...). El driver DXF de
        OGR/GDAL dibuja automáticamente esa etiqueta junto al punto.
        """
        capa = QgsVectorLayer("PointZ?crs={}".format(crs.authid() or crs.toWkt()), "dxf_tmp", "memory")
        proveedor = capa.dataProvider()
        tipo_texto = _tipo_campo_texto()
        proveedor.addAttributes([QgsField("Text", tipo_texto)])
        capa.updateFields()

        features = []
        for r in resultados:
            valor_id = r["original"][idx_id] if (idx_id is not None and idx_id < len(r["original"])) else None
            etiqueta = core.etiqueta_punto(valor_id, r["fila"])
            z = r["z_adj"] if r["z_adj"] is not None else 0.0
            feat = QgsFeature(capa.fields())
            feat.setGeometry(QgsGeometry(QgsPoint(r["x_adj"], r["y_adj"], z)))
            feat.setAttributes([etiqueta])
            features.append(feat)

        proveedor.addFeatures(features)
        capa.updateExtents()
        return capa

    def _exportar_vector_archivo(self, capa, ruta, nombre_driver):
        """Exporta ``capa`` (QgsVectorLayer) a un archivo vectorial
        usando el driver OGR indicado ("ESRI Shapefile", "DXF", ...).

        Prueba las distintas firmas que ha tenido
        QgsVectorFileWriter a través de las versiones de QGIS (V3,
        V2 y la firma antigua), ya que el complemento debe funcionar
        tanto en QGIS 3.16+ como en QGIS 4.x. Devuelve (ok, mensaje).
        """
        contexto = QgsProject.instance().transformContext()

        try:
            opciones = QgsVectorFileWriter.SaveVectorOptions()
            opciones.driverName = nombre_driver
            opciones.fileEncoding = "UTF-8"
            resultado = QgsVectorFileWriter.writeAsVectorFormatV3(capa, ruta, contexto, opciones)
        except AttributeError:
            try:
                opciones = QgsVectorFileWriter.SaveVectorOptions()
                opciones.driverName = nombre_driver
                opciones.fileEncoding = "UTF-8"
                resultado = QgsVectorFileWriter.writeAsVectorFormatV2(capa, ruta, contexto, opciones)
            except AttributeError:
                try:
                    codigo = QgsVectorFileWriter.writeAsVectorFormat(
                        capa, ruta, "UTF-8", capa.crs(), nombre_driver
                    )
                    resultado = (codigo, "")
                except Exception as exc:
                    return False, str(exc)
        except Exception as exc:
            return False, str(exc)

        if isinstance(resultado, (tuple, list)):
            codigo = resultado[0]
            mensaje = resultado[1] if len(resultado) > 1 else ""
        else:
            codigo = resultado
            mensaje = ""

        ok = _codigo_resultado(codigo) == 0
        return ok, str(mensaje)

    def _generar_reporte_html(self, contenido_html, ruta):
        """Escribe ``contenido_html`` (ver core.construir_reporte_html) tal
        cual a un archivo .html en disco, para abrirlo con cualquier
        navegador. Mucho más simple que generar PDF (no depende de
        QTextDocument/QPrinter ni de sus diferencias entre PyQt5/PyQt6) y
        además se ve mejor: el navegador sí soporta todo el CSS que usa
        el reporte (mayúsculas por CSS, tablas responsivas, etc.), cosa
        que el motor de texto enriquecido de Qt no soportaba del todo.
        Devuelve (ok, mensaje)."""
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(contenido_html)
        except OSError as exc:
            return False, str(exc)
        return True, ""
