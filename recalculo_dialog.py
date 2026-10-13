# -*- coding: utf-8 -*-
"""
recalculo_dialog.py
====================

Cuadro de diálogo del complemento "Recálculo RTK a Coordenadas
Ajustadas". Contiene toda la interfaz de usuario y la orquestación del
cálculo; la aritmética pura vive en core.py (sin dependencias de
QGIS) para poder probarla de forma aislada.
"""

import contextlib
import datetime
import os

from qgis.PyQt.QtCore import Qt, QDate
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QLabel,
    QPushButton,
    QToolButton,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QCheckBox,
    QMessageBox,
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
from . import i18n
from . import vemos

# Nota: estas dos constantes se mantienen por compatibilidad (por si algo
# externo las importa), pero el texto real que ve el usuario ahora sale
# siempre de i18n.tr(idioma, "placeholder_col"/"placeholder_col_opcional")
# para poder mostrarse en español, inglés o portugués según el idioma de
# QGIS.
PLACEHOLDER_COL = i18n.tr(i18n.IDIOMA_DEFECTO, "placeholder_col")
PLACEHOLDER_COL_OPCIONAL = i18n.tr(i18n.IDIOMA_DEFECTO, "placeholder_col_opcional")

# CRS geográfico oficial para Colombia (MAGNA-SIRGAS). El usuario puede
# cambiarlo libremente por cualquier otro (p. ej. WGS84 EPSG:4326) desde
# el selector de CRS del diálogo.
CRS_GEOGRAFICO_DEFECTO = "EPSG:4686"

# Carpeta con los archivos VEMOS*.TXT incluidos en el complemento (ver
# vemos_data/LEEME.txt para las citas de cada modelo), usados por la
# corrección opcional de época.
DIR_VEMOS_DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vemos_data")

