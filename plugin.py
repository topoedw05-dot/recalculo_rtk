# -*- coding: utf-8 -*-
"""
plugin.py
=========

Clase principal del complemento: registra el ícono/menú en QGIS y abre
el diálogo de recálculo.
"""

import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

from .recalculo_dialog import RecalculoRTKDialog
from . import i18n


class RecalculoRTKPlugin:
    """Recalcula coordenadas de campo (base RTK libre) hacia
    coordenadas ajustadas por postproceso estático."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.dialog = None
        # Idioma detectado automáticamente a partir de la configuración de
        # QGIS (ver i18n.detectar_idioma_qgis), usado para el texto del
        # menú/ícono del complemento. El diálogo (recalculo_dialog.py)
        # detecta el idioma de forma independiente al abrirse, por si el
        # usuario cambió el idioma de QGIS entre que se cargó el
        # complemento y que lo usó.
        self.idioma = i18n.detectar_idioma_qgis()
        self.menu = i18n.tr(self.idioma, "plugin_menu")

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        self.action = QAction(
            QIcon(icon_path),
            i18n.tr(self.idioma, "plugin_accion"),
            self.iface.mainWindow(),
        )
        self.action.setWhatsThis(i18n.tr(self.idioma, "plugin_whatsthis"))
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.menu, self.action)
        self.actions.append(self.action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []
        if self.dialog is not None:
            self.dialog.close()
            self.dialog = None

    def run(self):
        if self.dialog is None:
            self.dialog = RecalculoRTKDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