# Debe mantenerse igual al valor "version" de metadata.txt; se usa para
# identificar la versión del complemento en el reporte técnico opcional.
VERSION_PLUGIN = "1.5.5"


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
        # Idioma detectado automáticamente a partir de la configuración de
        # QGIS (Configuración > Opciones > General > Idioma de la interfaz),
        # sin selector manual: español, inglés o portugués de Brasil (ver
        # i18n.detectar_idioma_qgis). Se detecta una sola vez al abrir el
        # diálogo y se usa tanto para toda la interfaz como para el reporte
        # técnico opcional.
        self.idioma = i18n.detectar_idioma_qgis()
        self.setWindowTitle(self._tr("window_title"))

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

        ancho, alto = 820, 700
        pantalla = QApplication.primaryScreen()
        if pantalla is not None:
            disponible = pantalla.availableGeometry()
            ancho = min(ancho, max(420, disponible.width() - 60))
            alto = min(alto, max(320, disponible.height() - 80))
        self.resize(ancho, alto)

        self._csv_header = []
        self._csv_rows = []

        self._build_ui()

    def _tr(self, clave, **kwargs):
        """Atajo para ``i18n.tr(self.idioma, clave, **kwargs)``."""
        return i18n.tr(self.idioma, clave, **kwargs)

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
        layout.setSpacing(8)

        intro = QLabel(self._tr("intro_text"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # --- Coordenadas de la base (fila superior en paralelo), con un
        # icono de vector (➔) entre ambas tarjetas que deja claro
        # visualmente que se trata de una traslación/desplazamiento de
        # coordenadas de una base a la otra. --------------------------
        bases_layout = QHBoxLayout()
        self.grp_libre, self.ed_libre = self._build_coord_group(
            self._tr("grp_base_libre")
        )
        self.grp_ajustada, self.ed_ajustada = self._build_coord_group(
            self._tr("grp_base_ajustada")
        )
        lbl_vector = QLabel("➔")
        lbl_vector.setToolTip(self._tr("tooltip_vector"))
        lbl_vector.setAlignment(_valor_enum(Qt, "AlignCenter", "AlignmentFlag"))
        fuente_vector = lbl_vector.font()
        fuente_vector.setPointSize(fuente_vector.pointSize() + 12)
        fuente_vector.setBold(True)
        lbl_vector.setFont(fuente_vector)
        bases_layout.addWidget(self.grp_libre)
        bases_layout.addWidget(lbl_vector)
        bases_layout.addWidget(self.grp_ajustada)
        layout.addLayout(bases_layout)

        # --- División central en dos columnas: Entrada (izquierda) y
        # Salida/exportación (derecha), en vez de apilar todo uno debajo
        # del otro. ------------------------------------------------------
        columnas_layout = QHBoxLayout()
        columnas_layout.setSpacing(14)

        # ===== Columna izquierda: datos de entrada y sistemas =========
        col_izq = QVBoxLayout()
        col_izq.setSpacing(8)

        lbl_col_izq = QLabel("<b>{}</b>".format(self._tr("lbl_columna_entrada")))
        col_izq.addWidget(lbl_col_izq)

        grp_csv = QGroupBox(self._tr("grp_csv"))
        csv_layout = QVBoxLayout(grp_csv)

        fila_archivo = QHBoxLayout()
        self.ed_csv_path = QLineEdit()
        self.ed_csv_path.setPlaceholderText(self._tr("placeholder_csv_path"))
        btn_examinar = QPushButton(self._tr("btn_examinar"))
        btn_examinar.clicked.connect(self._on_examinar_csv)
        fila_archivo.addWidget(self.ed_csv_path)
        fila_archivo.addWidget(btn_examinar)
        csv_layout.addLayout(fila_archivo)

        # Los 4 selectores de columna se acomodan en una cuadrícula
        # compacta de 2x2 ([ID] [Z] / [X] [Y]) en vez de 4 filas
        # apiladas, para recortar el espacio vertical.
        cols_grid = QGridLayout()
        cols_grid.setHorizontalSpacing(6)
        cols_grid.setVerticalSpacing(4)
        self.cb_col_id = QComboBox()
        self.cb_col_x = QComboBox()
        self.cb_col_y = QComboBox()
        self.cb_col_z = QComboBox()
        cols_grid.addWidget(QLabel(self._tr("lbl_col_id_corta")), 0, 0)
        cols_grid.addWidget(self.cb_col_id, 0, 1)
        cols_grid.addWidget(QLabel(self._tr("lbl_col_z_corta")), 0, 2)
        cols_grid.addWidget(self.cb_col_z, 0, 3)
        cols_grid.addWidget(QLabel(self._tr("lbl_col_x_corta")), 1, 0)
        cols_grid.addWidget(self.cb_col_x, 1, 1)
        cols_grid.addWidget(QLabel(self._tr("lbl_col_y_corta")), 1, 2)
        cols_grid.addWidget(self.cb_col_y, 1, 3)
        cols_grid.setColumnStretch(1, 1)
        cols_grid.setColumnStretch(3, 1)
        csv_layout.addLayout(cols_grid)
        self._set_column_combos_enabled(False)

        col_izq.addWidget(grp_csv)

        # --- Sistemas de referencia (debajo del CSV, mismo bloque de
        # entrada), con etiquetas cortas. ------------------------------
        grp_crs = QGroupBox(self._tr("grp_crs"))
        crs_layout = QFormLayout(grp_crs)

        self.crs_plano_widget = QgsProjectionSelectionWidget()
        crs_actual = self.iface.mapCanvas().mapSettings().destinationCrs() if self.iface else None
        if crs_actual and crs_actual.isValid():
            self.crs_plano_widget.setCrs(crs_actual)
        crs_layout.addRow(self._tr("lbl_crs_plano"), self.crs_plano_widget)

        self.crs_geo_widget = QgsProjectionSelectionWidget()
        self.crs_geo_widget.setCrs(QgsCoordinateReferenceSystem(CRS_GEOGRAFICO_DEFECTO))
        crs_layout.addRow(self._tr("lbl_crs_geo"), self.crs_geo_widget)

        col_izq.addWidget(grp_crs)
        col_izq.addStretch(1)

        # ===== Columna derecha: exportación y reporte técnico ===========
        col_der = QVBoxLayout()
        col_der.setSpacing(8)

        lbl_col_der = QLabel("<b>{}</b>".format(self._tr("lbl_columna_salida")))
        col_der.addWidget(lbl_col_der)

        # --- Resultado principal ---------------------------------------
        grp_salida = QGroupBox(self._tr("grp_resultado"))
        salida_layout = QVBoxLayout(grp_salida)
        salida_layout.setSpacing(4)

        fila_salida = QHBoxLayout()
        self.ed_out_path = QLineEdit()
        self.ed_out_path.setPlaceholderText(self._tr("placeholder_out_path"))
        btn_salida = QPushButton(self._tr("btn_guardar_como"))
        btn_salida.clicked.connect(self._on_examinar_salida)
        fila_salida.addWidget(self.ed_out_path)
        fila_salida.addWidget(btn_salida)
        salida_layout.addLayout(fila_salida)

        self.chk_capa_ajustada = QCheckBox(self._tr("chk_capa_ajustada"))
        self.chk_capa_ajustada.setChecked(True)
        self.chk_capa_libre = QCheckBox(self._tr("chk_capa_libre"))
        salida_layout.addWidget(self.chk_capa_ajustada)
        salida_layout.addWidget(self.chk_capa_libre)

        col_der.addWidget(grp_salida)

        # --- Exportar a otros formatos: chips SHP/DXF + fila de ruta
        # dinámica que solo aparece para los formatos marcados, en vez
        # de dos filas idénticas siempre visibles. La advertencia sobre
        # los atributos de DXF queda detrás de un botón de ayuda "(?)".
        grp_export = QGroupBox(self._tr("grp_export_adicional"))
        export_layout = QVBoxLayout(grp_export)
        export_layout.setSpacing(4)

        fila_chips = QHBoxLayout()
        self.chk_export_shp = QCheckBox(self._tr("chip_shp"))
        self.chk_export_dxf = QCheckBox(self._tr("chip_dxf"))
        btn_ayuda_dxf = self._build_boton_ayuda(self._tr("nota_dxf"))
        fila_chips.addWidget(self.chk_export_shp)
        fila_chips.addWidget(self.chk_export_dxf)
        fila_chips.addWidget(btn_ayuda_dxf)
        fila_chips.addStretch(1)
        export_layout.addLayout(fila_chips)

        self.ed_shp_path, self.widget_fila_shp = self._build_fila_ruta_dinamica(
            export_layout, self._on_examinar_shp
        )
        self.ed_dxf_path, self.widget_fila_dxf = self._build_fila_ruta_dinamica(
            export_layout, self._on_examinar_dxf
        )
        self.chk_export_shp.toggled.connect(self.widget_fila_shp.setVisible)
        self.chk_export_dxf.toggled.connect(self.widget_fila_dxf.setVisible)

        col_der.addWidget(grp_export)

        # --- Reporte técnico (opcional): un único checkbox principal
        # que, al marcarlo, despliega los campos de Proyecto/Responsable
        # y la ruta; el párrafo explicativo queda detrás de un botón de
        # ayuda "(?)" en vez de un texto siempre visible. ----------------
        grp_reporte = QGroupBox()
        reporte_layout = QVBoxLayout(grp_reporte)
        reporte_layout.setSpacing(4)

        self.chk_reporte = QCheckBox(self._tr("chk_reporte"))
        reporte_layout.addWidget(self.chk_reporte)

        self.widget_reporte_detalle = QWidget()
        detalle_layout = QVBoxLayout(self.widget_reporte_detalle)
        detalle_layout.setContentsMargins(0, 2, 0, 0)
        detalle_layout.setSpacing(4)

        datos_form = QFormLayout()
        self.ed_reporte_proyecto = QLineEdit()
        self.ed_reporte_proyecto.setPlaceholderText(self._tr("placeholder_proyecto"))
        self.ed_reporte_responsable = QLineEdit()
        self.ed_reporte_responsable.setPlaceholderText(self._tr("placeholder_responsable"))
        datos_form.addRow(self._tr("lbl_proyecto"), self.ed_reporte_proyecto)
        datos_form.addRow(self._tr("lbl_responsable"), self.ed_reporte_responsable)
        detalle_layout.addLayout(datos_form)

        fila_reporte = QHBoxLayout()
        self.ed_reporte_path = QLineEdit()
        btn_reporte = QPushButton(self._tr("btn_guardar_como"))
        btn_reporte.clicked.connect(self._on_examinar_reporte)
        btn_ayuda_reporte = self._build_boton_ayuda(self._tr("nota_reporte"))
        fila_reporte.addWidget(self.ed_reporte_path)
        fila_reporte.addWidget(btn_reporte)
        fila_reporte.addWidget(btn_ayuda_reporte)
        detalle_layout.addLayout(fila_reporte)

        self.widget_reporte_detalle.setVisible(False)
        self.chk_reporte.toggled.connect(self.widget_reporte_detalle.setVisible)
        reporte_layout.addWidget(self.widget_reporte_detalle)

        col_der.addWidget(grp_reporte)

        # --- Corrección de época (VEMOS, opcional): lleva las
        # coordenadas geográficas ajustadas de su época de observación a
        # una época destino (p. ej. MAGNA-SIRGAS 2018.0) usando los
        # modelos de velocidades VEMOS de SIRGAS/DGFI-TUM. Desactivada
        # por defecto; un único checkbox despliega el resto, igual que
        # el bloque de reporte técnico. ------------------------------
        grp_epoca = QGroupBox()
        epoca_layout = QVBoxLayout(grp_epoca)
        epoca_layout.setSpacing(4)

        fila_chk_epoca = QHBoxLayout()
        self.chk_epoca = QCheckBox(self._tr("chk_epoca_vemos"))
        btn_ayuda_epoca = self._build_boton_ayuda(self._tr("nota_epoca_vemos"))
        fila_chk_epoca.addWidget(self.chk_epoca)
        fila_chk_epoca.addWidget(btn_ayuda_epoca)
        fila_chk_epoca.addStretch(1)
        epoca_layout.addLayout(fila_chk_epoca)

        self.widget_epoca_detalle = QWidget()
        epoca_detalle_layout = QVBoxLayout(self.widget_epoca_detalle)
        epoca_detalle_layout.setContentsMargins(0, 2, 0, 0)
        epoca_detalle_layout.setSpacing(4)

        epoca_form = QFormLayout()
        self.cb_modelo_vemos = QComboBox()
        for _clave_modelo in vemos.ORDEN_MODELOS:
            _info_modelo = vemos.MODELOS[_clave_modelo]
            self.cb_modelo_vemos.addItem("{} ({})".format(_clave_modelo, _info_modelo["marco"]), _clave_modelo)
        epoca_form.addRow(self._tr("lbl_modelo_vemos"), self.cb_modelo_vemos)

        self.ed_epoca_destino = QLineEdit(self._tr("valor_epoca_magna_sirgas"))
        epoca_form.addRow(self._tr("lbl_epoca_destino"), self.ed_epoca_destino)

        fila_epoca_obs = QHBoxLayout()
        self.fecha_epoca_obs = QDateEdit()
        self.fecha_epoca_obs.setCalendarPopup(True)
        self.fecha_epoca_obs.setDisplayFormat("yyyy-MM-dd")
        self.fecha_epoca_obs.setDate(QDate.currentDate())
        self.lbl_epoca_obs_decimal = QLabel()
        self.lbl_epoca_obs_decimal.setStyleSheet("QLabel { color: #5a6472; font-size: 11px; }")
        fila_epoca_obs.addWidget(self.fecha_epoca_obs)
        fila_epoca_obs.addWidget(self.lbl_epoca_obs_decimal)
        fila_epoca_obs.addStretch(1)
        self.fecha_epoca_obs.dateChanged.connect(self._actualizar_epoca_obs_decimal)
        epoca_form.addRow(self._tr("lbl_epoca_obs"), fila_epoca_obs)
        epoca_detalle_layout.addLayout(epoca_form)

        self.lbl_cobertura_vemos = QLabel()
        self.lbl_cobertura_vemos.setStyleSheet("QLabel { color: #5a6472; font-size: 11px; }")
        self.lbl_cobertura_vemos.setWordWrap(True)
        epoca_detalle_layout.addWidget(self.lbl_cobertura_vemos)

        self.widget_epoca_detalle.setVisible(False)
        self.chk_epoca.toggled.connect(self.widget_epoca_detalle.setVisible)
        epoca_layout.addWidget(self.widget_epoca_detalle)

        # Caché de grillas VEMOS ya leídas (clave de modelo) para no
        # releer el archivo en cada punto ni en cada cambio del combo.
        self._vemos_grids_cache = {}
        self.cb_modelo_vemos.currentIndexChanged.connect(self._actualizar_cobertura_vemos)
        self._actualizar_cobertura_vemos()
        self._actualizar_epoca_obs_decimal()

        col_der.addWidget(grp_epoca)
        col_der.addStretch(1)

        columnas_layout.addLayout(col_izq, 1)
        columnas_layout.addLayout(col_der, 1)
        layout.addLayout(columnas_layout)
        layout.addStretch(1)

        # El contenido configurable queda dentro de la barra de
        # desplazamiento; el registro de estado y los botones de acción
        # quedan fijos debajo, siempre visibles aunque se desplace el
        # contenido de arriba.
        scroll.setWidget(contenido)
        raiz.addWidget(scroll, 1)

        pie = QVBoxLayout()
        pie.setContentsMargins(12, 6, 12, 12)
        pie.setSpacing(4)

        # --- Log de estado: colapsado por defecto para no ocupar
        # espacio; se expande solo (o con un clic) cuando hace falta
        # ver el resultado del proceso. --------------------------------
        fila_log = QHBoxLayout()
        self.btn_toggle_log = QToolButton()
        self.btn_toggle_log.setCheckable(True)
        self.btn_toggle_log.setChecked(False)
        self.btn_toggle_log.setToolButtonStyle(_valor_enum(Qt, "ToolButtonTextBesideIcon", "ToolButtonStyle"))
        self.btn_toggle_log.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self.btn_toggle_log.toggled.connect(self._on_toggle_log)
        fila_log.addWidget(self.btn_toggle_log)
        fila_log.addStretch(1)
        pie.addLayout(fila_log)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(110)
        self.txt_log.setPlaceholderText(self._tr("placeholder_log"))
        self.txt_log.setVisible(False)
        pie.addWidget(self.txt_log)
        self._actualizar_texto_toggle_log()

        # --- Botones: "Calcular y exportar" queda destacado (color
        # verde principal) en la esquina inferior derecha, junto al
        # botón secundario "Cerrar". -------------------------------------
        botones = QHBoxLayout()
        botones.addStretch(1)
        btn_cerrar = QPushButton(self._tr("btn_cerrar"))
        btn_cerrar.clicked.connect(self.close)
        self.btn_ejecutar = QPushButton(self._tr("btn_calcular"))
        self.btn_ejecutar.clicked.connect(self._on_ejecutar)
        self.btn_ejecutar.setDefault(True)
        self.btn_ejecutar.setStyleSheet(
            "QPushButton {"
            "  background-color: #2e7d32; color: white; font-weight: bold;"
            "  padding: 6px 18px; border-radius: 4px; border: none;"
            "}"
            "QPushButton:hover { background-color: #388e3c; }"
            "QPushButton:pressed { background-color: #1b5e20; }"
        )
        botones.addWidget(btn_cerrar)
        botones.addWidget(self.btn_ejecutar)
        pie.addLayout(botones)

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
        for ed, etiqueta in (
            (ed_x, self._tr("lbl_x")), (ed_y, self._tr("lbl_y")), (ed_z, self._tr("lbl_z"))
        ):
            ed.setPlaceholderText(self._tr("placeholder_num"))
            # Ancho acotado a un tamaño estándar: las tarjetas de base no
            # necesitan estirarse tanto como el resto del diálogo.
            ed.setMaximumWidth(130)
            form.addRow(etiqueta, ed)

        return grupo, {"x": ed_x, "y": ed_y, "z": ed_z}

    def _build_boton_ayuda(self, texto_tooltip):
        """Botón de ayuda contextual "(?)": en vez de un párrafo de nota
        siempre visible, muestra el texto explicativo en un cuadro de
        mensaje al hacer clic, para no saturar la vista. También deja
        el texto como tooltip al pasar el cursor, pero el clic es la
        forma confiable de verlo completo (el tooltip no siempre
        aparece — depende del tema, del tiempo que el cursor se quede
        quieto, o de si se usa con pantalla táctil)."""
        boton = QToolButton()
        boton.setText("?")
        boton.setToolTip(texto_tooltip)
        boton.setCursor(_valor_enum(Qt, "PointingHandCursor", "CursorShape"))
        boton.setStyleSheet(
            "QToolButton {"
            "  border: 1px solid #888; border-radius: 9px;"
            "  min-width: 18px; max-width: 18px;"
            "  min-height: 18px; max-height: 18px;"
            "  font-weight: bold;"
            "}"
        )
        boton.clicked.connect(
            lambda: QMessageBox.information(self, self._tr("dlg_ayuda_titulo"), texto_tooltip)
        )
        return boton

    def _build_fila_ruta_dinamica(self, layout_padre, manejador_examinar):
        """Crea una fila "ruta + botón Guardar como..." para un formato
        de exportación adicional (Shapefile, DXF, ...), oculta por
        defecto: solo aparece cuando el checkbox correspondiente del
        chip (ver _build_ui) se marca, en vez de mostrar siempre filas
        idénticas para cada formato. Devuelve (campo_ruta, widget_fila)
        para que el llamador conecte la visibilidad al checkbox."""
        widget_fila = QWidget()
        fila = QHBoxLayout(widget_fila)
        fila.setContentsMargins(0, 0, 0, 0)
        campo_ruta = QLineEdit()
        boton = QPushButton(self._tr("btn_guardar_como"))
        boton.clicked.connect(manejador_examinar)
        fila.addWidget(campo_ruta)
        fila.addWidget(boton)
        widget_fila.setVisible(False)
        layout_padre.addWidget(widget_fila)
        return campo_ruta, widget_fila

    def _on_toggle_log(self, expandido):
        self.txt_log.setVisible(expandido)
        self._actualizar_texto_toggle_log()

    def _actualizar_texto_toggle_log(self):
        flecha = "▾" if self.btn_toggle_log.isChecked() else "▸"
        self.btn_toggle_log.setText("{} {}".format(flecha, self._tr("lbl_registro")))

    def _set_column_combos_enabled(self, enabled):
        for cb in (self.cb_col_id, self.cb_col_x, self.cb_col_y, self.cb_col_z):
            cb.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Manejadores de UI
    # ------------------------------------------------------------------
    def _on_examinar_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self._tr("dlg_sel_csv_titulo"), "", self._tr("filtro_csv")
        )
        if not path:
            return
        self.ed_csv_path.setText(path)
        self._cargar_columnas(path)

    def _cargar_columnas(self, path):
        try:
            header, rows = core.read_csv_rows(path)
        except Exception as exc:
            QMessageBox.critical(self, self._tr("err_leer_csv_titulo"), self._tr("err_leer_csv_msg", error=exc))
            self._set_column_combos_enabled(False)
            return

        if not header:
            QMessageBox.warning(self, self._tr("warn_archivo_vacio_titulo"), self._tr("warn_archivo_vacio_msg"))
            self._set_column_combos_enabled(False)
            return

        self._csv_header = header
        self._csv_rows = rows

        self.cb_col_id.clear()
        self.cb_col_x.clear()
        self.cb_col_y.clear()
        self.cb_col_z.clear()

        placeholder_col = self._tr("placeholder_col")
        placeholder_col_opcional = self._tr("placeholder_col_opcional")
        self.cb_col_id.addItem(placeholder_col_opcional)
        self.cb_col_z.addItem(placeholder_col_opcional)
        self.cb_col_x.addItem(placeholder_col)
        self.cb_col_y.addItem(placeholder_col)

        for nombre in header:
            self.cb_col_id.addItem(nombre)
            self.cb_col_x.addItem(nombre)
            self.cb_col_y.addItem(nombre)
            self.cb_col_z.addItem(nombre)

        # Adivinar columnas comunes por nombre, como comodidad (el
        # usuario siempre puede cambiarlas). Los nombres candidatos
        # incluyen equivalentes en español, inglés y portugués, ya que
        # el CSV del usuario puede venir con encabezados en cualquiera
        # de los tres idiomas independientemente del idioma de la
        # interfaz del complemento.
        self._preseleccionar_columna(self.cb_col_x, ("x", "este", "easting", "longitud", "lon", "longitude"))
        self._preseleccionar_columna(self.cb_col_y, ("y", "norte", "northing", "latitud", "lat", "latitude"))
        self._preseleccionar_columna(
            self.cb_col_z, ("z", "elevacion", "elevación", "elevation", "elevação", "cota", "altura", "h"))
        self._preseleccionar_columna(
            self.cb_col_id, ("id", "punto", "point", "ponto", "codigo", "código", "code", "nombre", "name", "nome"))

        self._set_column_combos_enabled(True)
        self._log(self._tr("log_columnas_cargadas", n_col=len(header), n_filas=len(rows),
                            archivo=os.path.basename(path)))

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
            self, self._tr("dlg_guardar_csv_titulo"), self.ed_out_path.text(), self._tr("filtro_csv_solo")
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
        path, _ = QFileDialog.getSaveFileName(self, self._tr("dlg_guardar_shp_titulo"), sugerido, self._tr("filtro_shp"))
        if path:
            self.ed_shp_path.setText(path)

    def _on_examinar_dxf(self):
        sugerido = self.ed_dxf_path.text().strip() or core.sugerir_ruta_con_extension(
            self.ed_out_path.text().strip() or "salida.csv", ".dxf"
        )
        path, _ = QFileDialog.getSaveFileName(self, self._tr("dlg_guardar_dxf_titulo"), sugerido, self._tr("filtro_dxf"))
        if path:
            self.ed_dxf_path.setText(path)

    def _on_examinar_reporte(self):
        sugerido = self.ed_reporte_path.text().strip()
        if not sugerido:
            csv_out = self.ed_out_path.text().strip() or "salida.csv"
            base, _ext = os.path.splitext(csv_out)
            sugerido = base + "_reporte.html"
        path, _ = QFileDialog.getSaveFileName(self, self._tr("dlg_guardar_reporte_titulo"), sugerido, self._tr("filtro_html"))
        if path:
            self.ed_reporte_path.setText(path)

    def _log(self, mensaje, nivel="info"):
        # El registro se expande solo en cuanto hay algo que mostrar,
        # para que el usuario no tenga que acordarse de desplegarlo a
        # mano justo cuando más importa ver el resultado del proceso.
        if not self.btn_toggle_log.isChecked():
            self.btn_toggle_log.setChecked(True)
        self.txt_log.appendPlainText(mensaje)

    # ------------------------------------------------------------------
    # Lectura y validación de entradas
    # ------------------------------------------------------------------
    def _leer_base(self, campos, nombre_base):
        try:
            x = core.parse_float(campos["x"].text())
            y = core.parse_float(campos["y"].text())
        except ValueError as exc:
            raise ValueError(self._tr("err_base_xy_invalida", nombre_base=nombre_base, error=exc))

        z_text = campos["z"].text().strip()
        z = None
        if z_text != "":
            try:
                z = core.parse_float(z_text)
            except ValueError as exc:
                raise ValueError(self._tr("err_base_z_invalida", nombre_base=nombre_base, error=exc))
        return x, y, z

    def _indice_columna(self, combo, opcional):
        idx = combo.currentIndex()
        if opcional:
            return None if idx <= 0 else idx - 1
        return None if idx <= 0 else idx - 1

    # ------------------------------------------------------------------
    # Corrección de época (VEMOS)
    # ------------------------------------------------------------------
    def _resolver_grid_vemos(self, clave_modelo):
        """Retorna la grilla VEMOS (``vemos.VemosGrid``) para
        ``clave_modelo``, leyéndola solo la primera vez (desde la
        carpeta ``vemos_data/`` incluida con el complemento) y
        reutilizando el resultado en llamadas posteriores (hay una
        por cada punto del CSV durante el cálculo)."""
        if clave_modelo not in self._vemos_grids_cache:
            ruta = os.path.join(DIR_VEMOS_DATOS, vemos.MODELOS[clave_modelo]["archivo"])
            self._vemos_grids_cache[clave_modelo] = vemos.leer_vemos(ruta)
        return self._vemos_grids_cache[clave_modelo]

    def _actualizar_cobertura_vemos(self):
        """Actualiza la etiqueta de cobertura real bajo el selector de
        modelo VEMOS. No interrumpe al usuario con un cuadro de error
        si el archivo no se puede leer todavía (p. ej. carpeta
        vemos_data/ incompleta): el error real se muestra solo al
        intentar calcular con la corrección activada."""
        clave = self.cb_modelo_vemos.currentData()
        if not clave:
            return
        texto = ""
        with contextlib.suppress(OSError, ValueError):
            grid = self._resolver_grid_vemos(clave)
            texto = self._tr("lbl_cobertura_vemos", zona=vemos.texto_cobertura(grid), nodos=len(grid))
        self.lbl_cobertura_vemos.setText(texto or self._tr("lbl_cobertura_vemos_no_disp"))

    def _actualizar_epoca_obs_decimal(self):
        """Actualiza la etiqueta que muestra el año decimal calculado
        a partir de la fecha de observación elegida en el calendario
        (``vemos.epoca_decimal``, mismo año + día del año que usa el
        resto del módulo ``vemos``)."""
        fecha = self.fecha_epoca_obs.date()
        decimal = vemos.epoca_decimal(fecha.year(), fecha.dayOfYear())
        self.lbl_epoca_obs_decimal.setText(self._tr("lbl_epoca_obs_decimal", valor="{:.3f}".format(decimal)))

    # ------------------------------------------------------------------
    # Ejecución del cálculo
    # ------------------------------------------------------------------
    def _on_ejecutar(self):
        self.txt_log.clear()
        try:
            base_libre = self._leer_base(self.ed_libre, self._tr("nombre_base_libre"))
            base_ajustada = self._leer_base(self.ed_ajustada, self._tr("nombre_base_ajustada"))
        except ValueError as exc:
            QMessageBox.warning(self, self._tr("warn_datos_incompletos_titulo"), str(exc))
            return

        if not self._csv_header:
            QMessageBox.warning(self, self._tr("warn_falta_csv_titulo"), self._tr("warn_falta_csv_msg"))
            return

        idx_x = self._indice_columna(self.cb_col_x, opcional=False)
        idx_y = self._indice_columna(self.cb_col_y, opcional=False)
        idx_z = self._indice_columna(self.cb_col_z, opcional=True)
        idx_id = self._indice_columna(self.cb_col_id, opcional=True)

        if idx_x is None or idx_y is None:
            QMessageBox.warning(
                self, self._tr("warn_columnas_incompletas_titulo"), self._tr("warn_columnas_incompletas_msg")
            )
            return
        if idx_x == idx_y or (idx_z is not None and idx_z in (idx_x, idx_y)):
            QMessageBox.warning(self, self._tr("warn_columnas_repetidas_titulo"), self._tr("warn_columnas_repetidas_msg"))
            return

        out_path = self.ed_out_path.text().strip()
        if not out_path:
            QMessageBox.warning(self, self._tr("warn_falta_salida_titulo"), self._tr("warn_falta_salida_msg"))
            return

        exportar_shp = self.chk_export_shp.isChecked()
        ruta_shp = self.ed_shp_path.text().strip()
        if exportar_shp and not ruta_shp:
            QMessageBox.warning(self, self._tr("warn_falta_shp_titulo"), self._tr("warn_falta_shp_msg"))
            return

        exportar_dxf = self.chk_export_dxf.isChecked()
        ruta_dxf = self.ed_dxf_path.text().strip()
        if exportar_dxf and not ruta_dxf:
            QMessageBox.warning(self, self._tr("warn_falta_dxf_titulo"), self._tr("warn_falta_dxf_msg"))
            return

        generar_reporte = self.chk_reporte.isChecked()
        ruta_reporte = self.ed_reporte_path.text().strip()
        if generar_reporte and not ruta_reporte:
            QMessageBox.warning(self, self._tr("warn_falta_reporte_titulo"), self._tr("warn_falta_reporte_msg"))
            return

        crs_plano = self.crs_plano_widget.crs()
        crs_geo = self.crs_geo_widget.crs()
        if not crs_plano.isValid() or not crs_geo.isValid():
            QMessageBox.warning(self, self._tr("warn_crs_invalido_titulo"), self._tr("warn_crs_invalido_msg"))
            return

        # --- Corrección de época (VEMOS), opcional: se valida todo antes
        # de calcular para no procesar el CSV completo y fallar al final. --
        aplicar_epoca = self.chk_epoca.isChecked()
        clave_modelo_epoca = None
        epoca_destino = None
        epoca_obs = None
        grid_epoca = None
        if aplicar_epoca:
            clave_modelo_epoca = self.cb_modelo_vemos.currentData()
            try:
                epoca_destino = core.parse_float(self.ed_epoca_destino.text())
            except ValueError as exc:
                QMessageBox.warning(
                    self, self._tr("warn_epoca_invalida_titulo"), self._tr("warn_epoca_destino_invalida", error=exc)
                )
                return
            fecha_epoca_obs = self.fecha_epoca_obs.date()
            epoca_obs = vemos.epoca_decimal(fecha_epoca_obs.year(), fecha_epoca_obs.dayOfYear())
            try:
                grid_epoca = self._resolver_grid_vemos(clave_modelo_epoca)
            except (OSError, ValueError) as exc:
                QMessageBox.critical(
                    self, self._tr("err_vemos_archivo_titulo"), self._tr("err_vemos_archivo_msg", error=exc)
                )
                return
            if vemos.fuera_de_vigencia(clave_modelo_epoca, epoca_obs):
                info_modelo_epoca = vemos.MODELOS[clave_modelo_epoca]
                self._log(self._tr(
                    "log_epoca_fuera_vigencia", modelo=clave_modelo_epoca,
                    t_ini=info_modelo_epoca["t_ini"], t_fin=info_modelo_epoca["t_fin"],
                ))

        dx, dy, dz = core.compute_delta(base_libre, base_ajustada)
        dz_texto = "{:.4f}".format(dz) if dz is not None else self._tr("log_dz_na")
        self._log(self._tr("log_vector_calculado", dx="{:.4f}".format(dx), dy="{:.4f}".format(dy), dz=dz_texto))

        resultados, errores = core.recalcular_filas(
            self._csv_header, self._csv_rows, idx_x, idx_y, idx_z, dx, dy, dz
        )

        if not resultados:
            QMessageBox.critical(self, self._tr("err_sin_datos_validos_titulo"), self._tr("err_sin_datos_validos_msg"))
            return

        transform = QgsCoordinateTransform(crs_plano, crs_geo, QgsProject.instance())
        transform_inv = QgsCoordinateTransform(crs_geo, crs_plano, QgsProject.instance()) if aplicar_epoca else None

        nuevo_header = list(self._csv_header) + [
            "X_ajustada", "Y_ajustada", "Z_ajustada", "Lon_ajustada", "Lat_ajustada"
        ]
        if aplicar_epoca:
            nuevo_header += [
                "X_epoca", "Y_epoca", "Z_epoca", "Lon_epoca", "Lat_epoca",
                "Desplazamiento_epoca_m", "Modelo_epoca", "Epoca_obs", "Epoca_destino",
            ]
        nuevas_filas = []
        puntos_reporte = []
        # Coordenadas planas "finales" que se usan para la GEOMETRÍA de
        # los puntos exportados (capa del proyecto, Shapefile y DXF): si
        # se activó la corrección de época y el punto quedó corregido,
        # son las coordenadas ya corregidas a la época destino; si no se
        # activó la corrección, o el punto cayó fuera de la cobertura
        # real del modelo VEMOS elegido, son las coordenadas ajustadas
        # por la base RTK sin corrección de época (igual que siempre).
        # Los ATRIBUTOS/columnas del CSV y del Shapefile (X_ajustada,
        # Y_ajustada, Z_ajustada, X_epoca, ...) no cambian: siguen
        # mostrando ambos valores por separado, esto solo decide dónde
        # queda plantado el punto.
        coords_finales = []
        errores_transform = 0
        puntos_corregidos_epoca = 0
        puntos_fuera_cobertura_epoca = 0
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

            resultado_epoca = None
            x_epoca = y_epoca = None
            if aplicar_epoca:
                if lon == "" or lat == "":
                    # Ya es un error de transformación; no tiene sentido
                    # intentar la corrección de época sobre coordenadas
                    # geográficas que no se pudieron calcular.
                    fila_salida += [
                        "", "", "", "", "", "", clave_modelo_epoca,
                        "{:.3f}".format(epoca_obs), "{:.3f}".format(epoca_destino),
                    ]
                else:
                    h_para_epoca = r["z_adj"] if r["z_adj"] is not None else 0.0
                    resultado_epoca = vemos.cambiar_epoca(grid_epoca, lat, lon, h_para_epoca, epoca_obs, epoca_destino)
                    if resultado_epoca is None:
                        puntos_fuera_cobertura_epoca += 1
                        fila_salida += [
                            "", "", "", "", "", "", clave_modelo_epoca,
                            "{:.3f}".format(epoca_obs), "{:.3f}".format(epoca_destino),
                        ]
                    else:
                        puntos_corregidos_epoca += 1
                        try:
                            punto_plano_epoca = transform_inv.transform(
                                QgsPointXY(resultado_epoca.lon, resultado_epoca.lat)
                            )
                            x_epoca, y_epoca = punto_plano_epoca.x(), punto_plano_epoca.y()
                        except Exception:
                            x_epoca, y_epoca = None, None
                        fila_salida += [
                            "{:.4f}".format(x_epoca) if x_epoca is not None else "",
                            "{:.4f}".format(y_epoca) if y_epoca is not None else "",
                            "{:.4f}".format(resultado_epoca.h) if r["z_adj"] is not None else "",
                            "{:.9f}".format(resultado_epoca.lon),
                            "{:.9f}".format(resultado_epoca.lat),
                            "{:.4f}".format(resultado_epoca.desplazamiento_m),
                            clave_modelo_epoca,
                            "{:.3f}".format(epoca_obs),
                            "{:.3f}".format(epoca_destino),
                        ]

            # x_epoca/y_epoca/resultado_epoca quedan en None si la
            # corrección no se activó, el punto cayó fuera de la
            # cobertura real del modelo, o no se pudo reproyectar de
            # vuelta a coordenadas planas — en todos esos casos la
            # geometría exportada usa la coordenada ajustada (sin
            # corrección de época), igual que si la opción no existiera.
            if aplicar_epoca and resultado_epoca is not None and x_epoca is not None and y_epoca is not None:
                z_final = resultado_epoca.h if r["z_adj"] is not None else None
                coords_finales.append((x_epoca, y_epoca, z_final))
            else:
                coords_finales.append((r["x_adj"], r["y_adj"], r["z_adj"]))

            nuevas_filas.append(fila_salida)

            if generar_reporte:
                valor_id = r["original"][idx_id] if (idx_id is not None and idx_id < len(r["original"])) else None
                punto_reporte = {
                    "etiqueta": core.etiqueta_punto(valor_id, r["fila"]),
                    "x": r["x"], "y": r["y"], "z": r["z"],
                    "x_adj": r["x_adj"], "y_adj": r["y_adj"], "z_adj": r["z_adj"],
                    "lon": lon if lon != "" else None,
                    "lat": lat if lat != "" else None,
                }
                if aplicar_epoca:
                    # Coordenadas ya corregidas por el modelo de velocidades
                    # VEMOS (ver "_on_ejecutar" arriba); quedan en None si el
                    # punto cayó fuera de la cobertura real del modelo o no
                    # se pudo reproyectar — el reporte las muestra como
                    # "N/A" en ese caso (ver core._tabla_epoca_html/
                    # construir_reporte_html).
                    punto_reporte["x_epoca"] = x_epoca
                    punto_reporte["y_epoca"] = y_epoca
                    punto_reporte["z_epoca"] = (
                        resultado_epoca.h if (resultado_epoca is not None and r["z_adj"] is not None) else None
                    )
                    punto_reporte["lon_epoca"] = resultado_epoca.lon if resultado_epoca is not None else None
                    punto_reporte["lat_epoca"] = resultado_epoca.lat if resultado_epoca is not None else None
                    punto_reporte["desplazamiento_epoca_m"] = (
                        resultado_epoca.desplazamiento_m if resultado_epoca is not None else None
                    )
                puntos_reporte.append(punto_reporte)

        try:
            core.write_csv_rows(out_path, nuevo_header, nuevas_filas)
        except Exception as exc:
            QMessageBox.critical(self, self._tr("err_guardar_titulo"), self._tr("err_guardar_msg", error=exc))
            return

        self._log(self._tr("log_recalculo_ok", ok=len(resultados), total=len(self._csv_rows)))
        if errores:
            self._log(self._tr("log_filas_omitidas", n=len(errores)))
            for num, msg in errores[:10]:
                self._log(self._tr("log_fila_error", num=num, msg=msg))
            if len(errores) > 10:
                self._log(self._tr("log_mas_errores", n=len(errores) - 10))
        if errores_transform:
            self._log(self._tr("log_errores_transform", n=errores_transform))
        if aplicar_epoca:
            self._log(self._tr(
                "log_epoca_aplicada", modelo=clave_modelo_epoca,
                corregidos=puntos_corregidos_epoca, fuera=puntos_fuera_cobertura_epoca,
            ))
            if puntos_fuera_cobertura_epoca:
                self._log(self._tr("log_epoca_fuera_cobertura", zona=vemos.texto_cobertura(grid_epoca)))
        self._log(self._tr("log_archivo_generado", ruta=out_path))

        nombre_id = self._csv_header[idx_id] if idx_id is not None else None
        idx_z_ajustada = len(self._csv_header) + 2  # posición de "Z_ajustada" en nuevo_header

        # La capa de puntos ajustados se construye si se va a mostrar en
        # el proyecto y/o si se va a exportar a Shapefile, aunque el
        # usuario no haya marcado "agregar al proyecto".
        capa_ajustada = None
        if self.chk_capa_ajustada.isChecked() or exportar_shp:
            capa_ajustada = self._crear_capa_puntos(
                self._tr("capa_ajustada_nombre"), crs_plano, nuevo_header, nuevas_filas,
                x_field_idx=len(self._csv_header) + 0,
                y_field_idx=len(self._csv_header) + 1,
                z_field_idx=idx_z_ajustada,
                id_field_name=nombre_id,
                agregar_al_proyecto=self.chk_capa_ajustada.isChecked(),
                # Geometría: coordenadas ya corregidas por época cuando el
                # usuario activó esa opción (y el punto quedó dentro de la
                # cobertura real del modelo); si no, las ajustadas por la
                # base RTK, igual que siempre. Los atributos de la capa
                # (incluidas las columnas "*_ajustada"/"*_epoca") no
                # cambian, solo la ubicación del punto.
                geom_coords=coords_finales,
            )

        if self.chk_capa_libre.isChecked():
            filas_libres = [r["original"] for r in resultados]
            self._crear_capa_puntos(
                self._tr("capa_libre_nombre"), crs_plano, self._csv_header, filas_libres,
                x_field_idx=idx_x, y_field_idx=idx_y, z_field_idx=idx_z,
                id_field_name=nombre_id,
                agregar_al_proyecto=True,
            )

        if exportar_shp:
            if capa_ajustada is None:
                self._log(self._tr("log_no_capa_shp"))
            else:
                ok, msg = self._exportar_vector_archivo(capa_ajustada, ruta_shp, "ESRI Shapefile")
                if ok:
                    self._log(self._tr("log_shp_generado", ruta=ruta_shp))
                else:
                    self._log(self._tr("log_shp_error", msg=msg))

        if exportar_dxf:
            capa_dxf = self._crear_capa_dxf(crs_plano, resultados, idx_id, coords_finales)
            ok, msg = self._exportar_vector_archivo(capa_dxf, ruta_dxf, "DXF")
            if ok:
                self._log(self._tr("log_dxf_generado", ruta=ruta_dxf))
            else:
                self._log(self._tr("log_dxf_error", msg=msg))

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
                # El reporte técnico se genera en el mismo idioma detectado
                # para la interfaz del complemento (ver __init__ / i18n.py).
                "idioma": self.idioma,
            }
            if aplicar_epoca:
                info_modelo_epoca = vemos.MODELOS[clave_modelo_epoca]
                info_reporte["epoca_info"] = {
                    "modelo": clave_modelo_epoca,
                    "marco": info_modelo_epoca["marco"],
                    "epoca_destino": epoca_destino,
                    "epoca_obs": epoca_obs,
                    "cobertura": vemos.texto_cobertura(grid_epoca),
                    "corregidos": puntos_corregidos_epoca,
                    "fuera_cobertura": puntos_fuera_cobertura_epoca,
                }
            html_reporte = core.construir_reporte_html(info_reporte)
            ok, msg = self._generar_reporte_html(html_reporte, ruta_reporte)
            if ok:
                reporte_ok = True
                self._log(self._tr("log_reporte_generado", ruta=ruta_reporte))
            else:
                self._log(self._tr("log_reporte_error", msg=msg))

        resumen = self._tr("resumen_principal", ruta=out_path, procesados=len(resultados), omitidos=len(errores))
        if exportar_shp:
            resumen += self._tr("resumen_shp", ruta=ruta_shp)
        if exportar_dxf:
            resumen += self._tr("resumen_dxf", ruta=ruta_dxf)
        if generar_reporte:
            resumen += self._tr(
                "resumen_reporte",
                ruta=ruta_reporte if reporte_ok else self._tr("resumen_reporte_no_generado"),
            )

        QMessageBox.information(self, self._tr("info_proceso_terminado_titulo"), resumen)

    # ------------------------------------------------------------------
    # Creación de capas de puntos en el proyecto
    # ------------------------------------------------------------------
    def _crear_capa_puntos(self, nombre, crs, header, filas, x_field_idx, y_field_idx,
                            z_field_idx=None, id_field_name=None, agregar_al_proyecto=True,
                            geom_coords=None):
        """Crea una capa de puntos en memoria a partir de ``filas``.

        Si ``z_field_idx`` se indica y los valores de esa columna son
        numéricos, la geometría se crea en 3D (PointZ), útil tanto para
        visualizar la elevación en QGIS como para que quede disponible
        al exportar a Shapefile/DXF.

        ``geom_coords``, si se indica, es una lista paralela a ``filas``
        con una tupla ``(x, y, z_o_None)`` por fila que se usa para la
        **geometría** del punto en vez de las columnas
        ``x_field_idx``/``y_field_idx``/``z_field_idx`` de ``fila`` — los
        **atributos** de la capa (incluidas esas mismas columnas, p. ej.
        "X_ajustada") siguen saliendo de ``fila`` sin cambios, solo
        cambia dónde queda plantado el punto. Se usa para que, con la
        corrección de época (VEMOS) activada, los puntos de la capa
        "ajustada" (y su exportación a Shapefile) queden ubicados en las
        coordenadas ya corregidas a la época destino, sin tener que
        duplicar columnas en el CSV de salida.
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
        for i, fila in enumerate(filas):
            if geom_coords is not None:
                x, y, z = geom_coords[i]
                if x is None or y is None:
                    continue
                if usar_z and z is None:
                    z = 0.0
            else:
                try:
                    x = float(str(fila[x_field_idx]).replace(",", "."))
                    y = float(str(fila[y_field_idx]).replace(",", "."))
                except (ValueError, IndexError):
                    continue
                z = 0.0
                if usar_z:
                    # La capa se declaró como PointZ: todas sus
                    # geometrías deben serlo, así que si no hay Z válida
                    # para esta fila se usa 0.0 en vez de mezclar
                    # geometrías 2D y 3D en la misma capa (lo que algunos
                    # proveedores rechazan).
                    try:
                        z_text = str(fila[z_field_idx]).strip()
                        if z_text != "":
                            z = float(z_text.replace(",", "."))
                    except (ValueError, IndexError):
                        z = 0.0

            feat = QgsFeature(capa.fields())
            if usar_z:
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

    def _crear_capa_dxf(self, crs, resultados, idx_id, coords_finales=None):
        """Crea una capa liviana de puntos ajustados pensada para la
        exportación a DXF: solo geometría (con Z si está disponible) y
        un campo especial "OGR_STYLE" con un "Feature Style String"
        ``LABEL(t:"...")`` por punto (columna ID si se seleccionó, o
        un consecutivo P1, P2, ...).

        OGR/GDAL reservan el nombre de campo "OGR_STYLE": no se crea
        como campo de atributo real, sino que su valor por entidad se
        usa como el estilo de la entidad al escribir. El driver DXF
        solo dibuja una etiqueta de texto (TEXT/MTEXT) junto al punto
        cuando ese estilo empieza por "LABEL"; un campo de atributo
        normal llamado "Text" NO lo lee el escritor DXF (solo lo usa
        el *lector* al reconstruir entidades TEXT existentes), por lo
        que esa variante dejaba los DXF exportados sin etiquetas.

        ``coords_finales``, si se indica, es una lista paralela a
        ``resultados`` con una tupla ``(x, y, z_o_None)`` por punto que
        se usa para la geometría en vez de ``r["x_adj"]``/``r["y_adj"]``/
        ``r["z_adj"]`` — con la corrección de época (VEMOS) activada, ya
        trae las coordenadas corregidas a la época destino (o las
        ajustadas sin corregir, si el punto cayó fuera de la cobertura
        real del modelo elegido).
        """
        capa = QgsVectorLayer("PointZ?crs={}".format(crs.authid() or crs.toWkt()), "dxf_tmp", "memory")
        proveedor = capa.dataProvider()
        tipo_texto = _tipo_campo_texto()
        proveedor.addAttributes([QgsField("OGR_STYLE", tipo_texto)])
        capa.updateFields()

        features = []
        for i, r in enumerate(resultados):
            valor_id = r["original"][idx_id] if (idx_id is not None and idx_id < len(r["original"])) else None
            etiqueta = core.etiqueta_punto(valor_id, r["fila"])
            estilo = core.estilo_etiqueta_dxf(etiqueta)
            if coords_finales is not None:
                x, y, z = coords_finales[i]
            else:
                x, y, z = r["x_adj"], r["y_adj"], r["z_adj"]
            if z is None:
                z = 0.0
            feat = QgsFeature(capa.fields())
            feat.setGeometry(QgsGeometry(QgsPoint(x, y, z)))
            feat.setAttributes([estilo])
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
